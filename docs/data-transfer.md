# Importing & exporting the data set

Admins can export the catalog data set as a portable ZIP archive and import
such an archive back, from **Admin → Standorte & Einstellungen →
Import / Export** (`/admin/data`). It is meant for backups, seeding a fresh
deployment, and moving structure/inventory between instances.

Unlike the one-way [leihs importer](leihs-import.md), this is a round-trip:
the same archive Ausleihbar writes is the one it reads.

## What is included

A ZIP with a natural-key `manifest.json` plus a `media/` folder holding the
referenced images and the welcome logo. Two scopes:

- **Whole system** — product types, products (incl. attributes & images),
  categories, sections, sets, all pools and resources, plus the CMS pages and
  the shop/welcome settings.
- **Single pool** — the pool, its resources, and just the structure those
  resources need (the referenced products, their product types and images).
  Categories/sections are **not** included, because they are system-wide.

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
/ `slug` for the rest. (A resource's `qr_code_id` is kept from the archive
unless it already belongs to a different unit, in which case a fresh one is
generated.)

Steps:

1. **Choose file** — select an archive exported as above.
2. **Dry run (preview)** first: it runs the whole import in a transaction, rolls
   it back, and reports what *would* change (created / updated counts per
   entity). Nothing is saved.
3. Review the summary, then **Import** for real.

The whole import runs in one transaction — if anything fails, nothing is
written. Re-importing the same archive is idempotent (everything shows up as
"updated", never duplicated).

## Notes & limits

- Export and import run **in memory**; very large media libraries may need a lot
  of RAM. (Streaming is a possible later improvement.)
- Re-importing an image whose file name is already taken in storage saves it
  under a new name rather than overwriting — no data loss, but it can leave
  duplicate media files over repeated imports.
- The feature is **admin-only** (`GET /api/manage/export/`,
  `POST /api/manage/import/`). The transfer logic lives in
  `backend/catalog/transfer.py`.
