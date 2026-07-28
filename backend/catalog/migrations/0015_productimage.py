# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import django.db.models.deletion
from django.db import migrations, models


def move_product_image_to_gallery(apps, schema_editor):
    """Carry each product's single image over into the new gallery (position 0).

    The file itself isn't moved — the new row references the same stored name.
    """
    Product = apps.get_model("catalog", "Product")
    ProductImage = apps.get_model("catalog", "ProductImage")
    for product in Product.objects.exclude(image="").exclude(image=None):
        ProductImage.objects.create(
            product=product, image=product.image.name, position=0
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0014_welcomesetting"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image", models.ImageField(upload_to="products/")),
                ("position", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.product",
                    ),
                ),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.RunPython(move_product_image_to_gallery, noop),
        migrations.RemoveField(model_name="product", name="image"),
    ]
