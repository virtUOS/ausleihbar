# Floors and equipment lose their department; name uniqueness.

import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("desksharing", "0021_places_ownership_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name='feature',
            name='pool',
        ),
        migrations.RemoveField(
            model_name='floor',
            name='pool',
        ),
        migrations.AddConstraint(
            model_name='feature',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='desk_feature_name_unique'),
        ),
        migrations.AddConstraint(
            model_name='floor',
            constraint=models.UniqueConstraint(models.F('building'), django.db.models.functions.text.Lower('name'), name='desk_floor_name_per_building'),
        ),
        migrations.AddConstraint(
            model_name='room',
            constraint=models.UniqueConstraint(models.F('floor'), django.db.models.functions.text.Lower('name'), name='desk_room_name_per_floor'),
        ),
    ]
