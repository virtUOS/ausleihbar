"""Give existing bookings a reservation number and stop pending from expiring.

The slot-hold/expiry semantics moved from ``pending`` to the new ``cart``
status, so submitted (pending) reservations no longer expire — clear their
``expires_at``. Also backfill a reservation number for every existing booking.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    Booking = apps.get_model("lending", "Booking")
    for booking in Booking.objects.all():
        if not booking.code:
            booking.code = f"R-{booking.id:05d}"
            booking.save(update_fields=["code"])
    Booking.objects.filter(status="pending").update(expires_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ("lending", "0004_booking_note_alter_booking_status"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
