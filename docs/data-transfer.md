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
(pool descriptions/directions, CMS pages, welcome text) are part of the
archive too; a single-pool export carries only the rich images of the exported
**pool's** description and directions. Two scopes:

- **Whole system** — product types (incl. image, position and the product
  order within the type), products (incl. attributes & images), sections
  (with their product types and sets, each in the section's order), sets, all
  pools and resources, plus the CMS pages and the shop/welcome settings.
- **Single pool** — the pool, its resources, and just the structure those
  resources need (the referenced products, their product types and images).
  Sections, type positions and the product order within a type are **not**
  included, because they are system-wide; importing a pool archive never
  changes them for a product type that already exists, and it only fills in
  that type's image if the type has none yet (an existing image is kept). A
  type the pool import creates is placed after all existing types.

Relations are written as natural keys: a section lists its `product_types`
and `product_type_order` by type name, a type's `product_order` lists product
titles.

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

Natural keys: pool `pool_id`, resource `inventory_number`, and `name` / `title`
/ `slug` for the rest. (A resource's `qr_code_id` is taken from the archive
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

## Archives from before product types replaced categories

Archives written before #20 contain a `categories` list and sections that list
`categories` instead of `product_types`. They can still be imported; the
categories are converted with the same rules as the upgrade migration:

- Each section gets the product types of the products in its categories — in
  the section's category order (then position/title), each category's
  products in its product order (then title), without duplicates.
- A category whose products all share one product type hands that type its
  image, its description (per language) and its product order — only where
  the type has none yet (after the archive's own type data was applied). The
  first such category, in section order, wins.
- The archive's product types are positioned by first appearance across the
  sections (sections by position), the rest after them by name.

Re-importing such an old archive re-derives this section structure (and the
type positions) each time, replacing the sections' current product types. No
categories are created; the import summary reports them under
`converted` (`{"converted": {"categories": N}}`).

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
- The feature is **admin-only** (`GET /api/manage/export/`,
  `POST /api/manage/import/`). The transfer logic lives in
  `backend/catalog/transfer.py`.
