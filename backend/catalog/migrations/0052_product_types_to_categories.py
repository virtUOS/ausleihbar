# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Data migration (#78, ADR-0011): categories return as shop navigation.

Every live product type that sits in at least one section (trashed sections
included, so a restored section keeps its content) becomes a top-level
category: name and description per language, the type's image file (same
stored path, no copy), ``position`` and ``product_order``; its live products
are assigned. Each section then gets the categories of its product types, with
``category_order`` mapped from ``product_type_order``. The shop looks the same
right after the update.

Idempotent: a live (not trashed) top-level category whose ``name`` equals
the type's name is reused (its fields are left alone); product and section links and order
entries are only added when missing. Prints a summary when there was anything
to convert (fresh installs and test databases stay quiet).

The rollback is a no-op: nothing is lost going forward (the product type
fields stay until the next schema step), and the schema rollback of 0051 drops
the categories.
"""
from django.db import migrations

TRANSLATED = tuple(
    f"{field}{suffix}"
    for field in ("name", "description")
    for suffix in ("", "_de", "_en")
)


def forwards(apps, schema_editor):
    Section = apps.get_model("catalog", "Section")
    ProductType = apps.get_model("catalog", "ProductType")
    Product = apps.get_model("catalog", "Product")
    Category = apps.get_model("catalog", "Category")

    sections = list(Section._base_manager.order_by("position", "title"))
    live_types = {
        t.pk: t
        for t in ProductType._base_manager.filter(
            deleted_at__isnull=True, sections__isnull=False
        )
        .distinct()
        .order_by("position", "name")
    }
    if not live_types:
        return

    print()
    print("  Categories from product types (#78):")

    existing = {
        c.name: c
        for c in Category._base_manager.filter(
            parent__isnull=True, deleted_at__isnull=True
        )
    }
    category_for_type = {}
    created, reused = [], []
    for ptype in live_types.values():
        category = existing.get(ptype.name)
        if category is None:
            category = Category(
                parent=None,
                image=ptype.image.name if ptype.image else None,
                position=ptype.position,
                product_order=list(ptype.product_order),
                **{field: getattr(ptype, field) for field in TRANSLATED},
            )
            category.save()
            existing[ptype.name] = category
            created.append(ptype.name)
        else:
            reused.append(ptype.name)
        category_for_type[ptype.pk] = category
        product_ids = list(
            Product._base_manager.filter(
                deleted_at__isnull=True, product_type_id=ptype.pk
            ).values_list("pk", flat=True)
        )
        if product_ids:
            category.products.add(*product_ids)

    for section in sections:
        type_ids = set(section.product_types.values_list("pk", flat=True))
        mapped = [
            category_for_type[t]
            for t in section.product_type_order
            if t in type_ids and t in category_for_type
        ]
        # Types in the section but not in its order sort after, like before.
        mapped += [
            category_for_type[t.pk]
            for t in live_types.values()
            if t.pk in type_ids and category_for_type[t.pk] not in mapped
        ]
        if not mapped:
            continue
        section.categories.add(*mapped)
        order = list(section.category_order)
        for category in mapped:
            if category.pk not in order:
                order.append(category.pk)
        if order != section.category_order:
            section.category_order = order
            section.save(update_fields=["category_order"])
        names = ", ".join(c.name for c in mapped)
        trashed = " (trashed)" if section.deleted_at else ""
        print(f"    Section '{section.title}'{trashed}: {names}")

    print(f"    Created categories: {len(created)}")
    if reused:
        print(f"    Already present (left unchanged): {', '.join(reused)}")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0051_category"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
