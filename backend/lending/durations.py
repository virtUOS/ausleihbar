# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Effective lending-duration limits (concept §3.2, ticket #109).

The min. and max. lending duration of a device (``Resource``) are resolved
separately, each from the first level that sets a value:

    device's own value → product's value → its pool's default → no limit

The unit is the product's lending type (days or hours); the pool default used
is ``default_(min|max)_(days|hours)`` accordingly. An empty value (``None``,
also ``0``) means "inherit". Every reservation belongs to one pool, so limits
are evaluated per device / pool.

Span lengths are counted exactly like the booking calendars count them (see
:func:`period_length`).
"""
import math
from collections import OrderedDict
from datetime import timedelta

from django.utils import timezone

from catalog.models import Product, ResourcePool

SOURCE_RESOURCE = "resource"
SOURCE_PRODUCT = "product"
SOURCE_POOL = "pool"
SOURCE_NONE = "none"


class DurationLimitError(ValueError):
    """A requested period lies outside the effective duration limits.

    ``violations`` lists one dict per offending item (``product``, ``title``,
    ``lending_type``, ``requested``, ``min``, ``max``, ``resource``) so an API
    can show the limits; ``str(error)`` is the human-readable message.
    """

    def __init__(self, message, violations=None):
        super().__init__(message)
        self.violations = violations or []


def lending_unit(lending_type):
    """``"hours"`` for hourly products, else ``"days"``."""
    return "hours" if lending_type == Product.LendingType.HOURS else "days"


def _value(value):
    """A stored limit, or ``None`` when unset (empty/0 = inherit)."""
    return value or None


def pool_defaults(pool, lending_type):
    """(min, max) default of ``pool`` in the unit of ``lending_type``."""
    unit = lending_unit(lending_type)
    return (
        _value(getattr(pool, f"default_min_{unit}")),
        _value(getattr(pool, f"default_max_{unit}")),
    )


def _resolve(*levels):
    """First set ``(value, source)`` of ``levels``, else ``(None, "none")``."""
    for value, source in levels:
        if _value(value):
            return value, source
    return None, SOURCE_NONE


def effective_limits_detail(resource, product=None, pool=None):
    """Effective min/max of ``resource`` with the level they come from.

    Returns ``{"min": (value, source), "max": (value, source),
    "inherited_min": …, "inherited_max": …}``; ``source`` is ``resource``,
    ``product``, ``pool`` or ``none``. ``inherited_*`` is what would apply
    without the device's own value (for the "inherit from product" toggle).
    """
    product = product or resource.product
    pool = pool or resource.resource_pool
    pool_min, pool_max = pool_defaults(pool, product.lending_type)
    inherited_min = _resolve(
        (product.min_duration, SOURCE_PRODUCT), (pool_min, SOURCE_POOL)
    )
    inherited_max = _resolve(
        (product.max_duration, SOURCE_PRODUCT), (pool_max, SOURCE_POOL)
    )
    return {
        "min": _resolve((resource.min_duration, SOURCE_RESOURCE), inherited_min),
        "max": _resolve((resource.max_duration, SOURCE_RESOURCE), inherited_max),
        "inherited_min": inherited_min,
        "inherited_max": inherited_max,
    }


def effective_limits(resource, product=None, pool=None):
    """``(min, max)`` effective lending duration of ``resource`` (None = no limit)."""
    detail = effective_limits_detail(resource, product, pool)
    return detail["min"][0], detail["max"][0]


def limits_for_resources(product, resources):
    """Bulk effective limits for many resources of one ``product``.

    ``resources`` is a queryset; its ordering is kept. Returns an ordered
    ``{resource_id: (pool_id, min, max)}`` using two queries (resources, pools)
    regardless of the number of devices.
    """
    rows = list(
        resources.values_list("id", "resource_pool_id", "min_duration", "max_duration")
    )
    pools = {
        pool.id: pool
        for pool in ResourcePool.objects.filter(id__in={row[1] for row in rows})
    }
    defaults = {pid: pool_defaults(pool, product.lending_type) for pid, pool in pools.items()}
    out = OrderedDict()
    for rid, pool_id, own_min, own_max in rows:
        pool_min, pool_max = defaults[pool_id]
        out[rid] = (
            pool_id,
            _value(own_min) or _value(product.min_duration) or pool_min,
            _value(own_max) or _value(product.max_duration) or pool_max,
        )
    return out


def _bookable(product, pool_ids):
    # The availability engine's base set (available-status, live units);
    # imported lazily — ``services`` imports this module.
    from .services import _available_base

    return _available_base(product, pool_ids)


def bookable_limits_by_pool(product, pool_ids=None):
    """:func:`limits_by_pool` over the bookable units of ``product`` in
    ``pool_ids`` (``None`` = all pools)."""
    return limits_by_pool(product, _bookable(product, pool_ids))


def calendar_limits(product, pool_ids=None):
    """``(min, max)`` for a booking calendar: the widest frame over the
    bookable units in ``pool_ids`` — the calendar must allow every length some
    unit admits; the cart then picks a fitting unit. Without units, the
    product's own values."""
    per_unit = limits_for_resources(product, _bookable(product, pool_ids))
    if not per_unit:
        return _value(product.min_duration), _value(product.max_duration)
    return widest((low, high) for _pool, low, high in per_unit.values())


