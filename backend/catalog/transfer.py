# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Import / export of the catalog data set as a portable ZIP archive.

The archive bundles a ``manifest.json`` (all structural + inventory data, keyed
by natural keys so it is portable across instances) and a ``media/`` folder with
the referenced images and uploads — including the rich-text images
(``rich/…``) referenced by the exported pools, pages and welcome text (#42).
Two scopes:

* ``full`` — the whole system: product types (attribute templates),
  categories (tree, images, order), products (+ images, categories), sections
  (with their top-level categories and sets), sets, all pools and resources,
  plus the CMS pages and shop/welcome settings.
* ``pool`` — a single pool with its resources and just the structure those
  resources need (the referenced products, their product types, their
  categories plus ancestors, and images).

Excluded by design: personal/operational data (users, bookings, blocks,
strikes) and the per-pool GitLab token (an instance-bound encrypted secret).

Import is a merge/upsert keyed by natural keys (``pool_id``,
``inventory_number``, ``name`` / ``title`` / ``slug``): existing rows are
updated, missing ones created. It runs in one transaction and supports a
dry-run that rolls back, writes no media files and only reports what would
change. Media files are de-duplicated by content on import (#64, see
``_MediaImporter``).

Categories (#78) are keyed by their **path**: the list of names (default
language, i.e. the bare ``name`` column) from the root down to the category.
Root names are unique among roots and sibling names per parent within an
archive; the import rejects duplicates and rows whose parent row is missing.

Two older formats are converted on import (``_category_plan``):

* pre-#20 archives (flat ``categories`` rows with ``title``, sections listing
  ``categories``) — their categories become top-level categories;
* ADR-0010-era archives (sections listing ``product_types``, types with
  image/position/product order) — every type in a section becomes a top-level
  category, with the rules of migration 0052 (``structure.categories_from_types``).
