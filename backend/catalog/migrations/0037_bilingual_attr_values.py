# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)
from django.conf import settings
from django.db import migrations

_TEXT_TYPES = {"short_text", "long_text"}


def forwards(apps, schema_editor):
    """Wrap existing free-text attribute values ("x") into {de,en} dicts
    ({"de": "x", "en": ""}); leave non-text values and existing dicts alone."""
    Product = apps.get_model("catalog", "Product")
    langs = [code for code, _ in settings.LANGUAGES]
    default = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    for product in Product.objects.select_related("product_type").iterator():
        schema = product.product_type.attribute_schema or []
        attrs = product.attributes or {}
        changed = False
        for attr in schema:
            key = attr.get("key")
            if attr.get("type") not in _TEXT_TYPES or key not in attrs:
                continue
            value = attrs[key]
            if isinstance(value, dict):
                continue
            wrapped = {lang: "" for lang in langs}
            wrapped[default] = str(value or "").strip()
            attrs[key] = wrapped
            changed = True
        if changed:
            product.attributes = attrs
            product.save(update_fields=["attributes"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0036_favorite")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
