# Importing & exporting the data set

Admins can export the catalog data set as a portable ZIP archive and import
such an archive back, from **Admin → Standorte & Einstellungen →
Import / Export** (`/admin/data`). It is meant for backups, seeding a fresh
deployment, and moving structure/inventory between instances.

Unlike the one-way [leihs importer](leihs-import.md), this is a round-trip:
the same archive Ausleihbar writes is the one it reads.

## What is included

A ZIP with a natural-key `manifest.json` plus a `media/` folder holding the
referenced images and the welcome logo. Images embedded in rich text
(pool descriptions/directions, product details and return info, CMS pages,
welcome text) are part of the archive too; a single-pool export carries only
the rich images of the exported **pool's** description and directions and of
its products. Plain-text product details/return info from an older archive are
converted to HTML on import. Two scopes:

- **Whole system** — product types (attribute templates), categories (the
  tree, incl. image, position among siblings and the product order within the
  category), products (incl. attributes, images and categories), sections
  (with their top-level categories and sets, each in the section's order),
  sets, all pools and resources, plus the CMS pages and the shop/welcome
  settings. Trashed categories, and categories below a trashed one, are left
  out.
- **Single pool** — the pool, its resources, and just the structure those
  resources need (the referenced products, their product types, their
  categories **plus all ancestors** of those, and images). Sections, category
  positions and the product order within a category are **not** included,
  because they are system-wide; importing a pool archive never changes them
  for a category that already exists, and it only fills in that category's
  image if it has none yet (an existing image is kept). A category the pool
  import creates is placed after its existing siblings.

Relations are written as natural keys: a section lists its `categories` and
`category_order` by name (sections hold top-level categories only), a
product lists its `categories` as paths, a category's `product_order` lists
product titles.

### Categories in the manifest

A category's natural key is its **path**: the list of names from the root
down to the category, e.g. `["Kameras", "Video"]`. The names are the
default-language names (the bare `name` column, i.e. `name_de`), at most
255 characters each. Root names are unique among the live roots and sibling
names among the live children of a parent — the database enforces this
(migration 0055; 0054 renamed existing duplicates to "Name (2)", …), and the
import rejects an archive that breaks it.
Rows are written parents first, in tree order:

```json
"categories": [
  {"path": ["Kameras"], "image": "media/categories/kameras.png",
   "position": 0, "product_order": ["Sony Alpha 7 IV", "GoPro"],
   "name_de": "Kameras", "name_en": "Cameras",
   "description_de": "…", "description_en": "…"},
  {"path": ["Kameras", "Video"], "image": null, "position": 0,
   "product_order": [], "name_de": "Video", "name_en": "Video",
   "description_de": "", "description_en": ""}
],
"products": [{"title": "GoPro", "categories": [["Kameras"], ["Kameras", "Video"]], …}],
"sections": [{"title": "Aufnahmetechnik", "categories": ["Kameras"],
              "category_order": ["Kameras"], …}]
```

Product-type schemas are applied from the archive as-is: importing one never
seeds device values when a property's scope differs from the existing type (the
product-to-device value copy only happens when editing a type in the UI).

