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


def business_hours(pool, day: date) -> tuple[int, int] | None:
    """The department's desksharing hours on ``day``, clamped to 06-20;
    ``None`` when closed that weekday."""
    settings_ = DeskSettings.objects.filter(pool=pool).first()
    if settings_ is None:
        return None
    hours = (settings_.business_hours or {}).get(str(day.weekday()))
    if not hours:
        return None
    start, end = max(FIRST_HOUR, int(hours[0])), min(LAST_HOUR, int(hours[1]))
    return (start, end) if start < end else None


def closed_hours(pool, day: date) -> set[int]:
    """Grid hours of ``day`` hit by a system- or pool-scoped lending block
    (public holidays are system-wide blocks)."""
    day_range = local_range(day, FIRST_HOUR, LAST_HOUR)
    periods = Block.objects.filter(
        Q(resource_pool__isnull=True) | Q(resource_pool=pool),
        product__isnull=True,
        resource__isnull=True,
        period__overlap=day_range,
    ).values_list("period", flat=True)
    closed = set()
    for period in periods:
        for hour in range(FIRST_HOUR, LAST_HOUR):
            start, end = local_dt(day, hour), local_dt(day, hour + 1)
            if (period.lower is None or period.lower < end) and (
                period.upper is None or period.upper > start
            ):
                closed.add(hour)
    return closed
