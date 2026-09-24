# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Backfill Booking.resource_pool and split legacy multi-pool bookings (#26).

Data migration — no schema change. See lending.splitting for the logic; it
takes model classes so it can run against these historical models here and
against the real models in tests.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    from lending.splitting import split_multi_pool_bookings

    split_multi_pool_bookings(
        apps.get_model("lending", "Booking"),
        apps.get_model("lending", "BookingItem"),
        apps.get_model("catalog", "ResourcePool"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('lending', '0013_booking_checkout_id_booking_confirmation_mailed_at_and_more'),
        ('catalog', '0045_notificationsetting_confirmation_send_time'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
