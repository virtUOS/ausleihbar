# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Sets get an image gallery and shop categories (#93 follow-up).

``ProductSetImage`` replaces the single ``ProductSet.image``: an existing
image becomes the set's first gallery image (position 0, the cover). The old
column is dropped in 0067 — a separate migration, so the inserted gallery rows
don't leave pending FK trigger events on the table being altered. The reverse
copies the cover back into ``image``.
"""
import django.db.models.deletion
from django.db import migrations, models


def image_to_gallery(apps, schema_editor):
    ProductSet = apps.get_model("catalog", "ProductSet")
    ProductSetImage = apps.get_model("catalog", "ProductSetImage")
    rows = [
        ProductSetImage(product_set_id=pk, image=image, position=0)
        for pk, image in ProductSet._base_manager.exclude(image="")
        .exclude(image__isnull=True)
        .values_list("pk", "image")
    ]
    ProductSetImage.objects.bulk_create(rows)


def gallery_to_image(apps, schema_editor):
    ProductSet = apps.get_model("catalog", "ProductSet")
    ProductSetImage = apps.get_model("catalog", "ProductSetImage")
    covers = {}
    for set_id, image in ProductSetImage.objects.order_by(
        "product_set_id", "position", "id"
    ).values_list("product_set_id", "image"):
        covers.setdefault(set_id, image)
    for set_id, image in covers.items():
        ProductSet._base_manager.filter(pk=set_id).update(image=image)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0065_productsetitem_quantity_check"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductSetImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image", models.ImageField(upload_to="sets/")),
                ("position", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "product_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.productset",
                    ),
                ),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddField(
            model_name="productset",
            name="categories",
            field=models.ManyToManyField(
                blank=True, related_name="product_sets", to="catalog.category"
            ),
        ),
        migrations.RunPython(image_to_gallery, gallery_to_image),
    ]
