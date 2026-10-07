# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Data step before 0055 (#78): make live sibling category names unique.

0055 adds unique constraints on the live (not trashed) categories' names per
parent and among the roots — for the bare ``name`` column and, added by
django-modeltranslation, for ``name_de``/``name_en`` too. Existing
duplicates (the manage API allowed them until now; 0052 maps unique product
type names, so it creates none) are renamed: the first per group (by
position, then id) keeps its name, the others get " (2)", " (3)", … —
skipping values already taken. Columns of a row holding the same duplicated
value are renamed together. Empty translations become NULL first (two empty
strings would collide; NULLs don't). Prints every rename; stays quiet when
there is nothing to do. Trashed rows are not renamed.
"""
from collections import defaultdict

from django.db import migrations

MAX_LENGTH = 255
COLUMNS = ("name", "name_de", "name_en")


def forwards(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for column in COLUMNS[1:]:
        Category._base_manager.filter(**{column: ""}).update(**{column: None})

    live = list(
        Category._base_manager.filter(deleted_at__isnull=True).order_by("position", "pk")
    )
    every = defaultdict(set)  # column -> {(parent_id, value)} of all live rows
    for category in live:
        for column in COLUMNS:
            value = getattr(category, column)
            if value:
                every[column].add((category.parent_id, value))
    seen = defaultdict(set)
    renamed = []
    for category in live:
        parent_id = category.parent_id
        duplicated = []
        for column in COLUMNS:
            value = getattr(category, column)
            if not value:
                continue
            if (parent_id, value) in seen[column] and value not in duplicated:
                duplicated.append(value)
        fields = []
        for value in duplicated:
            columns = [c for c in COLUMNS if getattr(category, c) == value]
            number = 2
            while True:
                suffix = f" ({number})"
                new = value[: MAX_LENGTH - len(suffix)] + suffix
                if all((parent_id, new) not in every[c] for c in columns):
                    break
                number += 1
            for column in columns:
                setattr(category, column, new)
                every[column].add((parent_id, new))
                fields.append(column)
            renamed.append((category.pk, value, new))
        for column in COLUMNS:
            value = getattr(category, column)
            if value:
                seen[column].add((parent_id, value))
        if fields:
            category.save(update_fields=fields)
    if renamed:
        print()
        print("  Duplicate category names renamed (#78):")
        for pk, old, new in renamed:
            print(f"    #{pk}: '{old}' -> '{new}'")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0053_section_categories_top_level"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
