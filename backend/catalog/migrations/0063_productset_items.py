# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Sets get per-product quantities and an order (#93).

``ProductSet.products`` becomes ``ManyToManyField(through="ProductSetItem")``
on the *existing* auto-created table, so no row is copied or lost:

1. State only: declare ``ProductSetItem`` on ``catalog_productset_products``
   (column ``productset_id`` kept via ``db_column``) and point the M2M at it.
2. Database + state: add ``quantity`` (default 1) and ``position``.
3. Backfill ``position`` per set in the current through-row id order.
4. Rename the table/column to the model's defaults
   (``catalog_productsetitem.product_set_id``).

Every step is reversible; going back drops quantity/position and restores
the original table and column names (the rows survive).
"""
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def backfill_positions(apps, schema_editor):
    Item = apps.get_model("catalog", "ProductSetItem")
    counters = {}
    changed = []
    for item in Item.objects.order_by("product_set_id", "id"):
        position = counters.get(item.product_set_id, 0)
        counters[item.product_set_id] = position + 1
        if item.position != position:
            item.position = position
            changed.append(item)
    Item.objects.bulk_update(changed, ["position"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0062_pickup_reminder_send_time"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ProductSetItem",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True, primary_key=True,
                                serialize=False, verbose_name="ID",
                            ),
                        ),
                        (
                            "product_set",
                            models.ForeignKey(
                                db_column="productset_id",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="items",
                                to="catalog.productset",
                            ),
                        ),
                        (
                            "product",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="set_items",
                                to="catalog.product",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "catalog_productset_products",
                        "unique_together": {("product_set", "product")},
                    },
                ),
                migrations.AlterField(
                    model_name="productset",
                    name="products",
                    field=models.ManyToManyField(
                        blank=True, related_name="product_sets",
                        through="catalog.ProductSetItem", to="catalog.product",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name="productsetitem",
            name="quantity",
            field=models.PositiveIntegerField(
                default=1, validators=[django.core.validators.MinValueValidator(1)]
            ),
        ),
        migrations.AddField(
            model_name="productsetitem",
            name="position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_positions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="productsetitem",
            options={"ordering": ["position", "id"]},
        ),
        migrations.AlterModelTable(name="productsetitem", table=None),
        migrations.AlterField(
            model_name="productsetitem",
            name="product_set",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="items",
                to="catalog.productset",
            ),
        ),
    ]
