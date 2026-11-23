# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Actions triggered by the buttons of a door display.

The device is bound to a room, not to a person: check-in works for any
holder, check-out hands back the rest of the booking, and a free meeting
room can be booked anonymously (no holder, no notification). Every action
is logged as a ``DisplayEvent``.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import booking, checkin, hours
from .booking import BookingError
from .models import DisplayEvent, Place, Reservation


def _log(display, action, place, reservation) -> None:
    DisplayEvent.objects.create(
        display=display,
        display_label=str(display),
        pool=place.pool,
        room=place.room,
        place=place,
        reservation=reservation,
        action=action,
    )


def check_in(reservation, *, display, now) -> None:
    """Check in a reservation of any holder (window rules as for the holder)."""
    with transaction.atomic():
        checkin._check_in_core(reservation, now)
        _log(display, DisplayEvent.Action.CHECK_IN, reservation.place, reservation)


def check_out(reservation, *, display, now) -> None:
    """Hand back the rest of a started, checked-in reservation. The holder is
    not notified."""
    with transaction.atomic():
        # Lock the row: a concurrent change must not be overwritten.
        current = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if (
            current.status != Reservation.Status.ACTIVE
            or current.checked_in_at is None
            or current.period.lower > now
        ):
            raise BookingError("not_allowed", detail="This reservation cannot be checked out.")
        current.status = Reservation.Status.RELEASED
        current.released_at = timezone.localtime(now, hours.TZ).replace(
            minute=0, second=0, microsecond=0
        )
        current.release_reason = Reservation.ReleaseReason.DISPLAY
        current.save(update_fields=["status", "released_at", "release_reason"])
        reservation.status = current.status
        reservation.released_at = current.released_at
        reservation.release_reason = current.release_reason
        _log(display, DisplayEvent.Action.CHECK_OUT, reservation.place, reservation)


def max_anonymous_hours(place, now) -> int:
    """Whole hours from the current local hour until the first taken or
    closed hour or the business end; 0 = not bookable now."""
    if place.kind != Place.Kind.MEETING_ROOM or not place.is_bookable:
        return 0
    local = timezone.localtime(now, hours.TZ)
    day, hour = local.date(), local.hour
    open_hours = hours.business_hours(place.pool, day)
    if open_hours is None or not open_hours[0] <= hour < open_hours[1]:
        return 0
    closed = hours.closed_hours(place.pool, day)
    end = hour
    while end < open_hours[1] and end not in closed:
        period = hours.local_range(day, end, end + 1)
        if booking._taken_place_ids([place.pk], period) or booking._is_fixed_for_others(
            place, None, period
        ):
            break
        end += 1
    return end - hour


def book_anonymous(place, *, display, hours_: int, now) -> Reservation:
    """Book a free meeting room from the current hour without a person.
    Access groups are deliberately not checked."""
    if place.kind != Place.Kind.MEETING_ROOM:
        raise BookingError("not_allowed", detail="Only meeting rooms can be booked here.")
    limit = max_anonymous_hours(place, now)
    if limit < 1:
        raise BookingError("taken", detail="The room is not free now.")
    count = max(1, min(int(hours_), limit))
    local = timezone.localtime(now, hours.TZ)
    day, hour = local.date(), local.hour
    try:
        with transaction.atomic():
            res = Reservation.objects.create(
                place=place,
                pool=place.pool,
                holder=None,
                booked_by=None,
                display=display,
                period=hours.local_range(day, hour, hour + count),
                checked_in_at=now,
            )
            _log(display, DisplayEvent.Action.BOOK, place, res)
    except IntegrityError:
        raise BookingError("taken", detail="The room was just taken.") from None
    return res
