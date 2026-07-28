"""Split ResourcePool.location into a multi-line address plus a separate room.

Existing ``location`` values are preserved by renaming the column to
``address`` (then widening it to TextField); ``room`` is added empty.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_resource_defect_note"),
    ]

    operations = [
        migrations.RenameField(
            model_name="resourcepool",
            old_name="location",
            new_name="address",
        ),
        migrations.AlterField(
            model_name="resourcepool",
            name="address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="resourcepool",
            name="room",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
