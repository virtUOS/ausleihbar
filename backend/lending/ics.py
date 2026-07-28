# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Build an iCalendar (.ics) entry for a confirmed booking (concept §4.6).

One VEVENT per pickup pool, spanning that group's lending period, attached to
the confirmation email so the borrower can add it to their calendar.
"""
from datetime import timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from catalog.models import Product


def _dt(value):
    """Format an aware datetime as a UTC iCalendar timestamp."""
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _date(value):
    """Local calendar date (YYYYMMDD) for an all-day VALUE=DATE field."""
    return timezone.localtime(value).strftime("%Y%m%d")


def _esc(text):
    """Escape a text value per RFC 5545."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _groups(booking):
    """Group the booking's active items by pickup pool, preserving order."""
    groups = {}
    for item in booking.items.all():
        pool = item.resource.resource_pool
        groups.setdefault(pool.id, (pool, []))[1].append(item)
    return list(groups.values())


def build_ics(booking):
    """Return an iCalendar document (str) for ``booking``."""
    shop = settings.SHOP_BASE_URL.rstrip("/")
    stamp = _dt(timezone.now())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Ausleihbar//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for pool, items in _groups(booking):
        start = min(i.period.lower for i in items)
        end = max(i.period.upper for i in items)
        products = "; ".join(
            f"{i.resource.product.title} ({i.resource.inventory_number})"
            for i in items
        )
        # Full, single-line location so calendar apps can show / navigate to it:
        # "<pool>, <room>, <every address line>".
        location_parts = [pool.name]
        if pool.room:
            location_parts.append(pool.room)
        if pool.address:
            location_parts += [
                ln.strip() for ln in pool.address.splitlines() if ln.strip()
            ]
        location = ", ".join(location_parts)
        # Day bookings are all-day events spanning exactly the booked days
        # (VALUE=DATE DTEND is exclusive per RFC 5545, = last day + 1); hourly
        # bookings keep their real start/end times.
        if items[0].resource.product.lending_type == Product.LendingType.DAYS:
            when = [f"DTSTART;VALUE=DATE:{_date(start)}", f"DTEND;VALUE=DATE:{_date(end)}"]
        else:
            when = [f"DTSTART:{_dt(start)}", f"DTEND:{_dt(end)}"]
        lines += [
            "BEGIN:VEVENT",
            f"UID:booking-{booking.id}-pool-{pool.id}@ausleihbar",
            f"DTSTAMP:{stamp}",
            *when,
            f"SUMMARY:{_esc(f'Ausleihbar {booking.code} — pickup at {pool.name}')}",
            f"LOCATION:{_esc(location)}",
            f"DESCRIPTION:{_esc(products + chr(10) + 'Bookings: ' + shop + '/bookings')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
