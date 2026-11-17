# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Booking cycles per department: how far ahead a person may book.

Bookings are open until the end of the current cycle; during the last
``transition_weeks`` of it the next cycle opens as well. Within
``advance_days`` of today any number of places may be booked, beyond that
only ``advance_places`` (the rest is enforced by the callers).
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from lending.services import add_months

from .hours import TZ
from .models import DeskSettings


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
    return datetime.now(TZ).date()


_berlin_today = today


def booking_window(pool, today: date | None = None) -> Window:
    if today is None:
        today = _berlin_today()
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
