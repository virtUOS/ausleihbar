# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Booking cycles per department: how far ahead a person may book.

Bookings are open until the end of the current cycle; during the last
``transition_weeks`` of it the next cycle opens as well. Within
``advance_days`` of today any number of places may be booked, beyond that
only ``advance_places`` (the rest is enforced by the callers).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from django.utils import timezone

from lending.services import add_months

from . import rights
from .hours import TZ, local_dt
from .models import DeskSettings, Place, Reservation


@dataclass(frozen=True)
class Window:
    today: date
    cycle_end: date
    next_cycle_end: date
    transition_from: date
    open_until: date
    advance_until: date
    advance_days: int
    advance_places: int


def today() -> date:
    return timezone.localtime(timezone.now(), TZ).date()


def _current_day() -> date:
    # Looked up at call time so that tests can patch ``cycles.today``.
    return today()


def booking_window(pool, today: date | None = None) -> Window:
    if today is None:
        today = _current_day()
    cfg = DeskSettings.for_pool(pool)
    n = cfg.cycle_months
    start = date(today.year, ((today.month - 1) // n) * n + 1, 1)
    next_start = add_months(start, n)
    cycle_end = next_start - timedelta(days=1)
    next_cycle_end = add_months(next_start, n) - timedelta(days=1)
    transition_from = next_start - timedelta(weeks=cfg.transition_weeks)
    advance_until = add_months(today, cfg.advance_months)
    if pool.max_booking_months:
        advance_until = min(advance_until, add_months(today, pool.max_booking_months))
    return Window(
        today=today,
        cycle_end=cycle_end,
        next_cycle_end=next_cycle_end,
        transition_from=transition_from,
        open_until=next_cycle_end if today >= transition_from else cycle_end,
        advance_until=advance_until,
        advance_days=cfg.advance_days,
        advance_places=cfg.advance_places,
    )


def is_privileged(actor, holder, pool) -> bool:
    """An assistant booking for somebody else may exceed the advance quota
    (the booking horizon is never waived)."""
    return actor.pk != holder.pk and pool.pk in rights.assistant_pool_ids(actor)


def advance_usage(pool, holder, window, *, exclude_request_id=None) -> dict[date, set[int]]:
    """Day -> place ids the holder already has beyond ``window.open_until`` in
    ``pool`` (active reservations that have not ended yet). Each source adds
    its days to the same mapping; ``exclude_request_id`` is for the sources
    that stem from a request (none yet)."""
    usage: dict[date, set[int]] = defaultdict(set)
    first_beyond = local_dt(window.open_until + timedelta(days=1), 0)
    reservations = Reservation.objects.filter(
        holder=holder,
        place__room__floor__pool=pool,
        status=Reservation.Status.ACTIVE,
        period__endswith__gt=timezone.now(),
        period__startswith__gte=first_beyond,
    ).values_list("place_id", "period")
    for place_id, period in reservations:
        usage[timezone.localtime(period.lower, TZ).date()].add(place_id)
    return usage


def check_limits(
    *, actor, holder, places: Iterable[Place], slots: Iterable[tuple[date, int]],
    exclude_request_id=None,
) -> list[str]:
    """Check ``slots`` (day, place id) of one booking against each involved
    department's window. Raises ``BookingError``; for a privileged actor the
    advance-quota breaches are returned as warning codes instead."""
    from .booking import BookingError

    by_pool: dict[int, tuple] = {}
    pool_of = {}
    for place in places:
        pool_of[place.pk] = place.pool
        by_pool.setdefault(place.pool.pk, (place.pool, []))
    for day, place_id in slots:
        by_pool[pool_of[place_id].pk][1].append((day, place_id))
    warnings: list[str] = []
    for pool, pool_slots in by_pool.values():
        window = booking_window(pool)
        if any(day > window.advance_until for day, _ in pool_slots):
            raise BookingError("horizon", detail="Too far ahead.")
        new: dict[date, set[int]] = defaultdict(set)
        for day, place_id in pool_slots:
            if day > window.open_until:
                new[day].add(place_id)
        if not new:
            continue
        used = advance_usage(pool, holder, window, exclude_request_id=exclude_request_id)
        total = {day: used.get(day, set()) | new.get(day, set()) for day in used.keys() | new.keys()}
        privileged = is_privileged(actor, holder, pool)
        breaches = []
        if len(total) > window.advance_days and any(day not in used for day in new):
            breaches.append(BookingError(
                "advance_days",
                detail="You have reached the number of days you may book beyond the booking window.",
                extra={"limit": window.advance_days, "open_until": window.open_until.isoformat()},
            ))
        too_many = sorted(d for d in new if len(total[d]) > window.advance_places)
        if too_many:
            breaches.append(BookingError(
                "advance_places",
                detail="Too many places on one day beyond the booking window.",
                extra={"limit": window.advance_places, "day": too_many[0].isoformat()},
            ))
        if breaches and not privileged:
            raise breaches[0]
        warnings.extend(b.code for b in breaches if b.code not in warnings)
    return warnings
