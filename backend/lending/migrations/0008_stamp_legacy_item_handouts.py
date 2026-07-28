"""Stamp item handout/return timestamps for pre-per-item bookings.

Before handout/return moved to the item level, a booking's status was set
without recording per-item ``handed_out_at`` / ``returned_at``. Backfill those
so the lending desk treats such bookings consistently (a handed-out booking's
items count as out; a returned booking's items as returned).
"""
from django.db import migrations


def stamp(apps, schema_editor):
    Booking = apps.get_model("lending", "Booking")
    BookingItem = apps.get_model("lending", "BookingItem")

    for booking in Booking.objects.filter(status="handed_out"):
        BookingItem.objects.filter(
            booking=booking, handed_out_at__isnull=True, returned_at__isnull=True
        ).update(handed_out_at=booking.updated_at)

    for booking in Booking.objects.filter(status="returned"):
        items = BookingItem.objects.filter(booking=booking, returned_at__isnull=True)
        items.filter(handed_out_at__isnull=True).update(handed_out_at=booking.updated_at)
        BookingItem.objects.filter(booking=booking, returned_at__isnull=True).update(
            returned_at=booking.updated_at
        )


class Migration(migrations.Migration):

    dependencies = [
        ("lending", "0007_booking_overdue_reminded_at"),
    ]

    operations = [
        migrations.RunPython(stamp, migrations.RunPython.noop),
    ]
