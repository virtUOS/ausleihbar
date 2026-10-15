# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Sets get an image and a rich-text description (#93).

The description becomes sanitized rich HTML like the product details (#98,
migration 0057): plain text is HTML-escaped into paragraphs
(``plain_to_html``), a value that already looks like HTML is only
re-sanitized. All language columns and the bare column, trashed rows
included. Idempotent; the text conversion's reverse is a no-op.
"""
from django.db import migrations, models

FIELDS = ("description", "description_de", "description_en")


def forwards(apps, schema_editor):
    from catalog.richtext import clean_rich, looks_like_html, plain_to_html

    ProductSet = apps.get_model("catalog", "ProductSet")
    for product_set in ProductSet._base_manager.all().only("pk", *FIELDS).iterator():
        changed = []
        for field in FIELDS:
            value = getattr(product_set, field, None)
            if not value:
                continue
            new = clean_rich(value) if looks_like_html(value) else plain_to_html(value)
            if new != value:
                setattr(product_set, field, new)
                changed.append(field)
        if changed:
            product_set.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0063_productset_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="productset",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="sets/"),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
