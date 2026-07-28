# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Import / export of the catalog data set as a portable ZIP archive.

The archive bundles a ``manifest.json`` (all structural + inventory data, keyed
by natural keys so it is portable across instances) and a ``media/`` folder with
the referenced images and uploads. Two scopes:

* ``full`` — the whole system: product types, products (+ images), categories,
  sections, sets, all pools and resources, plus the CMS pages and shop/welcome
  settings.
* ``pool`` — a single pool with its resources and just the structure those
  resources need (the referenced products, their product types and images).

Excluded by design: personal/operational data (users, bookings, blocks,
strikes) and the per-pool GitLab token (an instance-bound encrypted secret).

Import is a merge/upsert keyed by natural keys (``pool_id``,
``inventory_number``, ``name`` / ``title`` / ``slug``): existing rows are
updated, missing ones created. It runs in one transaction and supports a
dry-run that rolls back and only reports what would change.
"""

import io
import json
import uuid
import zipfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import translation

from .models import (
    Category,
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
    Category: ("title", "description"),
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
            categories, sections, sets_ = [], [], []
            include_settings = False
        else:
            product_types = list(ProductType.objects.order_by("name"))
            products = list(
                Product.objects.select_related("product_type")
                .prefetch_related("images")
                .order_by("title")
            )
            categories = list(
                Category.objects.prefetch_related("products").order_by("title")
            )
            sets_ = list(
                ProductSet.objects.select_related("resource_pool")
                .prefetch_related("products")
                .order_by("name")
            )
            sections = list(
                Section.objects.prefetch_related("categories", "sets").order_by(
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
            {"name": t.name, "attribute_schema": t.attribute_schema, **_dump_translations(t)}
            for t in product_types
        ]
        manifest["products"] = [_product_dict(p, media) for p in products]
        manifest["categories"] = [
            {
                "title": c.title,
                "image": media.add(c.image),
                "position": c.position,
                "products": [
                    product_key[p.id] for p in c.products.all() if p.id in product_key
                ],
                "product_order": [
                    product_key[pid] for pid in c.product_order if pid in product_key
                ],
                **_dump_translations(c),
            }
            for c in categories
        ]
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
        category_key = {c.id: c.title for c in categories}
        manifest["sections"] = [
            {
                "title": sec.title,
                "image": media.add(sec.image),
                "position": sec.position,
                "categories": [
                    category_key[c.id] for c in sec.categories.all() if c.id in category_key
                ],
                "sets": [set_key[s.id] for s in sec.sets.all() if s.id in set_key],
                "category_order": [
                    category_key[cid] for cid in sec.category_order if cid in category_key
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

    summary = {"created": {}, "updated": {}, "media": 0}

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
    to ``name_<lang>``, which misses rows created under another language."""
    qs = model.objects.all()
    return qs.rewrite(False) if hasattr(qs, "rewrite") else qs


def _upsert(model, **lookup):
    """Fetch by natural key or instantiate (unsaved) — so all fields, including
    unique translated columns, are populated before the INSERT."""
    obj = _canon(model).filter(**lookup).first()
    if obj is None:
        return model(**lookup), True
    return obj, False


def _do_import(zf, manifest, summary, bump):
    # 1. Product types (by name).
    for row in manifest.get("product_types", []):
        obj, created = _upsert(ProductType, name=row["name"])
        obj.attribute_schema = row.get("attribute_schema", [])
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
        obj.save()
        bump("created" if created else "updated", "resource_pools")

    # 4. Categories (by title) — products resolved by title.
    for row in manifest.get("categories", []):
        obj, created = _upsert(Category, title=row["title"])
        obj.position = row.get("position", obj.position)
        image = _save_media(zf, row.get("image"), summary)
        if image:
            obj.image = image
        _set_translations(obj, row)
        obj.save()
        products = list(
            _canon(Product).filter(title__in=row.get("products", []))
        )
        obj.products.set(products)
        by_title = {p.title: p.id for p in products}
        obj.product_order = [by_title[t] for t in row.get("product_order", []) if t in by_title]
        obj.save(update_fields=["product_order"])
        bump("created" if created else "updated", "categories")

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

    # 6. Sections (by title) — categories/sets resolved by natural key.
    for row in manifest.get("sections", []):
        obj, created = _upsert(Section, title=row["title"])
        obj.position = row.get("position", obj.position)
        image = _save_media(zf, row.get("image"), summary)
        if image:
            obj.image = image
        _set_translations(obj, row)
        obj.save()
        cats = list(_canon(Category).filter(title__in=row.get("categories", [])))
        sets_ = list(_canon(ProductSet).filter(name__in=row.get("sets", [])))
        obj.categories.set(cats)
        obj.sets.set(sets_)
        cat_by_title = {c.title: c.id for c in cats}
        set_by_name = {s.name: s.id for s in sets_}
        obj.category_order = [cat_by_title[t] for t in row.get("category_order", []) if t in cat_by_title]
        obj.set_order = [set_by_name[n] for n in row.get("set_order", []) if n in set_by_name]
        obj.save(update_fields=["category_order", "set_order"])
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
        # Keep qr_code_id unique: drop it if it already belongs to another unit.
        qr = defaults.get("qr_code_id")
        clash = Resource.objects.filter(qr_code_id=qr).exclude(
            inventory_number=row["inventory_number"]
        ).exists()
        if not qr or clash:
            defaults["qr_code_id"] = f"import-{uuid.uuid4().hex[:12]}"
        obj, created = Resource.objects.update_or_create(
            inventory_number=row["inventory_number"], defaults=defaults
        )
        bump("created" if created else "updated", "resources")

    # 8. CMS pages + singleton settings (full archive only).
    for row in manifest.get("pages", []):
        obj, created = _upsert(Page, slug=row["slug"])
        obj.is_published = row.get("is_published", obj.is_published)
        obj.show_in_footer = row.get("show_in_footer", obj.show_in_footer)
        obj.footer_order = row.get("footer_order", obj.footer_order)
        _set_translations(obj, row)
        obj.save()
        bump("created" if created else "updated", "pages")

    welcome = manifest.get("welcome_setting")
    if welcome:
        ws = WelcomeSetting.objects.first() or WelcomeSetting()
        ws.text = welcome.get("text", "")
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
