# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Backfill the German translation columns from the original field values.

Existing catalog content was entered in German before content translation
(issue #6) existed. modeltranslation adds ``*_de`` / ``*_en`` columns but leaves
them NULL; this copies each original value into its ``*_de`` column so the
default language is populated in every environment via ``migrate`` (not only
where ``update_translation_fields`` was run by hand). Reverse is a no-op — the
original columns are untouched.
"""

from django.db import migrations

# Model name → translated field names (must match catalog/translation.py).
TRANSLATED_FIELDS = {
    "ProductType": ("name", "description"),
    "Product": ("title", "description", "return_info"),
    "ResourcePool": ("name", "description", "address", "room", "directions"),
    "Category": ("title", "description"),
    "Section": ("title", "description"),
    "ProductSet": ("name", "description"),
    "Page": ("title", "body"),
}


def backfill_de(apps, schema_editor):
    for model_name, fields in TRANSLATED_FIELDS.items():
        model = apps.get_model("catalog", model_name)
        for obj in model.objects.all().iterator():
            changed = False
            for field in fields:
                if getattr(obj, f"{field}_de") in (None, ""):
                    setattr(obj, f"{field}_de", getattr(obj, field))
                    changed = True
            if changed:
                obj.save(update_fields=[f"{f}_de" for f in fields])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0020_category_description_de_category_description_en_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_de, migrations.RunPython.noop),
    ]
