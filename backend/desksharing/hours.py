# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""The desksharing hour grid: whole local hours 06-20 (Europe/Berlin)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Q

from lending.models import Block

from .models import DeskSettings

TZ = ZoneInfo("Europe/Berlin")
FIRST_HOUR = 6
LAST_HOUR = 20


def local_dt(day: date, hour: int) -> datetime:
    """Aware local datetime at ``hour``:00 of ``day`` (0 <= hour <= 24)."""
    if hour == 24:
        return datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ)
    return datetime.combine(day, time(hour), tzinfo=TZ)


def local_range(day: date, start_hour: int, end_hour: int) -> DateTimeTZRange:
    """[start_hour, end_hour) of ``day`` in local time (DST-safe: each bound
    gets the offset valid at that wall-clock time)."""
    return DateTimeTZRange(local_dt(day, start_hour), local_dt(day, end_hour))


def local_day_hours(period) -> tuple[date, int, int]:
    """(day, start_hour, end_hour) of a reservation period."""
    lower, upper = period.lower.astimezone(TZ), period.upper.astimezone(TZ)
    end_hour = upper.hour if upper.date() == lower.date() else 24
    return lower.date(), lower.hour, end_hour


def business_hours(pool, day: date, settings_=None) -> tuple[int, int] | None:
    """The department's desksharing hours on ``day``, clamped to 06-20;
    ``None`` when closed that weekday. Pass the pool's ``DeskSettings`` as
    ``settings_`` to avoid one query per day."""
    if settings_ is None:
        settings_ = DeskSettings.objects.filter(pool=pool).first()
    if settings_ is None:
        return None
    hours = (settings_.business_hours or {}).get(str(day.weekday()))
    if not hours:
        return None
    start, end = max(FIRST_HOUR, int(hours[0])), min(LAST_HOUR, int(hours[1]))
    return (start, end) if start < end else None


def _block_periods(pool, period):
    """Periods of system-wide lending blocks (public holidays) — plus the
    pool-scoped ones when ``pool`` is given — that overlap ``period``."""
    scope = Q(resource_pool__isnull=True)
    if pool is not None:
        scope |= Q(resource_pool=pool)
    return list(
        Block.objects.filter(
            scope, product__isnull=True, resource__isnull=True, period__overlap=period
        ).values_list("period", flat=True)
    )


def _blocked_hours(periods, day: date) -> set[int]:
    """Grid hours of ``day`` hit by any of ``periods``."""
    closed = set()
    for period in periods:
        for hour in range(FIRST_HOUR, LAST_HOUR):
            start, end = local_dt(day, hour), local_dt(day, hour + 1)
            if (period.lower is None or period.lower < end) and (
                period.upper is None or period.upper > start
            ):
                closed.add(hour)
    return closed


def closed_hours(pool, day: date) -> set[int]:
    """Grid hours of ``day`` hit by a system- or pool-scoped lending block
    (public holidays are system-wide blocks)."""
    return _blocked_hours(_block_periods(pool, local_range(day, FIRST_HOUR, LAST_HOUR)), day)


def closed_hours_by_day(pool, first: date, last: date) -> dict[date, set[int]]:
    """``closed_hours`` of every day in ``first..last`` (inclusive; only days
    with closed hours are listed) — one block query for the whole span."""
    periods = _block_periods(pool, DateTimeTZRange(local_dt(first, 0), local_dt(last, 24)))
    found = {}
    if not periods:
        return found
    day = first
    while day <= last:
        closed = _blocked_hours(periods, day)
        if closed:
            found[day] = closed
        day += timedelta(days=1)
    return found


def blocked_days(pool, first: date, last: date) -> list[date]:
    """Days in ``first..last`` (inclusive) on which blocks close every bookable
    hour: the department's business hours when ``pool`` is given (closed
    weekdays are not listed — they are no blocks), else the whole 06-20 grid
    and system-wide blocks only. One block query for the whole span."""
    periods = _block_periods(pool, DateTimeTZRange(local_dt(first, 0), local_dt(last, 24)))
    if not periods:
        return []
    business = None
    if pool is not None:
        settings_ = DeskSettings.objects.filter(pool=pool).first()
        business = (settings_.business_hours if settings_ else None) or {}
    days = []
    day = first
    while day <= last:
        if business is None:
            wanted = set(range(FIRST_HOUR, LAST_HOUR))
        else:
            span = business.get(str(day.weekday()))
            start = max(FIRST_HOUR, int(span[0])) if span else 0
            end = min(LAST_HOUR, int(span[1])) if span else 0
            wanted = set(range(start, end))
        if wanted and wanted <= _blocked_hours(periods, day):
            days.append(day)
        day += timedelta(days=1)
    return days
