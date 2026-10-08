# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""One-time data migration (#98): product description ("Product details") and
return info become rich HTML; convert the existing plain text.

Plain text is HTML-escaped; blank lines separate paragraphs (``<p>``), single
newlines become ``<br>`` (``plain_to_html``). A value that already looks like
HTML (starts with a block tag the rich editor produces, ``looks_like_html``)
is only re-sanitized — as in 0047 — so plain text that merely starts with
``<`` (e.g. "<script>…") is escaped, not trusted. Empty values are skipped.
Idempotent (converted values look like HTML). All language columns and the
bare column, trashed rows included. Irreversible (reverse is a no-op).
"""
from django.db import migrations

FIELDS = (
    "description", "description_de", "description_en",
    "return_info", "return_info_de", "return_info_en",
)


def forwards(apps, schema_editor):
    from catalog.richtext import clean_rich, looks_like_html, plain_to_html

    Product = apps.get_model("catalog", "Product")
    converted = 0
    for product in Product._base_manager.all().only("pk", *FIELDS).iterator():
        changed = []
        for field in FIELDS:
            value = getattr(product, field, None)
            if not value:
                continue
            new = clean_rich(value) if looks_like_html(value) else plain_to_html(value)
            if new != value:
                setattr(product, field, new)
                changed.append(field)
        if changed:
            product.save(update_fields=changed)
            converted += 1
    if converted and schema_editor is not None:
        print(f"\n  Converted texts of {converted} product(s) to rich HTML.")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0056_remove_type_navigation"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
