# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Whether a pool is open at a moment (item door signs, walk-in checks).

A pool is closed on its ``closed_weekdays`` and on days covered by a
system-wide or pool-wide ``Block``; otherwise its ``opening_hours`` decide
(``{"mon": [["09:00", "17:00"]], …}``, breaks between ranges are closed).
A pool without opening hours counts as open all day.
"""
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
NEXT_OPENING_DAYS = 8


def _ranges(opening_hours, day):
    """That weekday's opening ranges as sorted ``(time, time)`` pairs."""
    out = []
    for start_str, end_str in (opening_hours or {}).get(WEEKDAY_KEYS[day.weekday()], []) or []:
        sh, sm = (int(x) for x in start_str.split(":"))
        eh, em = (int(x) for x in end_str.split(":"))
        out.append((time(sh, sm), time(eh, em)))
    return sorted(out)


def within_opening_hours(opening_hours, moment, *, is_end):
    """Whether local ``moment`` lies in one of that weekday's opening ranges.

    A start must be in ``[open, close)``, an end in ``(open, close]``; breaks
    between ranges count as closed (same ranges as the hourly grid).
    """
    local = timezone.localtime(moment)
    current = local.time()
    for lo, hi in _ranges(opening_hours, local.date()):
        if (lo < current <= hi) if is_end else (lo <= current < hi):
            return True
    return False


def _has_hours(opening_hours) -> bool:
    return any((opening_hours or {}).values())


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def _closed_day(pool, day) -> bool:
    """Closed weekday or a system/pool block overlapping the local ``day``."""
    from .models import Block

    if day.weekday() in (pool.closed_weekdays or []):
        return True
    start = _day_start(day)
    end = _day_start(day + timedelta(days=1))
    return Block.objects.filter(
        Q(resource_pool__isnull=True) | Q(resource_pool=pool),
        product__isnull=True,
        resource__isnull=True,
        period__overlap=(start, end),
    ).exists()


def is_open(pool, moment) -> bool:
    day = timezone.localtime(moment).date()
    if _closed_day(pool, day):
        return False
    if not _has_hours(pool.opening_hours):
        return True
    return within_opening_hours(pool.opening_hours, moment, is_end=False)


def next_opening(pool, moment):
    """The next moment after ``moment`` the pool opens (within 8 days), or
    ``None``. Without opening hours, that is the start of the next open day."""
    today = timezone.localtime(moment).date()
    for offset in range(NEXT_OPENING_DAYS + 1):
        day = today + timedelta(days=offset)
        if _closed_day(pool, day):
            continue
        if not _has_hours(pool.opening_hours):
            start = _day_start(day)
            if start > moment:
                return start
            continue
        for lo, _hi in _ranges(pool.opening_hours, day):
            opening = timezone.make_aware(datetime.combine(day, lo))
            if opening > moment:
                return opening
    return None
