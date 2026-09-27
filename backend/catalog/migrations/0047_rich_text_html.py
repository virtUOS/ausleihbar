# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""One-time data migration (#5): convert existing rich-text fields to the
sanitized HTML subset.

CMS page bodies and the welcome text were authored as Markdown; pool
description/directions were plain text. Both now render as rich HTML
(``catalog/richtext.py``). Content that already looks like HTML (e.g. a page
re-saved through the new editor before this migration ran) is left untouched.
Idempotent: a second run converts nothing further. Irreversible (the reverse
migration is a no-op) — there is no reliable way to turn sanitized HTML back
into the original Markdown/plain text.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    from catalog.richtext import looks_like_html, markdown_to_html, plain_to_html

    Page = apps.get_model("catalog", "Page")
    WelcomeSetting = apps.get_model("catalog", "WelcomeSetting")
    ResourcePool = apps.get_model("catalog", "ResourcePool")

    def convert(obj, fields, fn):
        changed = []
        for field in fields:
            value = getattr(obj, field, None)
            if value and not looks_like_html(value):
                setattr(obj, field, fn(value))
                changed.append(field)
        if changed:
            obj.save(update_fields=changed)

    for page in Page._base_manager.all():
        convert(page, ("body", "body_de", "body_en"), markdown_to_html)
    for welcome in WelcomeSetting._base_manager.all():
        convert(welcome, ("text",), markdown_to_html)
    for pool in ResourcePool._base_manager.all():
        convert(
            pool,
            (
                "description", "description_de", "description_en",
                "directions", "directions_de", "directions_en",
            ),
            plain_to_html,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0046_privacy_free_texts"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
