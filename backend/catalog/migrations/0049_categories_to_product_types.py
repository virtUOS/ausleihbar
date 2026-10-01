# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Data migration (#20): product types replace categories.

Each section gets the product types of the (non-trashed) products in its former
(non-trashed) categories, in category order, then product order
(``catalog.structure.derive_section_types``). A category whose products all
share one type hands that type its image, description (per language) and
product order where the type has none yet. Type ``position`` follows the order
of first appearance across sections; types not reached follow, by name.
Finally all categories (live and trashed) are deleted; the next migration drops
the model.

Irreversible: rolling back raises ``IrreversibleError``. Make a ZIP export
before migrating (see INSTALL).
"""
from django.db import migrations

DESCRIPTION_FIELDS = ("description", "description_de", "description_en")


def _order_by_ids(objs, id_order, key):
    """Objects in ``id_order`` first, the rest by ``key``."""
    rank = {pk: i for i, pk in enumerate(id_order)}
    listed = sorted((o for o in objs if o.pk in rank), key=lambda o: rank[o.pk])
    rest = sorted((o for o in objs if o.pk not in rank), key=key)
    return listed + rest


def forwards(apps, schema_editor):
    from catalog.structure import derive_section_types

    Section = apps.get_model("catalog", "Section")
    Category = apps.get_model("catalog", "Category")
    ProductType = apps.get_model("catalog", "ProductType")
    Product = apps.get_model("catalog", "Product")

    types = {
        t.pk: t for t in ProductType._base_manager.filter(deleted_at__isnull=True)
    }
    live_products = list(
        Product._base_manager.filter(
            deleted_at__isnull=True, product_type_id__in=list(types)
        )
    )
    products_by_id = {p.pk: p for p in live_products}

    def category_data(category):
        products = [
            products_by_id[pid]
            for pid in category.products.values_list("id", flat=True)
            if pid in products_by_id
        ]
        ordered = _order_by_ids(products, category.product_order, key=lambda p: p.title)
        return {
            "key": category.pk,
            "products": [
                {"product_type": p.product_type_id, "title": p.title} for p in ordered
            ],
        }

    live_categories = list(
        Category._base_manager.filter(deleted_at__isnull=True).order_by("position", "title")
    )
    categories_by_id = {c.pk: c for c in live_categories}

    # Sections in position order (trashed ones too, so a restored section keeps
    # its content).
    sections = list(Section._base_manager.order_by("position", "title"))
    section_input = []
    category_sequence = []  # categories in first-reach order (for step 3)
    for section in sections:
        cats = [
            categories_by_id[cid]
            for cid in section.categories.values_list("id", flat=True)
            if cid in categories_by_id
        ]
        cats = _order_by_ids(cats, section.category_order, key=lambda c: (c.position, c.title))
        for c in cats:
            if c not in category_sequence:
                category_sequence.append(c)
        section_input.append(
            {"key": section.pk, "categories": [category_data(c) for c in cats]}
        )
    # Categories in no section still count for step 3.
    for c in live_categories:
        if c not in category_sequence:
            category_sequence.append(c)
    # Single-type detection for every live category (incl. ones in no section).
    _, category_types = derive_section_types(
        [{"key": None, "categories": [category_data(c) for c in category_sequence]}]
    )
    section_types, _ = derive_section_types(section_input)

    print()
    print("  Product types replace categories (#20):")

    # Step 2: section product types + order.
    for section in sections:
        type_ids = section_types.get(section.pk, [])
        section.product_types.set(type_ids)
        section.product_type_order = list(type_ids)
        section.save(update_fields=["product_type_order"])
        names = ", ".join(types[t].name for t in type_ids) or "-"
        trashed = " (trashed)" if section.deleted_at else ""
        print(f"    Section '{section.title}'{trashed}: {names}")

    # Step 3: copy category image / description / product order to its single type.
    copied_images, copied_descriptions, copied_orders = [], [], []
    for category in category_sequence:
        type_id = category_types.get(category.pk)
        if type_id is None:
            continue
        ptype = types[type_id]
        changed = []
        if not ptype.image and category.image:
            ptype.image = category.image.name
            changed.append("image")
            copied_images.append(f"{category.title} -> {ptype.name}")
        desc_langs = []
        for field in DESCRIPTION_FIELDS:
            if not getattr(ptype, field, None) and getattr(category, field, None):
                setattr(ptype, field, getattr(category, field))
                changed.append(field)
                desc_langs.append(field)
        if desc_langs:
            copied_descriptions.append(
                f"{category.title} -> {ptype.name} ({', '.join(desc_langs)})"
            )
        if not ptype.product_order:
            type_product_ids = {
                p.pk for p in live_products if p.product_type_id == type_id
            }
            order = [pid for pid in category.product_order if pid in type_product_ids]
            if order:
                ptype.product_order = order
                changed.append("product_order")
                copied_orders.append(f"{category.title} -> {ptype.name} ({len(order)})")
        if changed:
            ptype.save(update_fields=changed)

    # Step 4: type positions by first appearance, then the rest by name.
    ordered_ids = []
    for type_ids in section_types.values():
        for t in type_ids:
            if t not in ordered_ids:
                ordered_ids.append(t)
    all_types = list(ProductType._base_manager.all())
    reached = set(ordered_ids)
    rest = sorted((t for t in all_types if t.pk not in reached), key=lambda t: t.name)
    by_pk = {t.pk: t for t in all_types}
    for position, ptype in enumerate([by_pk[t] for t in ordered_ids] + rest):
        if ptype.position != position:
            ptype.position = position
            ptype.save(update_fields=["position"])

    # Step 5: summary.
    def report(label, items):
        print(f"    {label}: {len(items)}")
        for item in items:
            print(f"      {item}")

    report("Copied images", copied_images)
    report("Copied descriptions", copied_descriptions)
    report("Copied product orders", copied_orders)
    multi = [
        c.title for c in category_sequence if category_types.get(c.pk) is None
    ]
    report("Categories without a single type (nothing copied)", multi)
    print(
        f"    Type positions: {len(ordered_ids)} reached via sections, "
        f"{len(rest)} appended by name"
    )

    # Step 6 (data part): delete all categories, live and trashed.
    deleted = Category._base_manager.count()
    for section in sections:
        section.categories.clear()
    Category._base_manager.all().delete()
    print(f"    Deleted categories: {deleted}")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0048_product_types_structure_fields"),
    ]

    operations = [
        # reverse_code=None: rolling back raises IrreversibleError on purpose.
        migrations.RunPython(forwards, reverse_code=None),
    ]
