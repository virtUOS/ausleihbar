# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Import inventory from a leihs CSV export into the Ausleihbar catalog.

Maps leihs **models → Product** and **items → Resource**. Inventory only: the
command reads a fixed WHITELIST of columns and ignores everything else, so any
personal-data columns a leihs export may still contain (current borrower,
delegation, …) are never touched.

The mapping is lossy by design (leihs and Ausleihbar don't align 1:1). Run with
--dry-run first to see the report without writing anything.

Usage:
    python manage.py import_leihs <file.csv> --pool DigiLab [--dry-run]
"""
import csv
import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Product, ProductType, Resource, ResourcePool

# Only these leihs columns are read. Anything else in the file (incl. any
# leftover personal columns) is ignored entirely.
COL = {
    "title": "Produkt",
    "version": "Version",
    "manufacturer": "Hersteller",
    "description": "Beschreibung",
    "tech": "Technische Details",
    "internal": "Interne Beschreibung",
    "inventory_code": "Inventarcode",
    "serial": "Seriennummer",
    "retired": "Ausmusterung",
    "lendable": "Ausleihbar",
    "building": "Gebäude",
    "room": "Raum",
    "rack": "Gestell",
    "invoice_date": "Rechnungsdatum",
    "warranty_end": "Garantieablaufdatum",
    "value": "Anschaffungswert",
    "supplier": "Lieferant",
}

# Columns that must never be imported (defence in depth: if a raw, unsanitised
# export is passed, we still won't read these).
PERSONAL_COLUMNS = {
    "Ausleihende/r Vorname", "Ausleihende/r Nachname", "Ausleihende/r Personal ID",
    "Delegation Ausleihende/r Vorname", "Delegation Ausleihende/r Nachname",
    "Delegation Ausleihende/r Personal ID", "ausgeliehen bis",
    "Verantwortliche Person", "Benutzer/Verwendung", "Besitzer",
}


def _val(row, key):
    return (row.get(COL[key]) or "").strip()


def _parse_date(s):
    try:
        return datetime.date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def _parse_decimal(s):
    try:
        return Decimal(s.replace(",", ".")) if s else None
    except (InvalidOperation, AttributeError):
        return None


class Command(BaseCommand):
    help = "Import a leihs inventory CSV (models→products, items→resources)."

    def add_arguments(self, parser):
        parser.add_argument("csv_file")
        parser.add_argument(
            "--pool", default="DigiLab",
            help="Target ResourcePool name (created if missing). Default: DigiLab.",
        )
        parser.add_argument(
            "--product-type", default="leihs-Import",
            help="Target ProductType name (created if missing).",
        )
        parser.add_argument(
            "--lending-type", default="days", choices=["days", "hours"],
            help="Lending type for imported products. Default: days.",
        )
        parser.add_argument("--delimiter", default=";")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and report, but roll back without writing.",
        )

    def handle(self, *args, **opts):
        try:
            fh = open(opts["csv_file"], encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise CommandError(f"Cannot open {opts['csv_file']}: {exc}")
        with fh:
            rows = list(csv.DictReader(fh, delimiter=opts["delimiter"]))
        if not rows:
            raise CommandError("CSV has no data rows.")

        present_personal = PERSONAL_COLUMNS & set(rows[0].keys())
        if present_personal:
            self.stdout.write(self.style.WARNING(
                f"Note: {len(present_personal)} personal-data column(s) present in the "
                f"file are being ignored (not imported). Consider sanitising the export."
            ))

        try:
            with transaction.atomic():
                stats = self._import(rows, opts)
                if opts["dry_run"]:
                    transaction.set_rollback(True)
        except Exception as exc:  # surface row issues cleanly
            raise CommandError(str(exc))

        mode = "DRY-RUN (nothing written)" if opts["dry_run"] else "IMPORT complete"
        self.stdout.write(self.style.SUCCESS(
            f"\n{mode}: "
            f"{stats['products']} products, {stats['resources']} resources "
            f"(available {stats['available']}, blocked {stats['blocked']}, "
            f"retired {stats['retired']}); {stats['skipped']} rows skipped."
        ))

    def _import(self, rows, opts):
        pool, _ = ResourcePool.objects.get_or_create(
            name=opts["pool"],
            defaults={"pool_id": slugify(opts["pool"])[:64] or "imported"},
        )
        ptype, _ = ProductType.objects.get_or_create(
            name=opts["product_type"],
            defaults={"attribute_schema": [{
                "key": "hersteller", "label": "Hersteller", "type": "short_text",
                "visible": True, "required": False, "default": "",
            }]},
        )

        stats = {"products": 0, "resources": 0, "skipped": 0,
                 "available": 0, "blocked": 0, "retired": 0}
        product_cache = {}

        for row in rows:
            code = _val(row, "inventory_code")
            if not code:
                stats["skipped"] += 1
                continue

            title = _val(row, "title") or f"Unbenannt ({code})"
            version = _val(row, "version")
            if version:
                title = f"{title} {version}"

            if title not in product_cache:
                desc = "\n\n".join(
                    p for p in (_val(row, "description"), _val(row, "tech"),
                                _val(row, "internal")) if p
                )
                product, created = Product.objects.get_or_create(
                    title=title, product_type=ptype,
                    defaults={"lending_type": opts["lending_type"]},
                )
                product.description = desc
                product.attributes = {"hersteller": _val(row, "manufacturer")}
                product.save()
                product_cache[title] = product
                if created:
                    stats["products"] += 1

            # Status: retired wins, then non-lendable → blocked, else available.
            if _val(row, "retired"):
                status = Resource.Status.RETIRED
            elif _val(row, "lendable").lower() in ("false", "0", "nein", "no"):
                status = Resource.Status.BLOCKED
            else:
                status = Resource.Status.AVAILABLE
            stats[status] += 1

            location = " · ".join(
                p for p in (_val(row, "building"), _val(row, "room"),
                            _val(row, "rack")) if p
            )

            _, created = Resource.objects.update_or_create(
                inventory_number=code,
                defaults={
                    "product": product_cache[title],
                    "resource_pool": pool,
                    "status": status,
                    "qr_code_id": f"leihs-{code}",
                    "serial_number": _val(row, "serial"),
                    "storage_location": location,
                    "procurement_date": _parse_date(_val(row, "invoice_date")),
                    "warranty_end": _parse_date(_val(row, "warranty_end")),
                    "value": _parse_decimal(_val(row, "value")),
                    "procuring_institution": _val(row, "supplier"),
                },
            )
            if created:
                stats["resources"] += 1

        return stats
