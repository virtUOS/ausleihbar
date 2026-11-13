# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.db import migrations, models
from django.db.models import F


def backfill(apps, schema_editor):
    """Existing reservations of a fixed owner on their own place."""
    Reservation = apps.get_model("desksharing", "Reservation")
    pks = Reservation.objects.filter(
        holder__isnull=False, holder_id=F("place__fixed_owner_id")
    ).values("pk")
    Reservation.objects.filter(pk__in=pks).update(owner_use=True)


class Migration(migrations.Migration):

    dependencies = [
        ("desksharing", "0008_desk_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="owner_use",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