"""

import hashlib
import io
import json
import posixpath
import re
import zipfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DataError, IntegrityError, transaction
from django.db.models import F, Max
from django.utils import translation

from .structure import categories_from_types
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
from .inventory import default_qr_code_id
from . import rich_images
from .rich_images import RICH_IMAGE_EXTENSIONS, process_rich_image
from .richtext import (
    clean_rich,
    looks_like_html,
    markdown_to_html,
    plain_to_html,
    replace_rich_media,
    rich_media_names,
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
# 2: categories by path (#78); product types without navigation fields.
VERSION = 2

# Translatable base fields per model (django-modeltranslation adds _de/_en).
TRANSLATED = {
    ProductType: ("name", "description"),
    Category: ("name", "description"),
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
        return self._write(name, field_file.open)

    def add_name(self, name):
        """Add a file by its storage name (e.g. a rich-text image ``rich/x.png``)."""
        if not _safe_media_name(name):
            return None
        return self._write(name, lambda mode: default_storage.open(name, mode))

    def add_rich(self, obj):
        """Add every rich-text image (#42) referenced by ``obj``'s rich fields
        (all language columns, see ``RichHtmlModelMixin.rich_fields``)."""
        for field in getattr(obj, "rich_fields", ()):
            for name in sorted(rich_media_names(getattr(obj, field, None))):
                self.add_name(name)

    def _write(self, name, opener):
        arc = f"media/{name}"
        if name not in self.seen:
            try:
                with opener("rb") as fh:
                    self.zf.writestr(arc, fh.read())
                self.seen.add(name)
            except (FileNotFoundError, OSError):
                return None  # file vanished — skip rather than fail the export
        return arc


def _safe_media_name(name):
    """A storage-relative media file name without traversal (no absolute
    path, no ``..`` segment, not ``.`` or a bare directory name, i.e. it has a
    folder and a file part) — guards names parsed from HTML or read from an
    archive."""
    if not name or name.startswith("/") or "\\" in name or "\0" in name:
        return False
    if ".." in name.split("/") or posixpath.normpath(name) != name:
        return False
    # Must name a file inside a media folder: not ".", not a bare top-level
    # directory such as "rich" or "products".
    head, tail = posixpath.split(name)
    return bool(head) and bool(tail) and tail not in {".", ".."}


def _dump_translations(obj):
    out = {}
    for field in TRANSLATED.get(type(obj), ()):
        for lang in ("de", "en"):
            out[f"{field}_{lang}"] = getattr(obj, f"{field}_{lang}") or ""
    return out


def _decimal(value):
    return str(value) if value is not None else None


def _product_dict(product, media, category_paths):
    data = {
        "title": product.title,
        "product_type": product.product_type.name,
        "categories": sorted(
            category_paths[c.pk] for c in product.categories.all()
            if c.pk in category_paths
        ),
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


def _category_paths(scope, products):
    """``{category id: path}`` of the categories to export — all live ones
    (``full``) or those of ``products`` plus their ancestors (``pool``). A
    category in or below the trash is left out. Paths use the bare ``name``
    column, the natural key the import matches on."""
    nodes = {
        pk: (parent_id, name, deleted_at)
        for pk, parent_id, name, deleted_at in _canon(Category).values_list(
            "pk", "parent_id", "name", "deleted_at"
        )
    }

    def chain(pk):
        """Ids root → ``pk``, or None if any of them is trashed."""
        ids, seen = [], set()
        while pk is not None:
            if pk in seen or pk not in nodes or nodes[pk][2] is not None:
                return None
            seen.add(pk)
            ids.append(pk)
            pk = nodes[pk][0]
        return ids[::-1]

    if scope == "pool":
        wanted = set()
        for product in products:
            for category in product.categories.all():
                wanted.update(chain(category.pk) or ())
    else:
        wanted = {pk for pk in nodes if chain(pk)}
    return {pk: [nodes[i][1] for i in chain(pk)] for pk in wanted}


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
                .prefetch_related("product__categories")
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
                .prefetch_related("images", "categories")
                .order_by("title")
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

        category_paths = _category_paths(scope, products)
        categories = {
            c.pk: c for c in Category.objects.filter(pk__in=category_paths)
        }

        def tree_key(pk):
            # Depth-first: parents before children, siblings by position/name.
            key, node = [], categories[pk]
            while node is not None:
                key.append((node.position, category_paths[node.pk][-1]))
                node = categories.get(node.parent_id)
            return key[::-1]

        def category_dict(c):
            data = {
                "path": category_paths[c.pk],
                "image": media.add(c.image),
                **_dump_translations(c),
            }
            # Position and product order are system-wide structure; a pool
            # archive (a subset of the products) must not carry them.
            if scope != "pool":
                data["position"] = c.position
                data["product_order"] = [
                    product_key[pid] for pid in c.product_order if pid in product_key
                ]
            return data

        manifest["product_types"] = [
            {"name": t.name, "attribute_schema": t.attribute_schema,
             **_dump_translations(t)}
            for t in product_types
        ]
        manifest["categories"] = [
            category_dict(categories[pk]) for pk in sorted(categories, key=tree_key)
        ]
        manifest["products"] = [
            _product_dict(p, media, category_paths) for p in products
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
        # Sections hold top-level categories only, keyed by their name.
        root_key = {pk: path[0] for pk, path in category_paths.items() if len(path) == 1}
        manifest["sections"] = [
            {
                "title": sec.title,
                "image": media.add(sec.image),
                "position": sec.position,
                "categories": [
                    root_key[c.id] for c in sec.categories.all() if c.id in root_key
                ],
                "sets": [set_key[s.id] for s in sec.sets.all() if s.id in set_key],
                "category_order": [
                    root_key[cid] for cid in sec.category_order if cid in root_key
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
        for p in pools:
            media.add_rich(p)
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
            pages = list(Page.objects.order_by("slug"))
            manifest["pages"] = [
                {"slug": p.slug, "is_published": p.is_published,
                 "show_in_footer": p.show_in_footer, "footer_order": p.footer_order,
                 **_dump_translations(p)}
                for p in pages
            ]
            for p in pages:
                media.add_rich(p)
            welcome = WelcomeSetting.objects.first()
            if welcome:
                media.add_rich(welcome)
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


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _stored_sha256(name):
    with default_storage.open(name, "rb") as fh:
        digest = hashlib.sha256()
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _MediaImporter:
    """Writes media files from the archive into storage (#64).

    For every archive file (``media/<name>``) the target is ``<name>``:

    * a file with identical content (SHA-256) already at the target is reused —
      a re-import of the same archive writes no new files;
    * a different file at the target is kept, and the archive file goes to the
      storage's next available name (``get_available_name``), which is returned;
    * otherwise the file is saved at the target.

    In a dry-run nothing is written at all: the name that *would* be used is
    returned (so reference rewriting and the summary still work), and
    ``summary["media"]`` counts the files that *would be written*. In both
    modes it counts written files only — reused ones are not counted.

    Rich-text images (``media/rich/…``, #68) first go through the upload's
    validation and metadata-stripping re-encode (``rich_images.
    process_rich_image``): the re-encoded bytes are stored, under the detected
    format's extension (a changed name is reported like a collision rename, so
    ``rewrite`` updates the HTML). An existing file is reused if it equals the
    archive bytes or the re-encoded ones (re-encoding a JPEG is not
    byte-stable, so both are checked). A file that is no valid image or
    exceeds the limits is skipped and listed in ``summary["skipped_media"]``;
    its references stay as they are.

    Results are memoised per archive path, so a file referenced twice is
    written (and counted) once.
    """

    def __init__(self, zf, summary, dry_run=False):
        self.zf = zf
        self.summary = summary
        self.dry_run = dry_run
        self._done = {}
        self.renamed = {}  # rich-text images: archive name → stored name

    def save(self, arc_path):
        """Store ``arc_path`` from the archive; return its stored name (None if
        missing or unsafe)."""
        if not arc_path or not arc_path.startswith("media/"):
            return None
        if arc_path in self._done:
            return self._done[arc_path]
        target = arc_path[len("media/"):]
        stored = None
        if _safe_media_name(target):
            try:
                if (
                    target.startswith("rich/")
                    and self.zf.getinfo(arc_path).file_size > rich_images.RICH_IMAGE_MAX_BYTES
                ):
                    # too big: skip without decompressing (zip-bomb guard)
                    self.summary["skipped_media"].append(target)
                    self._done[arc_path] = None
                    return None
                raw = self.zf.read(arc_path)
            except KeyError:
                raw = None
            if raw is not None:
                try:
                    stored = self._store_any(target, raw)
                except OSError:
                    stored = None  # unwritable/unreadable target — skip the file
        self._done[arc_path] = stored
        return stored

    def _store_any(self, target, raw):
        if not target.startswith("rich/"):
            return self._store(target, raw)
        try:
            data, ext = process_rich_image(raw)
        except ValueError:
            self.summary["skipped_media"].append(target)
            return None
        stem, old_ext = posixpath.splitext(target)
        if old_ext.lower() not in RICH_IMAGE_EXTENSIONS[ext]:
            target = stem + ext
        return self._store(target, data, also_matches=raw)

    def _store(self, target, raw, also_matches=None):
        if default_storage.exists(target):
            digest = _stored_sha256(target)
            if digest == _sha256(raw) or (
                also_matches is not None and digest == _sha256(also_matches)
            ):
                return target  # identical file already there — reuse it
            name = default_storage.get_available_name(target)
        else:
            name = target
        if not self.dry_run:
            name = default_storage.save(name, ContentFile(raw))
        self.summary["media"] += 1  # written, or would be written (dry-run)
        return name

    def save_rich(self, manifest):
        """Store the rich-text images (#42) referenced by the manifest's rich
        fields (pools, pages, welcome text — all language columns) and record
        which ones got a different name, for ``rewrite``. Must run before the
        rows holding those fields are saved."""
        names = set()
        rows = list(manifest.get("resource_pools", [])) + list(manifest.get("pages", []))
        if manifest.get("welcome_setting"):
            rows.append(manifest["welcome_setting"])
        for row in rows:
            for value in row.values():
                if isinstance(value, str):
                    names |= rich_media_names(value)
        for name in sorted(names):
            stored = self.save(f"media/{name}")
            if stored and stored != name:
                self.renamed[name] = stored

    def rewrite(self, obj):
        """Point ``obj``'s rich fields at the renamed rich-text images. URLs
        are matched by their normalised storage name (``rich_media_name``) and
        rewritten to the canonical relative ``/<MEDIA_URL>/<new>`` form, the
        only one the sanitizer keeps."""
        if not self.renamed:
            return
        for field in getattr(obj, "rich_fields", ()):
            value = getattr(obj, field, None)
            if value:
                setattr(obj, field, replace_rich_media(value, self.renamed))


def import_archive(file_obj, dry_run=False):
    """Merge an export archive into the database.

    ``file_obj`` is an uploaded ZIP. Returns a summary dict of created/updated
    counts per entity; ``media`` counts the media files written (or, with
    ``dry_run``, that would be written); ``skipped_media`` lists the storage
    names of rich-text images rejected as invalid (#68). With ``dry_run`` the transaction is
    rolled back and no file is written.
    """
    try:
        zf = zipfile.ZipFile(file_obj)
        manifest = json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ImportError_("Not a valid transfer archive (missing manifest).") from exc
    if manifest.get("format") != FORMAT:
        raise ImportError_("This file is not an Ausleihbar transfer archive.")

    # Validate the category structure up front, before anything is written.
    try:
        plan = _category_plan(manifest)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ImportError_(f"Malformed archive: {exc!r}") from exc
    summary = {"created": {}, "updated": {}, "converted": dict(plan["converted"]),
               "media": 0, "skipped_media": []}

    def bump(kind, key):
        summary[kind][key] = summary[kind].get(key, 0) + 1

    class _Rollback(Exception):
        pass

    try:
        with translation.override(settings.MODELTRANSLATION_DEFAULT_LANGUAGE):
            with transaction.atomic():
                _do_import(
                    manifest, plan, summary, bump, _MediaImporter(zf, summary, dry_run)
                )
                if dry_run:
                    raise _Rollback()
    except _Rollback:
        summary["dry_run"] = True
    except (IntegrityError, DataError) as exc:
        # Rolled back. E.g. a value too long for its column, or a clash with
        # a live row (unique category names per parent).
        raise ImportError_(f"The archive conflicts with existing data: {exc}") from exc
    except (KeyError, TypeError, AttributeError) as exc:
        # Rolled back. A hand-edited/malformed manifest (missing key, wrong type).
        raise ImportError_(f"Malformed archive: {exc!r}") from exc
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
    qs = _canon(model).filter(**lookup)
    if hasattr(model, "all_objects"):
        # Natural keys without a unique constraint (category names) may match
        # several rows: prefer a live one.
        qs = qs.order_by(F("deleted_at").asc(nulls_first=True), "pk")
    obj = qs.first()
    if obj is None:
        return model(**lookup), True
    if getattr(obj, "deleted_at", None) is not None:
        obj.deleted_at = None
        obj.deleted_by = None
    return obj, False


def _fmt_path(path):
    return " › ".join(str(name) for name in path)


CATEGORY_NAME_MAX = Category._meta.get_field("name").max_length


def _category_path(value):
    """A category path from the archive as a tuple, or ``ImportError_``."""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(name, str) and name.strip() for name in value)
    ):
        raise ImportError_(f"Invalid category path in the archive: {value!r}.")
    too_long = [name for name in value if len(name) > CATEGORY_NAME_MAX]
    if too_long:
        raise ImportError_(
            f"Category name longer than {CATEGORY_NAME_MAX} characters in the "
            f"archive: {too_long[0][:40]}…"
        )
    return tuple(value)


def _category_plan(manifest):
    """Read the archive's categories into one shape, whatever the format.

    Returns ``{"rows", "sections", "converted"}``; each row is
    ``{"path", "data", "image", "position", "product_order", "products"}``
    (``data`` holds the ``name_*``/``description_*`` translations; a
    ``None`` position/product order means "not in the archive"; ``products``
    lists product titles to add, for formats whose products don't name their
    categories). Rows come parents first. ``sections`` maps a section title
    to its converted top-level category names (ADR-0010 archives only).

    * Current archives: ``categories`` rows keyed by ``path``.
    * Pre-#20 archives: flat ``categories`` rows with ``title`` → top-level
      categories (``converted["categories"]``).
    * ADR-0010-era archives (no categories, sections listing
      ``product_types``): every type in a section becomes a top-level category
      with its translations, image, position and product order, and the
      archive's products of that type; sections map ``product_type_order``
      (rules of migration 0052, ``converted["product_types"]``).

    Raises ``ImportError_`` for malformed or duplicate paths and for a row
    whose parent row is missing.
    """
    raw = manifest.get("categories") or []
    if not isinstance(raw, list) or not all(isinstance(r, dict) for r in raw):
        raise ImportError_("Invalid categories in the archive.")
    plan = {"rows": [], "sections": {}, "converted": {}}
    rows = plan["rows"]
    if any("path" not in r and "title" in r for r in raw):
        for r in raw:
            rows.append({
                "path": _category_path([r.get("title")]),
                "data": {
                    "name_de": r.get("title_de"), "name_en": r.get("title_en"),
                    "description_de": r.get("description_de"),
                    "description_en": r.get("description_en"),
                },
                "image": r.get("image"),
                "position": r.get("position", 0),
                "product_order": r.get("product_order") or [],
                "products": r.get("products") or [],
            })
        plan["converted"]["categories"] = len(raw)
    elif raw:
        for r in raw:
            rows.append({
                "path": _category_path(r.get("path")),
                "data": r,
                "image": r.get("image"),
                "position": r.get("position"),
                "product_order": r.get("product_order"),
                "products": None,
            })
    else:
        sections = [
            s for s in manifest.get("sections") or []
            if "product_types" in s and "categories" not in s
        ]
        if sections:
            types = {t["name"]: t for t in manifest.get("product_types") or []}
            converted, section_categories = categories_from_types(
                [{"key": n, "name": n, "position": t.get("position")}
                 for n, t in types.items()],
                [{"key": s["title"], "types": s.get("product_types") or [],
                  "type_order": s.get("product_type_order") or []}
                 for s in sections],
            )
            products = {}
            for p in manifest.get("products") or []:
                products.setdefault(p.get("product_type"), []).append(p["title"])
            for name in converted:
                t = types[name]
                rows.append({
                    "path": _category_path([name]),
                    "data": t,
                    "image": t.get("image"),
                    "position": t.get("position") or 0,
                    "keep_position": True,  # an existing category keeps its own
                    "product_order": t.get("product_order") or [],
                    "products": products.get(name, []),
                })
            plan["sections"] = section_categories
            plan["converted"]["product_types"] = len(converted)

    paths = set()
    for row in rows:
        if row["path"] in paths:
            raise ImportError_(
                f"Duplicate category in the archive: {_fmt_path(row['path'])}."
            )
        paths.add(row["path"])
    for row in rows:
        if len(row["path"]) > 1 and row["path"][:-1] not in paths:
            raise ImportError_(
                f"Category {_fmt_path(row['path'])} has no parent in the archive."
            )
    rows.sort(key=lambda r: len(r["path"]))  # stable: parents first
    return plan


def _import_categories(plan, full, media, bump):
    """Upsert the plan's categories (parents first), matched by path.

    Returns ``(by_path, writable)``: the categories by path, and the paths
    whose system-wide structure (position, product order, image) this archive
    may set — all of them in a full archive, only newly created ones in a pool
    archive (an existing category only gets an image if it has none).
    """
    default = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    by_path, writable = {}, set()
    for row in plan["rows"]:
        path = row["path"]
        parent = by_path[path[:-1]] if len(path) > 1 else None
        obj, created = _upsert(Category, parent=parent, name=path[-1])
        if full or created:
            writable.add(path)
        position = row["position"]
        if row.get("keep_position") and not created:
            position = None  # ADR-0010 conversion: like migration 0052
        if full and position is not None:
            obj.position = position
        elif created:
            # No position in the archive: append after the existing siblings.
            last = _canon(Category).filter(parent=parent).aggregate(m=Max("position"))["m"]
            obj.position = 0 if last is None else last + 1
        if path in writable or not obj.image:
            image = media.save(row["image"])
            if image:
                obj.image = image
        if full or created:
            # A pool archive never rewrites an existing category's texts.
            _set_translations(obj, row["data"])
            # The path is the natural key: its last name is the default-language
            # name (the bare column follows it on save).
            setattr(obj, f"name_{default}", path[-1])
            obj.name = path[-1]
        obj.save()
        by_path[path] = obj
        bump("created" if created else "updated", "categories")
    return by_path, writable


def _import_category_products(plan, by_path, writable):
    """Add the products a converted row lists, then set each writable
    category's product order (titles → ids of its products)."""
    for row in plan["rows"]:
        category = by_path[row["path"]]
        if row["products"]:
            category.products.add(
                *_canon(Product).filter(title__in=row["products"], deleted_at__isnull=True)
            )
        if row["product_order"] is not None and row["path"] in writable:
            ids = dict(
                _canon(Product)
                .filter(categories=category, title__in=row["product_order"])
                .values_list("title", "id")
            )
            category.product_order = list(
                dict.fromkeys(ids[t] for t in row["product_order"] if t in ids)
            )
            category.save(update_fields=["product_order"])


def _top_level_category(by_path, name):
    """A section's category by name: the archive's, else a live existing one."""
    found = by_path.get((name,))
    if found is None:
        found = (
            _canon(Category)
            .filter(parent__isnull=True, name=name, deleted_at__isnull=True)
            .order_by("pk")
            .first()
        )
    return found


def _do_import(manifest, plan, summary, bump, media):
    # 0. Rich-text images (#42) first: a renamed one (#64) changes the URLs
    #    the pool/page/welcome HTML must point to before those rows are saved.
    media.save_rich(manifest)

    # 1. Product types (by name): attribute templates. Navigation fields of
    #    older archives (image, position, product order) are not applied to
    #    the type; an ADR-0010-era archive turns them into categories (1b).
    full = manifest.get("scope") != "pool"
    for row in manifest.get("product_types", []):
        obj, created = _upsert(ProductType, name=row["name"])
        obj.attribute_schema = row.get("attribute_schema", [])
        _set_translations(obj, row)
        obj.save()
        bump("created" if created else "updated", "product_types")

    # 1b. Categories (by path, parents first). A pool archive never changes
    #     the structure (position, product order, image) of an existing one.
    categories, writable = _import_categories(plan, full, media, bump)

    # 2. Products (by title) + their images and categories.
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
        if "categories" in row:
            listed = [
                categories[path]
                for path in (
                    tuple(p) for p in row["categories"] or [] if isinstance(p, list)
                )
                if path in categories
            ]
            if full:
                obj.categories.set(listed)
            else:
                # Pool archive: add only — keep the product's other local
                # categories (it may sit in categories this pool doesn't see).
                obj.categories.add(*listed)
        # Images: match by position so a re-import doesn't duplicate.
        for img in row.get("images", []):
            saved = media.save(img.get("file"))
            if not saved:
                continue
            pi, _ = ProductImage.objects.update_or_create(
                product=obj, position=img.get("position", 0),
                defaults={"image": saved},
            )

    # 2b. Products of converted categories + each category's product order.
    _import_category_products(plan, categories, writable)

    # 3. Pools (by pool_id).
    for row in manifest.get("resource_pools", []):
        obj, created = _upsert(ResourcePool, pool_id=row["pool_id"])
        for field in POOL_FIELDS:
            if field == "pool_id":
                continue
            setattr(obj, field, row.get(field, getattr(obj, field)))
        image = media.save(row.get("image"))
        if image:
            obj.image = image
        _set_translations(obj, row)
        _normalise_rich(
            obj,
            ("description", "description_de", "description_en",
             "directions", "directions_de", "directions_en"),
            plain_to_html,
        )
        media.rewrite(obj)
        obj.save()
        bump("created" if created else "updated", "resource_pools")

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

    # 6. Sections (by title) — top-level categories/sets by natural key.
    for row in manifest.get("sections", []):
        obj, created = _upsert(Section, title=row["title"])
        obj.position = row.get("position", obj.position)
        image = media.save(row.get("image"))
        if image:
            obj.image = image
        _set_translations(obj, row)
        obj.save()
        if "categories" in row:
            names = [n for n in row["categories"] or [] if isinstance(n, str)]
            order = [n for n in row.get("category_order") or [] if isinstance(n, str)]
        elif row["title"] in plan["sections"]:  # ADR-0010 archive: converted
            names = order = plan["sections"][row["title"]]
        else:
            names = order = None  # no category data: leave them as they are
        if names is not None:
            by_name = {}
            for name in names:
                category = _top_level_category(categories, name)
                if category is not None:
                    by_name[name] = category
            obj.categories.set(by_name.values())
            obj.category_order = list(
                dict.fromkeys(by_name[n].pk for n in order if n in by_name)
            )
        sets_ = list(_canon(ProductSet).filter(name__in=row.get("sets", [])))
        obj.sets.set(sets_)
        set_by_name = {s.name: s.id for s in sets_}
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
        media.rewrite(obj)
        obj.save()
        bump("created" if created else "updated", "pages")

    welcome = manifest.get("welcome_setting")
    if welcome:
        ws = WelcomeSetting.objects.first() or WelcomeSetting()
        ws.text = welcome.get("text", "")
        _normalise_rich(ws, ("text",), markdown_to_html)
        media.rewrite(ws)
        logo = media.save(welcome.get("logo"))
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
