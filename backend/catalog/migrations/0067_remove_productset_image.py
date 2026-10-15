# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Drop the single set image — moved into the gallery by 0066."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0066_productset_gallery_categories"),
    ]

    operations = [
        migrations.RemoveField(model_name="productset", name="image"),
    ]
