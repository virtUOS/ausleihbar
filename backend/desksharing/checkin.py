# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Check-in, QR scan and "Ich komme später".

The check-in window of a reservation runs from 15 minutes before its start
to its end. Scanning a place's QR code checks in the holder's own booking or
books the place spontaneously and checks in at once.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from . import booking, hours, rights
from .booking import BookingError
from .models import Place, Reservation

WINDOW_LEAD = timedelta(minutes=15)


@dataclass
class ScanResult:
    action: str  # "checked_in" | "booked" | "not_allowed" | "taken"
    reservation: Reservation | None = None
    next_free_until: datetime | None = None
    # For "not_allowed": no_rights | inactive | closed | outside_hours |
    # unknown_token | horizon.
    reason: str = ""


def _now(now):
    return now or timezone.now()


def _window_open(reservation, now) -> bool:
    """Window open or already started (and not over)."""
    return reservation.period.lower - WINDOW_LEAD <= now < reservation.period.upper


def check_in(reservation, *, user, now=None) -> None:
    """Check in the holder; every active reservation of the same group and
    holder on the same local day whose window is open is checked in too."""
    now = _now(now)
    if reservation.holder_id != user.pk:
        raise BookingError("not_allowed", detail="Only the holder may check in.")
    if reservation.status != Reservation.Status.ACTIVE:
        raise BookingError("not_allowed", detail="This reservation is not active.")
    if not _window_open(reservation, now):
        raise BookingError("outside_window", detail="Check-in is not possible now.")
    day = hours.local_day_hours(reservation.period)[0]
    with transaction.atomic():
        # Lock the rows: a concurrent release must not be overwritten.
        siblings = list(
            Reservation.objects.select_for_update()
            .filter(
                group=reservation.group,
                holder_id=reservation.holder_id,
                status=Reservation.Status.ACTIVE,
            )
            .order_by("pk")
        )
        if reservation.pk not in {r.pk for r in siblings}:
            raise BookingError("not_allowed", detail="This reservation is not active.")
        for res in siblings:
            if hours.local_day_hours(res.period)[0] != day or not _window_open(res, now):
                continue
            if res.checked_in_at is None:
                res.checked_in_at = now
            res.potentially_free_at = None
            res.save(update_fields=["checked_in_at", "potentially_free_at"])
            if res.pk == reservation.pk:
                reservation.checked_in_at = res.checked_in_at
                reservation.potentially_free_at = None


def come_later(reservation, *, user, until, now=None) -> None:
    """Announce a later arrival; ``until`` must lie after now and within the
    reservation period."""
    now = _now(now)
    if reservation.holder_id != user.pk:
        raise BookingError("not_allowed", detail="Only the holder may do this.")
    if (
        reservation.status != Reservation.Status.ACTIVE
        or reservation.checked_in_at is not None
        or reservation.period.upper <= now
    ):
        raise BookingError("not_allowed", detail="This reservation cannot be postponed.")
    if until <= now or until > reservation.period.upper:
        raise BookingError("invalid_until", detail="Choose a time within the reservation.")
    reservation.late_until = until
    reservation.save(update_fields=["late_until"])


def _spontaneous_end(place, user, day, start_hour) -> int:
    """First hour after ``start_hour`` that is closed, taken or outside the
    business hours (at most the business end)."""
    pool = place.pool
    business_end = hours.business_hours(pool, day)[1]
    closed = hours.closed_hours(pool, day)
    end = start_hour + 1
    if place.kind == Place.Kind.MEETING_ROOM:
        # Meeting rooms are taken spontaneously for the current hour only.
        return min(end, business_end)
    while end < business_end and end not in closed:
        period = hours.local_range(day, end, end + 1)
        if booking._taken_place_ids([place.pk], period) or booking._is_fixed_for_others(
            place, user, period
        ):
            break
        end += 1
    return end


def check_in_place(place, *, user, now=None) -> ScanResult:
    """Check in at ``place``: the user's own booking, or a spontaneous one."""
    now = _now(now)
    if not place.is_bookable:
        return ScanResult("not_allowed", reason="inactive")
    if not rights.can_book_place(user, place):
        return ScanResult("not_allowed", reason="no_rights")
    active = Reservation.objects.filter(place=place, status=Reservation.Status.ACTIVE)
    mine = (
        active.filter(
            holder=user,
            period__startswith__lte=now + WINDOW_LEAD,
            period__endswith__gt=now,
        )
        .order_by("period")
        .first()
    )
    if mine is not None:
        check_in(mine, user=user, now=now)
        return ScanResult("checked_in", mine)
    local = timezone.localtime(now, hours.TZ)
    day, hour = local.date(), local.hour
    open_hours = hours.business_hours(place.pool, day)
    if open_hours is None or hour in hours.closed_hours(place.pool, day):
        return ScanResult("not_allowed", reason="closed")
    if not open_hours[0] <= hour < open_hours[1]:
        return ScanResult("not_allowed", reason="outside_hours")
    current = hours.local_range(day, hour, hour + 1)
    holder_res = active.filter(period__overlap=current).first()
    if holder_res is not None:
        return ScanResult("taken", None, holder_res.period.upper)
    if booking._is_fixed_for_others(place, user, current):
        return ScanResult("taken")
    end = _spontaneous_end(place, user, day, hour)
    try:
        # Atomic: a failed check-in never leaves a booking behind.
        with transaction.atomic():
            [res] = booking.book(
                actor=user, holder=user, places=[place], day=day,
                start_hour=hour, end_hour=end,
            )
            check_in(res, user=user, now=now)
    except BookingError as exc:
        if exc.code == "taken":
            return ScanResult("taken")
        reason = exc.code if exc.code in ("closed", "outside_hours", "horizon") else "no_rights"
        return ScanResult("not_allowed", reason=reason)
    return ScanResult("booked", res, res.period.upper)


def scan(token: str, *, user, now=None) -> ScanResult:
    place = (
        Place.objects.select_related("room__floor__pool").filter(qr_token=token).first()
    )
    if place is None:
        return ScanResult("not_allowed", reason="unknown_token")
    return check_in_place(place, user=user, now=now)
