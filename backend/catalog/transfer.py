# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Import / export of the catalog data set as a portable ZIP archive.

The archive bundles a ``manifest.json`` (all structural + inventory data, keyed
by natural keys so it is portable across instances) and a ``media/`` folder with
the referenced images and uploads. Two scopes:

* ``full`` — the whole system: product types (+ images, order), products
  (+ images), sections (with their product types), sets, all pools and
  resources, plus the CMS pages and shop/welcome settings.
* ``pool`` — a single pool with its resources and just the structure those
  resources need (the referenced products, their product types and images).

Excluded by design: personal/operational data (users, bookings, blocks,
strikes) and the per-pool GitLab token (an instance-bound encrypted secret).

Import is a merge/upsert keyed by natural keys (``pool_id``,
``inventory_number``, ``name`` / ``title`` / ``slug``): existing rows are
updated, missing ones created. It runs in one transaction and supports a
dry-run that rolls back and only reports what would change.

Archives written before #20 (product types replace categories) carry a
``categories`` list and sections listing ``categories``. They are converted on
import with the same rules as migration 0049 (see ``_convert_categories``).
"""

import io
import json
import zipfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import translation

from .structure import derive_section_types
from .models import (
    Page,
    Product,
    ProductImage,
    ProductSet,
    ProductType,
    Resource,
    ResourcePool,
    Section,
    ShopSetting,
    WelcomeSetting,
)
from .inventory import default_qr_code_id
from .richtext import clean_rich, looks_like_html, markdown_to_html, plain_to_html

def _normalise_import_attributes(attributes, schema):
    """Apply the current stored shape to imported attribute values (wraps
    free-text values to {de,en}); unknown keys pass through unchanged."""
    from .serializers import _normalize_attr_value

    by_key = {a["key"]: a for a in (schema or []) if a.get("key")}
    result = {}
    for key, value in (attributes or {}).items():
        result[key] = _normalize_attr_value(by_key[key], value) if key in by_key else value
    return result


FORMAT = "ausleihbar-transfer"
VERSION = 1

# Translatable base fields per model (django-modeltranslation adds _de/_en).
TRANSLATED = {
    ProductType: ("name", "description"),
    Product: ("title", "description", "return_info"),
    ResourcePool: ("name", "description", "address", "room", "directions"),
    Section: ("title", "description"),
    ProductSet: ("name", "description"),
    Page: ("title", "body"),
}

POOL_FIELDS = (
    "pool_id", "name", "description", "address", "room", "directions",
    "phone", "email", "notify_on_defect", "defect_gitlab_url",
    "opening_hours", "closed_weekdays", "lead_time_hours", "max_booking_months",
    "default_min_days", "default_max_days", "default_min_hours",
    "default_max_hours", "is_active",
)
RESOURCE_FIELDS = (
    "inventory_number", "qr_code_id", "status", "serial_number",
    "storage_location", "procurement_date", "warranty_end", "value",
    "procuring_institution", "owning_institution", "lending_type",
    "min_duration", "max_duration",
)


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

class _MediaWriter:
    """Copies referenced media files into the archive, de-duplicated by path."""

    def __init__(self, zf):
        self.zf = zf
        self.seen = set()

    def add(self, field_file):
        if not field_file:
            return None
        name = field_file.name  # storage-relative, e.g. "products/x.jpg"
        if not name:
            return None
        arc = f"media/{name}"
        if name not in self.seen:
            try:
                with field_file.open("rb") as fh:
                    self.zf.writestr(arc, fh.read())
                self.seen.add(name)
            except (FileNotFoundError, OSError):
                return None  # file vanished — skip rather than fail the export
        return arc


def _dump_translations(obj):
    out = {}
    for field in TRANSLATED.get(type(obj), ()):
        for lang in ("de", "en"):
            out[f"{field}_{lang}"] = getattr(obj, f"{field}_{lang}") or ""
    return out


def _decimal(value):
    return str(value) if value is not None else None


def _product_dict(product, media):
    data = {
        "title": product.title,
        "product_type": product.product_type.name,
        "lending_type": product.lending_type,
        "min_duration": product.min_duration,
        "max_duration": product.max_duration,
        "attributes": product.attributes,
        "images": [
            {"position": img.position, "file": media.add(img.image)}
            for img in product.images.all()
        ],
        **_dump_translations(product),
    }
    return data


def build_archive(scope="full", pool=None):
    """Return the export ZIP as bytes for ``scope`` ('full' or 'pool')."""
    # Pin the active language to the canonical one so the bare model fields
    # (title/name/…) resolve to a single, stable column regardless of request.
    with translation.override(settings.MODELTRANSLATION_DEFAULT_LANGUAGE):
        return _build_archive(scope, pool)


def _build_archive(scope, pool):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        media = _MediaWriter(zf)
        manifest = {"format": FORMAT, "version": VERSION, "scope": scope}

        if scope == "pool":
            if pool is None:
                raise ValueError("A pool is required for a pool-scoped export.")
            pools = [pool]
            resources = list(
                Resource.objects.filter(resource_pool=pool)
                .select_related("product__product_type")
                .order_by("inventory_number")
            )
            products = sorted(
                {r.product for r in resources}, key=lambda p: p.title
            )
            product_types = sorted(
                {p.product_type for p in products}, key=lambda t: t.name
            )
            sections, sets_ = [], []
            include_settings = False
        else:
            product_types = list(ProductType.objects.order_by("name"))
            products = list(
                Product.objects.select_related("product_type")
                .prefetch_related("images")
                .order_by("title")
            )
            sets_ = list(
                ProductSet.objects.select_related("resource_pool")
                .prefetch_related("products")
                .order_by("name")
            )
            sections = list(
                Section.objects.prefetch_related("product_types", "sets").order_by(
                    "title"
                )
            )
            pools = list(ResourcePool.objects.order_by("pool_id"))
            resources = list(
                Resource.objects.select_related("product", "resource_pool")
                .order_by("inventory_number")
            )
            include_settings = True

        # id → natural key maps, to express relations portably.
        product_key = {p.id: p.title for p in products}

        manifest["product_types"] = [
            {
                "name": t.name,
                "attribute_schema": t.attribute_schema,
                "image": media.add(t.image),
                "position": t.position,
                "product_order": [
                    product_key[pid] for pid in t.product_order if pid in product_key
                ],
                **_dump_translations(t),
            }
            for t in product_types
        ]
        manifest["products"] = [_product_dict(p, media) for p in products]
        manifest["product_sets"] = [
            {
                "name": s.name,
                "resource_pool": s.resource_pool.pool_id if s.resource_pool else None,
                "products": [
                    product_key[p.id] for p in s.products.all() if p.id in product_key
                ],
                **_dump_translations(s),
            }
            for s in sets_
        ]
        set_key = {s.id: s.name for s in sets_}
        type_key = {t.id: t.name for t in product_types}
        manifest["sections"] = [
            {
                "title": sec.title,
                "image": media.add(sec.image),
                "position": sec.position,
                "product_types": [
                    type_key[t.id] for t in sec.product_types.all() if t.id in type_key
                ],
                "sets": [set_key[s.id] for s in sec.sets.all() if s.id in set_key],
                "product_type_order": [
                    type_key[tid] for tid in sec.product_type_order if tid in type_key
                ],
                "set_order": [
                    set_key[sid] for sid in sec.set_order if sid in set_key
                ],
                **_dump_translations(sec),
            }
            for sec in sections
        ]
        manifest["resource_pools"] = [
            {**{f: getattr(p, f) for f in POOL_FIELDS}, "image": media.add(p.image),
             **_dump_translations(p)}
            for p in pools
        ]
        manifest["resources"] = [
            {
                **{f: getattr(r, f) for f in RESOURCE_FIELDS if f != "value"},
                "value": _decimal(r.value),
                "procurement_date": r.procurement_date.isoformat() if r.procurement_date else None,
                "warranty_end": r.warranty_end.isoformat() if r.warranty_end else None,
                "product": r.product.title,
                "resource_pool": r.resource_pool.pool_id,
            }
            for r in resources
        ]

        if include_settings:
            manifest["pages"] = [
                {"slug": p.slug, "is_published": p.is_published,
                 "show_in_footer": p.show_in_footer, "footer_order": p.footer_order,
                 **_dump_translations(p)}
                for p in Page.objects.order_by("slug")
            ]
            welcome = WelcomeSetting.objects.first()
            if welcome:
                manifest["welcome_setting"] = {
                    "text": welcome.text, "logo": media.add(welcome.logo)
                }
            shop = ShopSetting.objects.first()
            if shop:
                manifest["shop_setting"] = {
                    "show_popular": shop.show_popular,
                    "show_new_arrivals": shop.show_new_arrivals,
                    "new_product_days": shop.new_product_days,
                }

        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

class ImportError_(Exception):
    """The uploaded archive is not a valid Ausleihbar transfer archive."""


def _set_translations(obj, data):
    """Apply *_de/*_en from the manifest. Must run inside a
    ``translation.override(default)`` block so the bare field writes the
    default-language column. Empty translations are stored as NULL (not ""),
    so the per-language unique columns don't collide across rows."""
    default = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    for field in TRANSLATED.get(type(obj), ()):
        values = {lang: (data.get(f"{field}_{lang}") or None) for lang in ("de", "en")}
        for lang, value in values.items():
            setattr(obj, f"{field}_{lang}", value)
        # The bare field (also the natural-key column) must never be empty:
        # default language, else any non-empty translation.
        bare = values.get(default) or next((v for v in values.values() if v), "")
        setattr(obj, field, bare or "")


def _normalise_rich(obj, fields, fn):
    """Bring an imported rich-text field (#5) up to the sanitized HTML subset:
    Markdown/plain-text values (from an archive written before the field
    became rich HTML) are converted with ``fn``; anything that already looks
    like HTML is only re-sanitized. Mirrors migration 0047."""
    for field in fields:
        value = getattr(obj, field, None)
        if not value:
            continue
        if not looks_like_html(value):
            value = fn(value)
        setattr(obj, field, clean_rich(value))


def _save_media(zf, arc_path, counters):
    """Write a media file from the archive into storage; return its stored name."""
    if not arc_path:
        return None
    try:
        raw = zf.read(arc_path)
    except KeyError:
        return None
    name = arc_path[len("media/"):]
    saved = default_storage.save(name, ContentFile(raw))
    counters["media"] += 1
    return saved


def import_archive(file_obj, dry_run=False):
    """Merge an export archive into the database.

    ``file_obj`` is an uploaded ZIP. Returns a summary dict of created/updated
    counts per entity. With ``dry_run`` the transaction is rolled back.
    """
    try:
        zf = zipfile.ZipFile(file_obj)
        manifest = json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ImportError_("Not a valid transfer archive (missing manifest).") from exc
    if manifest.get("format") != FORMAT:
        raise ImportError_("This file is not an Ausleihbar transfer archive.")

    summary = {"created": {}, "updated": {}, "converted": {}, "media": 0}

    def bump(kind, key):
        summary[kind][key] = summary[kind].get(key, 0) + 1

    class _Rollback(Exception):
        pass

    try:
        with translation.override(settings.MODELTRANSLATION_DEFAULT_LANGUAGE):
            with transaction.atomic():
                _do_import(zf, manifest, summary, bump)
                if dry_run:
                    raise _Rollback()
    except _Rollback:
        summary["dry_run"] = True
    return summary


def _canon(model):
    """Queryset that matches the canonical (original) columns, not the active
    language's — modeltranslation otherwise rewrites ``name``/``title`` lookups
    to ``name_<lang>``, which misses rows created under another language.

    Soft-delete models use ``all_objects`` (not the default, alive-only
    ``objects``) so the natural-key lookup also finds TRASHED rows — a
    trashed row still occupies its unique slot (Rule B), so an alive-only
    lookup would miss it, try to create a new row with the same natural key,
    and blow up on the DB's unique constraint. ``_upsert`` restores a
    matched trashed row, since importing it re-establishes it as live."""
    qs = model.all_objects.all() if hasattr(model, "all_objects") else model.objects.all()
    return qs.rewrite(False) if hasattr(qs, "rewrite") else qs


def _upsert(model, **lookup):
    """Fetch by natural key (including trashed rows, for soft-delete models)
    or instantiate (unsaved) — so all fields, including unique translated
    columns, are populated before the INSERT. A trashed match is restored
    (``deleted_at``/``deleted_by`` cleared): the import re-establishes it as
    live, so it must not stay hidden in the trash."""
    obj = _canon(model).filter(**lookup).first()
    if obj is None:
        return model(**lookup), True
    if getattr(obj, "deleted_at", None) is not None:
        obj.deleted_at = None
        obj.deleted_by = None
    return obj, False


def _ordered_titles(titles, order, sort_key):
    """``titles`` listed in ``order`` first, the rest by ``sort_key`` (the
    migration's ``_order_by_ids`` on natural keys)."""
    rank = {t: i for i, t in enumerate(order)}
    listed = sorted((t for t in titles if t in rank), key=rank.__getitem__)
    rest = sorted((t for t in titles if t not in rank), key=sort_key)
    return listed + rest


def _convert_categories(zf, manifest, summary):
    """Convert the ``categories`` of a pre-#20 archive (product types replace
    categories) with the rules of migration 0049:

    * each section's product types are derived from its categories (in the
      section's category order, then position/title) and their products (in
      the category's product order, then title) via ``derive_section_types``;
    * a category whose products all share one type hands that type its image,
      description (per language) and product order — only where the type has
      none yet (the first such category, in section order, wins);
    * the archive's types get positions by first appearance across the
      sections (sections by position/title), the others after them by name —
      the archive carries no type positions of its own.

    Returns ``{section title: [type names]}`` for step 6 and counts the
    converted categories in ``summary["converted"]``. No-op for new archives.
    """
    categories = manifest.get("categories") or []
    if not categories:
        return {}
    by_title = {row["title"]: row for row in categories}
    # Live products (just imported or already present) → their type name.
    titles = {t for row in categories for t in row.get("products", [])}
    product_types = {
        title: type_name
        for title, type_name in _canon(Product)
        .filter(title__in=titles, deleted_at__isnull=True)
        .values_list("title", "product_type__name")
    }

    def category_data(row):
        products = [t for t in row.get("products", []) if t in product_types]
        ordered = _ordered_titles(products, row.get("product_order", []), str)
        return {
            "key": row["title"],
            "products": [
                {"product_type": product_types[t], "title": t} for t in ordered
            ],
        }

    def category_sort(title):
        row = by_title[title]
        return (row.get("position", 0), title)

    sections = sorted(
        manifest.get("sections", []), key=lambda r: (r.get("position", 0), r["title"])
    )
    section_input = []
    sequence = []  # categories in first-reach order, then the unreached ones
    for row in sections:
        cats = [t for t in row.get("categories", []) if t in by_title]
        cats = _ordered_titles(cats, row.get("category_order", []), category_sort)
        sequence.extend(t for t in cats if t not in sequence)
        section_input.append(
            {"key": row["title"], "categories": [category_data(by_title[t]) for t in cats]}
        )
    for title in sorted(by_title, key=category_sort):
        if title not in sequence:
            sequence.append(title)
    section_types, _ = derive_section_types(section_input)
    _, category_types = derive_section_types(
        [{"key": None, "categories": [category_data(by_title[t]) for t in sequence]}]
    )

    default = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    for title in sequence:
        type_name = category_types.get(title)
        if type_name is None:
            continue
        row = by_title[title]
        ptype = _canon(ProductType).get(name=type_name)
        changed = False
        if not ptype.image and row.get("image"):
            image = _save_media(zf, row["image"], summary)
            if image:
                ptype.image = image
                changed = True
        copied_description = False
        for lang in ("de", "en"):
            field = f"description_{lang}"
            if not getattr(ptype, field) and row.get(field):
                setattr(ptype, field, row[field])
                copied_description = True
        if copied_description:
            # Keep the bare column in step, as _set_translations does.
            other = "en" if default == "de" else "de"
            ptype.description = (
                getattr(ptype, f"description_{default}")
                or getattr(ptype, f"description_{other}")
                or ""
            )
            changed = True
        if not ptype.product_order and row.get("product_order"):
            ids = dict(
                _canon(Product)
                .filter(product_type=ptype, title__in=row["product_order"])
                .values_list("title", "id")
            )
            order = [ids[t] for t in row["product_order"] if t in ids]
            if order:
                ptype.product_order = order
                changed = True
        if changed:
            ptype.save()

    # Type positions: first appearance across sections, then the rest by name.
    reached = []
    for names in section_types.values():
        reached.extend(n for n in names if n not in reached)
    archive_types = [row["name"] for row in manifest.get("product_types", [])]
    rest = sorted((n for n in archive_types if n not in reached), key=str.casefold)
    for position, name in enumerate(reached + rest):
        _canon(ProductType).filter(name=name).update(position=position)

    summary["converted"]["categories"] = len(categories)
    return section_types


def _do_import(zf, manifest, summary, bump):
    # 1. Product types (by name). Their product order needs the products, so
    #    it is resolved after step 2.
    for row in manifest.get("product_types", []):
        obj, created = _upsert(ProductType, name=row["name"])
        obj.attribute_schema = row.get("attribute_schema", [])
        obj.position = row.get("position", obj.position)
        image = _save_media(zf, row.get("image"), summary)
        if image:
            obj.image = image
        _set_translations(obj, row)
        obj.save()
        bump("created" if created else "updated", "product_types")

    # 2. Products (by title) + their images.
    for row in manifest.get("products", []):
        ptype = _canon(ProductType).filter(name=row.get("product_type")).first()
        if ptype is None:
            continue  # type missing from a pool-scoped archive without it
        obj, created = _upsert(Product, title=row["title"])
        obj.product_type = ptype
        obj.lending_type = row.get("lending_type") or obj.lending_type
        obj.min_duration = row.get("min_duration")
        obj.max_duration = row.get("max_duration")
        obj.attributes = _normalise_import_attributes(
            row.get("attributes", {}), obj.product_type.attribute_schema
        )
        _set_translations(obj, row)
        obj.save()
        bump("created" if created else "updated", "products")
        # Images: match by position so a re-import doesn't duplicate.
        for img in row.get("images", []):
            saved = _save_media(zf, img.get("file"), summary)
            if not saved:
                continue
            pi, _ = ProductImage.objects.update_or_create(
                product=obj, position=img.get("position", 0),
                defaults={"image": saved},
            )

    # 2b. Product order within each type (product titles → ids of that type).
    for row in manifest.get("product_types", []):
        if "product_order" not in row:
            continue  # pre-#20 archive: keep the order (or take a category's, step 4)
        ptype = _canon(ProductType).get(name=row["name"])
        ids = dict(
            _canon(Product)
            .filter(product_type=ptype, title__in=row["product_order"])
            .values_list("title", "id")
        )
        ptype.product_order = [ids[t] for t in row["product_order"] if t in ids]
        ptype.save(update_fields=["product_order"])

    # 3. Pools (by pool_id).
    for row in manifest.get("resource_pools", []):
        obj, created = _upsert(ResourcePool, pool_id=row["pool_id"])
        for field in POOL_FIELDS:
            if field == "pool_id":
                continue
            setattr(obj, field, row.get(field, getattr(obj, field)))
        image = _save_media(zf, row.get("image"), summary)
        if image:
            obj.image = image
        _set_translations(obj, row)
        _normalise_rich(
            obj,
            ("description", "description_de", "description_en",
             "directions", "directions_de", "directions_en"),
            plain_to_html,
        )
        obj.save()
        bump("created" if created else "updated", "resource_pools")

    # 4. Categories of a pre-#20 archive → section product types (+ copies).
    derived_section_types = _convert_categories(zf, manifest, summary)

    # 5. Sets (by name).
    for row in manifest.get("product_sets", []):
        obj, created = _upsert(ProductSet, name=row["name"])
        pool_id = row.get("resource_pool")
        obj.resource_pool = (
            ResourcePool.objects.filter(pool_id=pool_id).first() if pool_id else None
        )
        _set_translations(obj, row)
        obj.save()
        obj.products.set(_canon(Product).filter(title__in=row.get("products", [])))
        bump("created" if created else "updated", "product_sets")

    # 6. Sections (by title) — product types/sets resolved by natural key.
    for row in manifest.get("sections", []):
        obj, created = _upsert(Section, title=row["title"])
        obj.position = row.get("position", obj.position)
        image = _save_media(zf, row.get("image"), summary)
        if image:
            obj.image = image
        _set_translations(obj, row)
        obj.save()
        if "product_types" in row:
            type_names = row["product_types"]
            type_order = row.get("product_type_order", [])
        else:  # pre-#20 archive: derived from the section's categories
            type_names = derived_section_types.get(row["title"], [])
            type_order = type_names
        types = list(_canon(ProductType).filter(name__in=type_names))
        sets_ = list(_canon(ProductSet).filter(name__in=row.get("sets", [])))
        obj.product_types.set(types)
        obj.sets.set(sets_)
        type_by_name = {t.name: t.id for t in types}
        set_by_name = {s.name: s.id for s in sets_}
        obj.product_type_order = [
            type_by_name[n] for n in type_order if n in type_by_name
        ]
        obj.set_order = [set_by_name[n] for n in row.get("set_order", []) if n in set_by_name]
        obj.save(update_fields=["product_type_order", "set_order"])
        bump("created" if created else "updated", "sections")

    # 7. Resources (by inventory_number) — product + pool resolved by natural key.
    for row in manifest.get("resources", []):
        product = _canon(Product).filter(title=row.get("product")).first()
        pool = ResourcePool.objects.filter(pool_id=row.get("resource_pool")).first()
        if product is None or pool is None:
            continue
        defaults = {f: row.get(f) for f in RESOURCE_FIELDS if f != "inventory_number"}
        defaults["product"] = product
        defaults["resource_pool"] = pool
        obj, created = _upsert(Resource, inventory_number=row["inventory_number"])
        qr = str(defaults.pop("qr_code_id", None) or "").strip()
        # Printed labels encode qr_code_id, so a stored ID is never replaced by
        # a blank or clashing manifest value (#57). "Free" is checked against
        # ALL rows (trashed ones still occupy their unique slot).
        taken = qr and _canon(Resource).filter(qr_code_id=qr).exclude(
            inventory_number=row["inventory_number"]
        ).exists()
        if qr and not taken:
            obj.qr_code_id = qr
        elif not obj.qr_code_id:
            obj.qr_code_id = default_qr_code_id(row["inventory_number"])
        for field, value in defaults.items():
            setattr(obj, field, value)
        obj.save()
        bump("created" if created else "updated", "resources")

    # 8. CMS pages + singleton settings (full archive only).
    for row in manifest.get("pages", []):
        obj, created = _upsert(Page, slug=row["slug"])
        obj.is_published = row.get("is_published", obj.is_published)
        obj.show_in_footer = row.get("show_in_footer", obj.show_in_footer)
        obj.footer_order = row.get("footer_order", obj.footer_order)
        _set_translations(obj, row)
        _normalise_rich(obj, ("body", "body_de", "body_en"), markdown_to_html)
        obj.save()
        bump("created" if created else "updated", "pages")

    welcome = manifest.get("welcome_setting")
    if welcome:
        ws = WelcomeSetting.objects.first() or WelcomeSetting()
        ws.text = welcome.get("text", "")
        _normalise_rich(ws, ("text",), markdown_to_html)
        logo = _save_media(zf, welcome.get("logo"), summary)
        if logo:
            ws.logo = logo
        ws.save()

    shop = manifest.get("shop_setting")
    if shop:
        ss = ShopSetting.objects.first() or ShopSetting()
        ss.show_popular = shop.get("show_popular", True)
        ss.show_new_arrivals = shop.get("show_new_arrivals", True)
        ss.new_product_days = shop.get("new_product_days", ss.new_product_days)
        ss.save()