def period_length(lending_type, start, end):
    """Length of [start, end) in the lending unit — counted like the calendars.

    * days: the number of local calendar days the span touches, start day
      inclusive (``BookingCalendar`` sends start/end *dates*; the API turns
      them into [start 00:00, end+1 00:00), so 1st..3rd = 3 days). The last
      day is the one holding ``end - 1µs``, the same rule ``available_resources``
      uses for the return day.
    * hours: whole *wall-clock* hours, a started hour counts. The hourly grid
      (``availability_per_hour`` / ``HourlyBookingCalendar``) builds slots by
      local wall-clock arithmetic (aware datetime + 1 h keeps the tzinfo), so
      the count is taken on local wall-clock times and equals the number of
      slots selected — also on DST days (e.g. 00:00–05:00 on the October
      fall-back day is 5 hours, though 6 hours elapse).
    """
    if lending_type == Product.LendingType.HOURS:
        wall_start = timezone.localtime(start).replace(tzinfo=None)
        wall_end = timezone.localtime(end).replace(tzinfo=None)
        return max(1, math.ceil((wall_end - wall_start) / timedelta(hours=1)))
    first = timezone.localtime(start).date()
    last = timezone.localtime(end - timedelta(microseconds=1)).date()
    return (last - first).days + 1


def fits(limits, length):
    """Whether ``length`` lies within ``(min, max)`` (``None`` = open)."""
    low, high = limits
    return (low is None or length >= low) and (high is None or length <= high)


def widest(limits):
    """The widest ``(min, max)`` over several ranges (any open side stays open).

    An empty input yields ``(None, None)``.
    """
    limits = list(limits)
    if not limits:
        return None, None
    mins = [low for low, _high in limits]
    maxes = [high for _low, high in limits]
    return (
        None if any(m is None for m in mins) else min(mins),
        None if any(m is None for m in maxes) else max(maxes),
    )


def limits_by_pool(product, resources):
    """Per-pool widest ranges of ``resources`` (a queryset of ``product``'s).

    Returns ``[{"pool_id", "pool_name", "min", "max"}]`` ordered by the pools'
    curated position, then name. Three queries in total.
    """
    per_resource = limits_for_resources(product, resources)
    grouped = {}
    for pool_id, low, high in per_resource.values():
        grouped.setdefault(pool_id, []).append((low, high))
    pools = ResourcePool.objects.filter(id__in=grouped).order_by("position", "name")
    rows = []
    for pool in pools:
        low, high = widest(grouped[pool.id])
        rows.append({"pool_id": pool.id, "pool_name": pool.name, "min": low, "max": high})
    return rows


def _unit_text(count, unit):
    singular = unit[:-1]  # "days" -> "day", "hours" -> "hour"
    return f"{count} {singular if count == 1 else unit}"


def format_range(low, high, unit):
    """English text of a duration range, e.g. ``1–7 days`` / ``at most 4 hours``."""
    unit = lending_unit(unit)
    if low is None and high is None:
        return "no limit"
    if low is None:
        return f"at most {_unit_text(high, unit)}"
    if high is None:
        return f"at least {_unit_text(low, unit)}"
    if low == high:
        return _unit_text(low, unit)
    return f"{low}–{_unit_text(high, unit)}"


def limit_message(product, pool_ranges, length):
    """Clear refusal text naming the allowed range(s) and the requested length.

    ``pool_ranges`` is a list of ``{"pool_name", "min", "max"}``; when the pools
    share one range it is given once, otherwise per pool.
    """
    unit = lending_unit(product.lending_type)
    distinct = {(r["min"], r["max"]) for r in pool_ranges}
    if len(distinct) <= 1:
        low, high = distinct.pop() if distinct else (None, None)
        allowed = format_range(low, high, unit)
    else:
        allowed = ", ".join(
            f"{r['pool_name']} {format_range(r['min'], r['max'], unit)}"
            for r in pool_ranges
        )
    return (
        f"Lending duration for '{product.title}': {allowed} "
        f"(selected: {_unit_text(length, unit)})."
    )