`position` and `product_order` are missing from pool archives. On import a
category is matched by its path (parent first, then the name among that
parent's children; a live row wins over a trashed one, which is restored);
its last path element becomes its default-language name. A category is
never moved: a category with the same name elsewhere in the tree is a
different one. A full archive replaces a product's categories by those listed
in its row; a pool archive only **adds** them (the product keeps its other
categories) and never changes an existing category's name or description. The import refuses (nothing is written) an archive with a malformed,
too long or duplicate path or a row whose parent row is missing; any other
malformed or conflicting data also aborts the import with an error instead of
writing half of it. A section entry that
names no top-level category is skipped.

Translatable text is carried in both languages (`*_de` / `*_en`).

## Never included

- **Personal & operational data:** users, bookings, blocks (Sperrtage),
  strikes — none of it is exported.
- **The per-pool GitLab token.** It is an encrypted, instance-bound secret (see
  [INSTALL §4.7](INSTALL.md)); it would not decrypt elsewhere. After importing a
  pool that used the defect→GitLab integration, re-enter its token under
  **Defekte → GitLab verbinden**.

Treat export archives as sensitive anyway — they contain your full catalogue
and contact details. Store them like a database backup.

## Export

1. Open **Import / Export**.
2. **Export whole system** downloads `ausleihbar-export.zip`.
3. To export one pool, pick it from the dropdown and **Export pool** →
   `ausleihbar-pool-<pool_id>.zip`.

## Import (merge)

Import is a **merge / upsert**, never a wipe: existing rows are matched by their
natural key and updated, missing ones are created. Nothing in the target that
is absent from the archive is deleted.

Resources also carry their `attributes` (values of the product type's
device-scope properties, #106; a row without them yields none, keys not
device-scope in the product's type are dropped); a product's `attributes`
never carry device-scope keys.

Natural keys: pool `pool_id`, resource `inventory_number`, category path (see
above), and `name` / `title` / `slug` for the rest. (A resource's `qr_code_id` is taken from the archive
when it is free. IDs are applied row by row; a value still held by another unit at that moment is skipped (the unit keeps its ID). A blank or clashing value never replaces an existing unit's
stored ID — printed labels depend on it; a new unit without a usable ID gets
`QR-<inventory number>`, as in the inventory API.)

Steps:

1. **Choose file** — select an archive exported as above.
2. **Dry run (preview)** first: it runs the whole import in a transaction, rolls
   it back, and reports what *would* change (created / updated counts per
   entity). Nothing is saved, and no media files are written to storage.
3. Review the summary, then **Import** for real.

The whole import runs in one transaction — if anything fails, nothing is
written. Re-importing the same archive is idempotent (everything shows up as
"updated", never duplicated).

## Older archives

Archives from earlier versions are converted on import; the import summary
reports the conversion under `converted`, and the resulting categories are
counted as created/updated `categories` like any others.

**Before #20 (flat categories).** These archives contain a `categories` list
whose rows have a `title` (no `path`), and sections that list `categories`.
Each category becomes a **top-level** category with its translations,
description, image, position, products (`products`) and product order;
sections get their categories and category order directly. Product types are
not touched. Summary: `{"converted": {"categories": N}}`.

**ADR-0010 era (product types as navigation, #20 until #78).** These archives
have no `categories`; sections list `product_types` and
`product_type_order`, and types carry an image, a position and a product
order. They are converted with the rules of the upgrade migration (0052):

- every product type that sits in at least one of the archive's sections
  becomes a top-level category with the type's name and description (per
  language), image, position and product order; the archive's products of
  that type are added to it;
- each section gets the categories of its types, in the section's type
  order; types missing from that order follow in type position order.

Unlike the migration, an existing top-level category with the same name is
**updated** from the archive (import semantics: texts, image, product order)
— but, like the migration, it **keeps its position**; only a newly created
category takes the type's position. The
types' own image, position and product order are not applied (product types
are attribute templates now). A pool archive of that era has no sections, so
nothing is converted and its products get no categories. Summary:
`{"converted": {"product_types": N}}`.

## Notes & limits

- Export and import run **in memory**; very large media libraries may need a lot
  of RAM. (Streaming is a possible later improvement.)
- Media are de-duplicated by SHA-256, compared only with the file at the
  **same target name**: if that name already exists with identical content, the
  file is reused (not written again). So a re-import of the same archive into
  the same instance doesn't create new files. If the name is taken by
  *different* content, a renamed copy is stored and the rich-text HTML that
  references it is rewritten to the new name. (Identical content under another
  name is not detected.)
- The `media` count in the import summary is the number of files written (in a
  dry run: that would be written); reused files are not counted.
- Archive media names that are unsafe (absolute paths, `..` traversal, `.`,
  bare folder names such as `media/products`) are ignored, as are files that
  can't be written to storage.
- Rich-image references are resolved like the browser does (HTML entities,
  percent-escapes, `.`/`..` segments, doubled slashes), so e.g.
  `/media/./rich/a.png` and `/media/rich/%61.png` both count as `rich/a.png`
  (export, import rewrite and `cleanup_rich_images` share this logic).
- Uploaded rich images are re-encoded without EXIF/GPS/XMP/comments (the ICC
  colour profile is kept); an animated PNG (APNG) is stored as its first frame
  only, animated GIF/WebP keep all frames.
- Rich images in an imported archive (`media/rich/…`) go through the **same
  validation and re-encode** as an upload (the size is checked from the ZIP
  header *before* decompression) (`catalog/rich_images.py`
  `process_rich_image`: format allowlist, 5 MB / pixel / frame limits, metadata
  stripped), so a hand-edited archive can't smuggle in EXIF/GPS or oversized
  images. The re-encoded file is stored under the detected format's extension
  (e.g. PNG content named `x.jpg` becomes `rich/x.png`; `.jpeg` stays) and the
  HTML is rewritten accordingly. De-dup reuses an existing file that equals
  either the archive bytes or the re-encoded ones. A file that is no valid
  image is skipped — the import continues, its references are left as they
  are, and its name is listed under `skipped_media` in the summary (also in a
  dry run, which processes the images but writes nothing).
- The feature is **admin-only** (`GET /api/manage/export/`,
  `POST /api/manage/import/`). The transfer logic lives in
  `backend/catalog/transfer.py`.
