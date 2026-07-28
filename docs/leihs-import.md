# Importing inventory from leihs

A one-way importer brings catalog **inventory** from a [leihs](https://github.com/leihs/leihs)
CSV export into Ausleihbar. It maps leihs **models → Products** and
**items → Resources**. The mapping is intentionally lossy — leihs and Ausleihbar
do not align 1:1.

## Personal data: never imported

The importer reads only a fixed **whitelist of inventory columns**. Any
personal-data columns a leihs export may still contain (current borrower,
delegation, responsible person, …) are ignored and never written. Still, treat
the export file as sensitive:

- Export **inventory only** (models/items), not contracts/orders.
- The leihs item export may include a *"borrowed by"* column — strip it before
  the file leaves leihs if possible.
- leihs CSVs are git-ignored (`docs/*leihs*.csv`); **do not commit them.**

## Steps

1. In the leihs admin → **Inventory**, export the item list as CSV (semicolon
   separated, UTF-8). It already contains the model columns (`Produkt`,
   `Hersteller`, `Beschreibung`, …) per item.
2. Copy the file where the backend container can read it, e.g.:
   ```bash
   docker compose cp inventory.csv backend:/tmp/leihs.csv
   ```
3. **Dry run** first (parses + reports, writes nothing):
   ```bash
   docker compose exec backend python manage.py import_leihs /tmp/leihs.csv \
       --pool DigiLab --dry-run
   ```
4. Review the report, then run for real (drop `--dry-run`).

Re-running is **idempotent**: resources are matched by inventory number and
products by title, so a second run updates instead of duplicating.

### Options

| Option            | Default        | Meaning |
|-------------------|----------------|---------|
| `--pool`          | `DigiLab`      | Target ResourcePool (created if missing). |
| `--product-type`  | `leihs-Import` | Target ProductType (created if missing; holds the `Hersteller` attribute). |
| `--lending-type`  | `days`         | `days` or `hours` for imported products. |
| `--delimiter`     | `;`            | CSV delimiter. |
| `--dry-run`       | off            | Parse + report only; roll back. |

## Field mapping

| leihs column | Ausleihbar |
|---|---|
| `Produkt` (+ `Version`) | `Product.title` |
| `Beschreibung` (+ `Technische Details`, `Interne Beschreibung`) | `Product.description` |
| `Hersteller` | `Product.attributes.hersteller` |
| `Inventarcode` | `Resource.inventory_number` (+ generated `qr_code_id` `leihs-<code>`) |
| `Seriennummer` | `Resource.serial_number` |
| `Gebäude` · `Raum` · `Gestell` | `Resource.storage_location` |
| `Rechnungsdatum` | `Resource.procurement_date` |
| `Garantieablaufdatum` | `Resource.warranty_end` |
| `Anschaffungswert` | `Resource.value` |
| `Lieferant` | `Resource.procuring_institution` |
| `Ausmusterung` set → `retired`; `Ausleihbar=false` → `blocked`; else `available` | `Resource.status` |

**Not imported** (no equivalent in Ausleihbar's model, or empty in typical
exports): `Kategorien`, `Eigenschaften`, `Zubehör`, `Ergänzende Modelle`,
`Name`, `Notiz`, `Zustand`/`Vollständigkeit`, MAC/IMEI, and all personal columns.

Categories/sections and pool structure are refined manually after the import.
