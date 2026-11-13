# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.db import migrations, models


def unflag_fixed_special(apps, schema_editor):
    """A fixed desk may no longer be a special place (its individual
    statistics would reveal the owner's absence days): keep the owner,
    drop the flag."""
    Place = apps.get_model("desksharing", "Place")
    Place.objects.filter(is_special=True, fixed_owner__isnull=False).update(is_special=False)


class Migration(migrations.Migration):

    dependencies = [
        ("desksharing", "0013_remove_floor_template_fields"),
    ]

    operations = [
        migrations.RunPython(unflag_fixed_special, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="place",
            constraint=models.CheckConstraint(
                condition=models.Q(("is_special", False), ("fixed_owner__isnull", True), _connector="OR"),
                name="desk_fixed_place_not_special",
            ),
        ),
    ]
