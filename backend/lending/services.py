# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Availability computation and reservation creation (ADR-0006)."""
import calendar
import uuid
from collections import OrderedDict, defaultdict
from datetime import datetime, time, timedelta

import holidays as holidays_lib

from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Count, F, Max, Q
from django.utils import timezone

from catalog.models import Product, Resource, ResourceDefect, ResourcePool

from .models import Block, Booking, BookingItem, CartSetting, HolidaySetting


def _blocks_overlapping(start, end):
    """Block rows overlapping [start, end) as plain dicts."""
    return list(
        Block.objects.filter(period__overlap=DateTimeTZRange(start, end)).values(
            "resource_id", "product_id", "resource_pool_id", "period"
        )
    )


def _blocked_ids(resource_rows, blocks):
    """Resource ids blocked by any of ``blocks``.

    ``resource_rows`` is an iterable of (id, product_id, resource_pool_id).
    A resource is blocked if a system block exists, or its pool/product/itself
    is blocked.
    """
    has_system = False
    blocked_pools, blocked_products, blocked_res = set(), set(), set()
    for block in blocks:
        if block["resource_id"] is not None:
            blocked_res.add(block["resource_id"])
        elif block["product_id"] is not None:
            blocked_products.add(block["product_id"])
        elif block["resource_pool_id"] is not None:
            blocked_pools.add(block["resource_pool_id"])
        else:
            has_system = True
    return {
        rid
        for rid, product_id, pool_id in resource_rows
        if has_system
        or rid in blocked_res
        or product_id in blocked_products
        or pool_id in blocked_pools
    }


def _pool_closed_map(pool_ids):
    """Map pool id -> set of closed weekdays (0=Mon … 6=Sun)."""
    return {
        pid: set(weekdays or [])
        for pid, weekdays in ResourcePool.objects.filter(id__in=pool_ids).values_list(
            "id", "closed_weekdays"
        )
    }


def _pool_lead_map(pool_ids):
    """Map pool id -> required lead time in hours before pickup."""
    return dict(
        ResourcePool.objects.filter(id__in=pool_ids).values_list(
            "id", "lead_time_hours"
        )
    )


def _lead_blocked_ids(resource_rows, pool_lead, start, now):
    """Resource ids whose pool lead time isn't met for a pickup at ``start``.

    A pool with ``lead_time_hours`` requires the pickup to be at least that many
    hours from ``now``; earlier pickups are not bookable for those resources.
    """
    return {
        rid
        for rid, _product_id, pool_id in resource_rows
        if pool_lead.get(pool_id, 0)
        and start < now + timedelta(hours=pool_lead[pool_id])
    }


def _add_months(d, months):
    """Add ``months`` calendar months to a date, clamping the day if needed."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _pool_horizon_map(pool_ids):
    """Map pool id -> max booking horizon in months."""
    return dict(
        ResourcePool.objects.filter(id__in=pool_ids).values_list(
            "id", "max_booking_months"
        )
    )


def _horizon_blocked_ids(resource_rows, pool_horizon, start, now):
    """Resource ids whose pool booking horizon is exceeded by ``start``.

    A pickup further in the future than the pool's ``max_booking_months`` from
    today is not bookable (concept §3.5). A horizon of 0 means no limit.
    """
    today = timezone.localtime(now).date()
    pickup_day = timezone.localtime(start).date()
    blocked = set()
    for rid, _product_id, pool_id in resource_rows:
        months = pool_horizon.get(pool_id) or 0
        if months and pickup_day > _add_months(today, months):
            blocked.add(rid)
    return blocked


def _weekdays_in_window(start, end):
    """Set of weekday numbers covered by [start, end) in local time."""
    days = set()
    day = timezone.localtime(start).date()
    last = timezone.localtime(end - timedelta(microseconds=1)).date()
    while day <= last and len(days) < 7:
        days.add(day.weekday())
        day += timedelta(days=1)
    return days


def _closed_resource_ids(resource_rows, pool_closed, weekdays):
    """Resource ids whose pool is closed on any of ``weekdays``."""
    return {
        rid
        for rid, _product_id, pool_id in resource_rows
        if pool_closed.get(pool_id, set()) & weekdays
    }

# Default hold (minutes) used when no CartSetting row exists yet.
HOLD_MINUTES = 30


def cart_hold_minutes():
    """How long a cart holds its slots before expiring (admin-configurable)."""
    return CartSetting.load().hold_minutes


def release_expired_holds():
    """Free the slots of expired carts.

    A cart holds its slots via active booking items. The no-overlap exclusion
    constraint only looks at ``is_active`` (it cannot join to ``expires_at``),
    while availability already treats an expired cart as free. Cancelling
    expired carts keeps both views consistent. Returns the number released.
    """
    now = timezone.now()
    expired = Booking.objects.filter(
        status=Booking.Status.CART, expires_at__lt=now
    )
    ids = list(expired.values_list("id", flat=True))
    if not ids:
        return 0
    BookingItem.objects.filter(booking_id__in=ids, is_active=True).update(
        is_active=False
    )
    Booking.objects.filter(id__in=ids).update(status=Booking.Status.CANCELLED)
    return len(ids)


def cancel_uncollected_bookings(dry_run=False):
    """Cancel reservations that were never collected and are fully in the past.

    A PENDING/CONFIRMED booking whose items were never handed out and whose
    latest booked period has elapsed is a no-show: it needlessly held its slots
    for the whole period (issue #45). Cancelling frees the slots and marks the
    booking cancelled (history is kept). Open-ended bookings (no end) and
    anything already picked up are left untouched. Idempotent; safe to schedule.

    Returns the number of bookings cancelled (or that *would* be, for a dry run).
    """
    now = timezone.now()
    candidates = Booking.objects.filter(
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
    ).prefetch_related("items")
    to_cancel = []
    for booking in candidates:
        items = [i for i in booking.items.all() if i.is_active]
        if not items:
            continue
        # Anything already picked up (or returned) is a real lending, not a no-show.
        if any(i.handed_out_at or i.returned_at for i in items):
            continue
        uppers = [i.period.upper for i in items if i.period and i.period.upper]
        # Skip open-ended bookings (an item without an end never "expires" here).
        if len(uppers) != len(items):
            continue
        if max(uppers) <= now:
            to_cancel.append(booking.id)
    if not to_cancel or dry_run:
        return len(to_cancel)
    BookingItem.objects.filter(booking_id__in=to_cancel, is_active=True).update(
        is_active=False
    )
    Booking.objects.filter(id__in=to_cancel).update(status=Booking.Status.CANCELLED)
    return len(to_cancel)


def _occupying_items(product, start, end):
    """Active booking items of a product overlapping [start, end).

    Items in an expired cart are treated as free (their hold has lapsed).
    """
    now = timezone.now()
    return (
        BookingItem.objects.filter(
            resource__product=product,
            is_active=True,
            period__overlap=DateTimeTZRange(start, end),
        )
        .exclude(
            booking__status=Booking.Status.CART,
            booking__expires_at__lt=now,
        )
    )


def _closed_on_day(rows, date):
    """Resource ids closed on ``date`` (a block or a closed weekday)."""
    day_start = timezone.make_aware(datetime.combine(date, time.min))
    day_end = day_start + timedelta(days=1)
    blocked = _blocked_ids(rows, _blocks_overlapping(day_start, day_end))
    pool_closed = _pool_closed_map({row[2] for row in rows})
    closed_weekday = _closed_resource_ids(rows, pool_closed, {date.weekday()})
    return blocked | closed_weekday


def _lending_unit_delta(product, amount):
    """Turn an integer amount in the product's lending unit into a timedelta."""
    if not amount:
        return timedelta(0)
    if product.lending_type == Product.LendingType.HOURS:
        return timedelta(hours=amount)
    return timedelta(days=amount)


def product_gap_delta(product):
    """The product's minimum gap between bookings as a timedelta (0 -> none)."""
    return _lending_unit_delta(product, product.min_gap or 0)


def _gap_expanded(items, gap):
    """Widen each (resource_id, period) by ``gap`` on both sides so the day/slot
    overlap tests enforce the product's min-gap. A zero gap is a no-op."""
    if not gap:
        return items
    widened = []
    for resource_id, period in items:
        lower = period.lower - gap if period.lower is not None else None
        upper = period.upper + gap if period.upper is not None else None
        widened.append((resource_id, DateTimeTZRange(lower, upper)))
    return widened


def missing_lead_delta(product):
    """The product's 'missing product' notice lead as a timedelta (0 -> none)."""
    return _lending_unit_delta(product, product.missing_notice_lead or 0)


def _available_base(product, pool_ids=None):
    """Available-status resources of ``product``, optionally limited to pools.

    ``pool_ids=None`` means no pool restriction; passing a set restricts to
    those pools (used to enforce pool eligibility, concept §3.4).
    """
    qs = Resource.objects.filter(product=product, status=Resource.Status.AVAILABLE)
    if pool_ids is not None:
        qs = qs.filter(resource_pool_id__in=pool_ids)
    return qs


def available_resources(product, start, end, pool_ids=None, ignore_planning=False):
    """Return the resources of ``product`` bookable for [start, end).

    A resource is bookable if it is free of overlapping bookings for the whole
    range (widened by the product's ``min_gap`` on both sides, #48 part 2) AND
    its pool is open (no block / closed weekday) on both the pickup day (start)
    and the return day (end) AND the pickup respects the pool's lead time.
    Blocked/closed days *within* the range are bridgeable — the device is
    simply kept over them.

    Results are ordered best condition first, then longest idle (oldest
    ``returned_at``, nulls — i.e. never returned yet — first), then id, so
    allocation picks the best-rated, longest-idle unit (#48 FIFO + #49
    condition).

    ``ignore_planning`` skips the lead-time and booking-horizon limits (lender
    walk-in lending, concept §6.4); overlaps and closed days still apply.
    """
    base = _available_base(product, pool_ids)
    rows = list(base.values_list("id", "product_id", "resource_pool_id"))
    gap = product_gap_delta(product)
    occupied = set(
        _occupying_items(product, start - gap, end + gap).values_list(
            "resource_id", flat=True
        )
    )
    pickup_day = timezone.localtime(start).date()
    return_day = timezone.localtime(end - timedelta(microseconds=1)).date()
    closed = _closed_on_day(rows, pickup_day) | _closed_on_day(rows, return_day)
    lead_blocked = set()
    horizon_blocked = set()
    if not ignore_planning:
        now = timezone.now()
        pool_lead = _pool_lead_map({row[2] for row in rows})
        lead_blocked = _lead_blocked_ids(rows, pool_lead, start, now)
        pool_horizon = _pool_horizon_map({row[2] for row in rows})
        horizon_blocked = _horizon_blocked_ids(rows, pool_horizon, start, now)
    return (
        base.exclude(id__in=(occupied | closed | lead_blocked | horizon_blocked))
        .annotate(last_return=Max("booking_items__returned_at"))
        .order_by("-condition_rating", F("last_return").asc(nulls_first=True), "id")
    )


def availability(product, start, end, pool_ids=None):
    """Return total available-status resources and how many are free."""
    total = _available_base(product, pool_ids).count()
    free = available_resources(product, start, end, pool_ids).count()
    return {"total": total, "available": free}


def availability_by_pool(product, start, end, pool_ids):
    """Per-pool availability breakdown for [start, end).

    Returns one entry per pool in ``pool_ids`` that holds an available-status
    resource of ``product`` — ``{"pool_id", "total", "available"}`` — ordered by
    the pool's curated position then name. Pools with resources but zero free for
    the range are still included (available=0); pools with no resource for this
    product are omitted. Reuses ``availability()`` per pool so counts match what
    add-to-cart would allocate.
    """
    have = set(
        Resource.objects.filter(
            product=product,
            status=Resource.Status.AVAILABLE,
            resource_pool_id__in=pool_ids,
        ).values_list("resource_pool_id", flat=True)
    )
    if not have:
        return []
    ordered = list(
        ResourcePool.objects.filter(id__in=have)
        .order_by("position", "name")
        .values_list("id", flat=True)
    )
    out = []
    for pid in ordered:
        counts = availability(product, start, end, {pid})
        out.append({"pool_id": pid, "total": counts["total"], "available": counts["available"]})
    return out


def availability_per_day(
    product, start_date, end_date, pool_ids=None, ignore_planning=False
):
    """Available count per day in [start_date, end_date) for a calendar view.

    Fetches the overlapping bookings once and buckets them by day in Python.
    ``ignore_planning`` skips lead time and the booking horizon (walk-in, §6.4).
    """
    rows = list(
        _available_base(product, pool_ids).values_list(
            "id", "product_id", "resource_pool_id"
        )
    )
    available_ids = {row[0] for row in rows}
    total = len(available_ids)

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.min))
    gap = product_gap_delta(product)
    # Widen the fetch window by the gap so near-boundary bookings just outside
    # [start, end) are returned (mirrors available_resources); _gap_expanded then
    # widens each period so the day bucketing actually counts them (#48 part 2).
    items = list(
        _occupying_items(product, start_dt - gap, end_dt + gap).values_list(
            "resource_id", "period"
        )
    )
    items = _gap_expanded(items, gap)
    blocks = _blocks_overlapping(start_dt, end_dt)
    pool_closed = _pool_closed_map({row[2] for row in rows})
    pool_lead = _pool_lead_map({row[2] for row in rows})
    pool_horizon = _pool_horizon_map({row[2] for row in rows})
    now = timezone.now()

    days = []
    day = start_date
    while day < end_date:
        day_start = timezone.make_aware(datetime.combine(day, time.min))
        day_end = day_start + timedelta(days=1)
        occupied = {
            resource_id
            for resource_id, period in items
            if period.lower < day_end and (period.upper is None or period.upper > day_start)
        }
        day_blocks = [
            b
            for b in blocks
            if b["period"].lower < day_end
            and (b["period"].upper is None or b["period"].upper > day_start)
        ]
        blocked = _blocked_ids(rows, day_blocks)
        closed_today = blocked | _closed_resource_ids(rows, pool_closed, {day.weekday()})
        open_ids = available_ids - closed_today
        # Lead time reduces availability but is not a "closed" day.
        lead_blocked = set()
        horizon_blocked = set()
        if not ignore_planning:
            lead_blocked = _lead_blocked_ids(rows, pool_lead, day_start, now)
            horizon_blocked = _horizon_blocked_ids(rows, pool_horizon, day_start, now)
        free = len(open_ids - occupied - lead_blocked - horizon_blocked)
        # A day beyond every pool's booking horizon is shown as closed (greyed).
        beyond_horizon = bool(available_ids) and available_ids <= horizon_blocked
        days.append(
            {
                "date": day.isoformat(),
                "available": free,
                "total": total,
                "closed": (total > 0 and len(open_ids) == 0) or beyond_horizon,
            }
        )
        day += timedelta(days=1)
    return days


def availability_on_date(product_ids, date, pool_ids=None):
    """Available/total counts for several products on a single day.

    Used by the shop list to show per-product availability for a chosen date.
    One query for resources and one for overlapping bookings.
    """
    day_start = timezone.make_aware(datetime.combine(date, time.min))
    day_end = day_start + timedelta(days=1)

    base = Resource.objects.filter(
        product_id__in=product_ids, status=Resource.Status.AVAILABLE
    )
    if pool_ids is not None:
        base = base.filter(resource_pool_id__in=pool_ids)
    rows = list(base.values_list("id", "product_id", "resource_pool_id"))
    resources_by_product = defaultdict(set)
    for resource_id, product_id, _pool_id in rows:
        resources_by_product[product_id].add(resource_id)

    now = timezone.now()
    gap_by_product = {
        p.id: product_gap_delta(p) for p in Product.objects.filter(id__in=product_ids)
    }
    max_gap = max(gap_by_product.values(), default=timedelta(0))
    occupied_by_product = defaultdict(set)
    overlapping = (
        BookingItem.objects.filter(
            resource__product_id__in=product_ids,
            is_active=True,
            period__overlap=DateTimeTZRange(day_start - max_gap, day_end + max_gap),
        )
        .exclude(booking__status=Booking.Status.CART, booking__expires_at__lt=now)
        .values_list("resource__product_id", "resource_id", "period")
    )
    for product_id, resource_id, period in overlapping:
        gap = gap_by_product.get(product_id, timedelta(0))
        lo = day_start - gap
        hi = day_end + gap
        if period.lower < hi and (period.upper is None or period.upper > lo):
            occupied_by_product[product_id].add(resource_id)

    blocked = _blocked_ids(rows, _blocks_overlapping(day_start, day_end))
    pool_closed = _pool_closed_map({row[2] for row in rows})
    closed = _closed_resource_ids(rows, pool_closed, {date.weekday()})
    pool_lead = _pool_lead_map({row[2] for row in rows})
    lead_blocked = _lead_blocked_ids(rows, pool_lead, day_start, now)
    pool_horizon = _pool_horizon_map({row[2] for row in rows})
    horizon_blocked = _horizon_blocked_ids(rows, pool_horizon, day_start, now)
    unavailable = blocked | closed | lead_blocked | horizon_blocked

    result = {}
    for product_id in product_ids:
        resources = resources_by_product.get(product_id, set())
        occupied = occupied_by_product.get(product_id, set())
        result[product_id] = {
            "total": len(resources),
            "available": len(resources - occupied - unavailable),
        }
    return result


_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def availability_per_hour(product, date, pool_ids=None, ignore_planning=False):
    """Hourly availability for ``product`` on ``date``, within opening hours.

    Returns one slot per open hour (across the product's pools' opening hours
    for that weekday) with the free/total resource count. Used by the hourly
    booking grid. ``ignore_planning`` skips lead time / horizon (walk-in, §6.4).
    """
    rows = list(
        _available_base(product, pool_ids).values_list(
            "id", "product_id", "resource_pool_id"
        )
    )
    total = len(rows)
    pool_ids = {row[2] for row in rows}
    key = _WEEKDAY_KEYS[date.weekday()]

    ranges = []
    for opening in ResourcePool.objects.filter(id__in=pool_ids).values_list(
        "opening_hours", flat=True
    ):
        ranges.extend((opening or {}).get(key, []) or [])

    slots = {}
    for start_str, end_str in ranges:
        sh, sm = (int(x) for x in start_str.split(":"))
        eh, em = (int(x) for x in end_str.split(":"))
        cur = timezone.make_aware(datetime.combine(date, time(sh, sm)))
        range_end = timezone.make_aware(datetime.combine(date, time(eh, em)))
        while cur + timedelta(hours=1) <= range_end:
            slot_end = cur + timedelta(hours=1)
            iso = cur.isoformat()
            if iso not in slots:
                slots[iso] = {
                    "start": iso,
                    "end": slot_end.isoformat(),
                    "label": cur.strftime("%H:%M"),
                    "available": available_resources(
                        product, cur, slot_end, pool_ids, ignore_planning
                    ).count(),
                    "total": total,
                }
            cur = slot_end
    return [slots[k] for k in sorted(slots)]


def hourly_utilization_per_day(
    product, start_date, end_date, pool_ids=None, ignore_planning=False
):
    """Per-day capacity utilization for an hourly product over [start, end).

    Capacity for a day = open hours × available resources. Returns each day's
    booked percentage (0–100 of capacity) and a ``closed`` flag for days with
    no opening hours. One bookings query is reused across the whole range.
    ``ignore_planning`` skips lead time and the booking horizon (walk-in, §6.4).
    """
    rows = list(
        _available_base(product, pool_ids).values_list(
            "id", "product_id", "resource_pool_id"
        )
    )
    available_ids = {row[0] for row in rows}
    resource_count = len(available_ids)
    pool_ids = {row[2] for row in rows}
    opening_by_pool = dict(
        ResourcePool.objects.filter(id__in=pool_ids).values_list("id", "opening_hours")
    )

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.min))
    gap = product_gap_delta(product)
    # Widen the fetch window by the gap so near-boundary bookings just outside
    # [start, end) are returned (mirrors available_resources); _gap_expanded then
    # widens each period so the day bucketing actually counts them (#48 part 2).
    items = list(
        _occupying_items(product, start_dt - gap, end_dt + gap).values_list(
            "resource_id", "period"
        )
    )
    items = _gap_expanded(items, gap)
    blocks = _blocks_overlapping(start_dt, end_dt)
    pool_closed = _pool_closed_map(pool_ids)
    pool_lead = _pool_lead_map(pool_ids)
    pool_horizon = _pool_horizon_map(pool_ids)
    now = timezone.now()

    days = []
    day = start_date
    while day < end_date:
        key = _WEEKDAY_KEYS[day.weekday()]
        ranges = []
        for opening in opening_by_pool.values():
            ranges.extend((opening or {}).get(key, []) or [])

        slot_starts = {}
        for start_str, end_str in ranges:
            sh, sm = (int(x) for x in start_str.split(":"))
            eh, em = (int(x) for x in end_str.split(":"))
            cur = timezone.make_aware(datetime.combine(day, time(sh, sm)))
            range_end = timezone.make_aware(datetime.combine(day, time(eh, em)))
            while cur + timedelta(hours=1) <= range_end:
                slot_starts[cur] = cur + timedelta(hours=1)
                cur += timedelta(hours=1)

        day_start = timezone.make_aware(datetime.combine(day, time.min))
        horizon_blocked = (
            set()
            if ignore_planning
            else _horizon_blocked_ids(rows, pool_horizon, day_start, now)
        )
        beyond_horizon = bool(available_ids) and available_ids <= horizon_blocked
        if not slot_starts or resource_count == 0 or beyond_horizon:
            days.append({"date": day.isoformat(), "booked_pct": None, "closed": True})
            day += timedelta(days=1)
            continue

        closed_ids = _closed_resource_ids(rows, pool_closed, {day.weekday()})
        capacity = len(slot_starts) * resource_count
        free = 0
        for slot_start, slot_end in slot_starts.items():
            occupied = {
                rid
                for rid, period in items
                if period.lower < slot_end
                and (period.upper is None or period.upper > slot_start)
            }
            slot_blocks = [
                b
                for b in blocks
                if b["period"].lower < slot_end
                and (b["period"].upper is None or b["period"].upper > slot_start)
            ]
            blocked = _blocked_ids(rows, slot_blocks)
            lead_blocked = (
                set()
                if ignore_planning
                else _lead_blocked_ids(rows, pool_lead, slot_start, now)
            )
            free += len(
                available_ids - occupied - blocked - lead_blocked - closed_ids
            )

        booked = capacity - free
        days.append(
            {
                "date": day.isoformat(),
                "booked_pct": round(booked / capacity * 100),
                "closed": False,
            }
        )
        day += timedelta(days=1)
    return days


def closed_days_for_pools(pool_ids, start_date, end_date):
    """ISO dates in [start_date, end_date) on which *every* given pool is closed.

    A pool is closed on a day if that weekday is in its ``closed_weekdays`` or a
    pool-wide block (system-wide or pool-scoped) covers the day. Used to grey out
    non-working days in the lending calendar.
    """
    pool_ids = set(pool_ids)
    if not pool_ids:
        return []

    pool_closed = _pool_closed_map(pool_ids)
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.min))
    # Only pool-wide blocks (system or pool-scoped) close a whole pool.
    blocks = [
        b
        for b in _blocks_overlapping(start_dt, end_dt)
        if b["product_id"] is None and b["resource_id"] is None
    ]

    closed = []
    day = start_date
    while day < end_date:
        day_start = timezone.make_aware(datetime.combine(day, time.min))
        day_end = day_start + timedelta(days=1)
        day_blocks = [
            b
            for b in blocks
            if b["period"].lower < day_end
            and (b["period"].upper is None or b["period"].upper > day_start)
        ]
        system_blocked = any(b["resource_pool_id"] is None for b in day_blocks)
        blocked_pools = {
            b["resource_pool_id"] for b in day_blocks if b["resource_pool_id"] is not None
        }
        all_closed = all(
            system_blocked
            or pid in blocked_pools
            or day.weekday() in pool_closed.get(pid, set())
            for pid in pool_ids
        )
        if all_closed:
            closed.append(day.isoformat())
        day += timedelta(days=1)
    return closed


def _assign_code(booking):
    booking.code = f"R-{booking.id:05d}"


def create_reservation(borrower, items, status=Booking.Status.PENDING):
    """Create a booking with the given items and a reservation number.

    ``items`` is an iterable of ``(resource, start, end)`` tuples. A ``cart``
    booking holds its slots and expires; a ``pending`` one is a submitted
    reservation that does not expire. Raises ``django.db.IntegrityError`` if a
    slot overlaps an existing active booking (the exclusion constraint).
    """
    items = list(items)
    booking = Booking.objects.create(borrower=borrower, status=status)
    _assign_code(booking)
    if status == Booking.Status.CART:
        booking.expires_at = timezone.now() + timedelta(minutes=cart_hold_minutes())
    booking.save(update_fields=["code", "expires_at", "updated_at"])
    for resource, start, end in items:
        BookingItem.objects.create(
            booking=booking,
            resource=resource,
            period=DateTimeTZRange(start, end),
        )
    # A reservation belongs to a single pool (#26); set it when the items
    # created here all share one.
    pool_ids = {resource.resource_pool_id for resource, _start, _end in items}
    if len(pool_ids) == 1:
        booking.resource_pool_id = pool_ids.pop()
        booking.save(update_fields=["resource_pool", "updated_at"])
    return booking


def submit_cart(cart, note=""):
    """Submit a cart as one reservation per pool (#26), linked by ``checkout_id``.

    The first pool (curated order) keeps the cart booking and its number; each
    further pool gets its own booking. Returns the reservations, pool-ordered.
    """
    active = list(
        cart.items.filter(is_active=True)
        .select_related("resource__resource_pool")
        .order_by(
            "resource__resource_pool__position",
            "resource__resource_pool__name",
            "id",
        )
    )
    groups = OrderedDict()
    for item in active:
        groups.setdefault(item.resource.resource_pool, []).append(item)
    checkout_id = uuid.uuid4()
    bookings = []
    with transaction.atomic():
        for index, (pool, items) in enumerate(groups.items()):
            if index == 0:
                booking = cart
                booking.resource_pool = pool
                booking.checkout_id = checkout_id
                booking.save(update_fields=["resource_pool", "checkout_id", "updated_at"])
                booking.submit(note)
            else:
                booking = Booking.objects.create(
                    borrower=cart.borrower, status=Booking.Status.PENDING,
                    note=note, resource_pool=pool, checkout_id=checkout_id,
                )
                _assign_code(booking)
                booking.save(update_fields=["code", "updated_at"])
                BookingItem.objects.filter(id__in=[i.id for i in items]).update(
                    booking=booking
                )
            bookings.append(booking)
    # The first reservation is the caller's cart object, whose prefetched
    # ``items`` (see ``get_active_cart``) still lists the items just moved to
    # the other pools' bookings. Re-fetch all of them so the mail and the
    # response see each reservation's own items only.
    return [_hydrated_cart(booking.pk) for booking in bookings]


def overdue_items(booking, today=None):
    """Return (overdue_pickup_items, overdue_return_items) for a booking.

    An overdue pickup is an item still awaiting handout whose start day has
    passed; an overdue return is an item that is out whose last booked day has
    passed.
    """
    today = today or timezone.localdate()
    pickups, returns = [], []
    if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT):
        return pickups, returns
    for item in booking.items.all():
        if not item.period or item.returned_at:
            continue
        if item.handed_out_at is None:
            start = item.period.lower
            if start and timezone.localtime(start).date() < today:
                pickups.append(item)
        else:
            upper = item.period.upper
            if upper and timezone.localtime(upper - timedelta(microseconds=1)).date() < today:
                returns.append(item)
    return pickups, returns


def get_active_cart(borrower):
    """The borrower's current cart (reaping expired carts first), or None."""
    release_expired_holds()
    return (
        Booking.objects.filter(borrower=borrower, status=Booking.Status.CART)
        .prefetch_related("items__resource__product", "items__resource__resource_pool")
        .first()
    )


def _hydrated_cart(pk):
    """Re-fetch a cart with its items freshly prefetched.

    ``get_active_cart`` prefetches ``items`` at fetch time; adding a BookingItem
    afterwards does not update that cached list, so serializing the same object
    would miss the just-added item. Re-fetch to return an up-to-date cart.
    """
    return (
        Booking.objects.prefetch_related(
            "items__resource__product", "items__resource__resource_pool"
        ).get(pk=pk)
    )


def add_to_cart(borrower, product, start, end, pool_ids=None):
    """Allocate a free resource for [start, end) and add it to the borrower's
    cart, creating the cart (with a reservation number) if needed and renewing
    its hold. Returns the cart. Raises ``ValueError`` if nothing is available.

    ``pool_ids`` (when given) limits allocation to pools the borrower may use.
    """
    cart = get_active_cart(borrower)
    resource = available_resources(product, start, end, pool_ids).first()
    if resource is None:
        raise ValueError("This product is not available in the selected period.")
    with transaction.atomic():
        if cart is None:
            cart = Booking.objects.create(
                borrower=borrower, status=Booking.Status.CART
            )
            _assign_code(cart)
        cart.expires_at = timezone.now() + timedelta(minutes=cart_hold_minutes())
        cart.save(update_fields=["code", "expires_at", "updated_at"])
        BookingItem.objects.create(
            booking=cart, resource=resource, period=DateTimeTZRange(start, end)
        )
    return _hydrated_cart(cart.pk)


def walkin_available_resources(product, pool_id, start, end):
    """Resources of ``product`` in one pool that are free for [start, end).

    Unlike :func:`available_resources`, a walk-in lending (concept §6.4) ignores
    the pool's lead time and booking horizon — the lender is lending in person —
    but it still respects the no-overlap constraint with existing bookings. The
    product's ``min_gap`` is *not* applied here (walk-in stays unbuffered).
    Ordered the same way as :func:`available_resources`: best condition first,
    then longest idle.
    """
    occupied = set(
        _occupying_items(product, start, end).values_list("resource_id", flat=True)
    )
    return (
        Resource.objects.filter(
            product=product,
            resource_pool_id=pool_id,
            status=Resource.Status.AVAILABLE,
        )
        .exclude(id__in=occupied)
        .annotate(last_return=Max("booking_items__returned_at"))
        .order_by("-condition_rating", F("last_return").asc(nulls_first=True), "id")
    )


def walkin_resource_options(product, pool_id, start, end):
    """The product's lendable units in a pool, each flagged for a time conflict.

    Lets the lender pick the exact unit handed out (concept §6.4); ``conflict``
    marks units already booked in [start, end).
    """
    occupied = set(
        _occupying_items(product, start, end).values_list("resource_id", flat=True)
    )
    resources = Resource.objects.filter(
        product=product,
        resource_pool_id=pool_id,
        status=Resource.Status.AVAILABLE,
    ).order_by("inventory_number")
    return [
        {
            "id": r.id,
            "inventory_number": r.inventory_number,
            "conflict": r.id in occupied,
        }
        for r in resources
    ]


def create_walkin_booking(borrower, pool_id, items, hand_out=False, note=""):
    """Lender walk-in lending (concept §6.4): create a booking on a borrower's
    behalf from one pool, bypassing lead time and horizon.

    ``items`` is an iterable of ``(product, start, end, resource)`` where
    ``resource`` is the specific unit the lender hands out, or ``None`` to let
    the system pick a free one. The booking is created ``CONFIRMED`` (a
    reservation held at the desk) or ``HANDED_OUT`` when ``hand_out`` is set.
    All-or-nothing: a product with no free unit, or a chosen unit that isn't
    free, rejects the whole lending with a ``ValueError``.
    """
    items = list(items)
    if not items:
        raise ValueError("Add at least one item.")
    status = Booking.Status.HANDED_OUT if hand_out else Booking.Status.CONFIRMED
    now = timezone.now()
    with transaction.atomic():
        allocations = []
        chosen = set()
        for product, start, end, resource in items:
            if resource is not None:
                conflict = (
                    _occupying_items(product, start, end)
                    .filter(resource_id=resource.id)
                    .exists()
                )
                if (
                    resource.product_id != product.id
                    or resource.resource_pool_id != pool_id
                    or resource.status != Resource.Status.AVAILABLE
                    or resource.id in chosen
                    or conflict
                ):
                    raise ValueError(
                        f"'{resource.inventory_number}' is not available in the "
                        "selected period."
                    )
            else:
                resource = (
                    walkin_available_resources(product, pool_id, start, end)
                    .exclude(id__in=chosen)
                    .first()
                )
                if resource is None:
                    raise ValueError(
                        f"'{product.title}' is not available in the selected period."
                    )
            chosen.add(resource.id)
            allocations.append((resource, start, end))
        booking = Booking.objects.create(
            borrower=borrower, status=status, note=note or "",
            resource_pool_id=pool_id, confirmed_at=now,
        )
        _assign_code(booking)
        booking.save(update_fields=["code", "updated_at"])
        for resource, start, end in allocations:
            BookingItem.objects.create(
                booking=booking,
                resource=resource,
                period=DateTimeTZRange(start, end),
                handed_out_at=now if hand_out else None,
            )
    return booking


def import_holidays(country, subdiv, years, pool=None):
    """Create blocks for public holidays of a country/subdivision.

    Each holiday becomes a one-day block (system-wide, or pool-scoped if
    ``pool`` is given). Idempotent: re-importing the same holidays is a no-op.
    Returns the list of newly created holidays.
    """
    if isinstance(years, int):
        years = [years]
    holiday_calendar = holidays_lib.country_holidays(
        country, subdiv=subdiv or None, years=years
    )

    created = []
    for holiday_date, name in sorted(holiday_calendar.items()):
        start = timezone.make_aware(datetime.combine(holiday_date, time.min))
        period = DateTimeTZRange(start, start + timedelta(days=1))
        _, was_created = Block.objects.get_or_create(
            period=period,
            reason=f"Holiday: {name}",
            resource_pool=pool,
            product=None,
            resource=None,
        )
        if was_created:
            created.append({"date": holiday_date.isoformat(), "name": name})
    return created


def holiday_horizon_months():
    """Months of public holidays to keep loaded: the longest pool horizon."""
    longest = ResourcePool.objects.aggregate(m=Max("max_booking_months"))["m"]
    return longest or 24


def refresh_holidays():
    """Load public holidays for the configured region across the booking horizon.

    Reads the singleton :class:`HolidaySetting` and ensures system-wide holiday
    blocks exist from this year through the end of the longest pool booking
    horizon. Idempotent. Returns the list of newly created holidays.
    """
    setting = HolidaySetting.load()
    if not setting.country:
        return []
    today = timezone.localdate()
    last_day = _add_months(today, holiday_horizon_months())
    years = list(range(today.year, last_day.year + 1))
    return import_holidays(setting.country, setting.subdivision, years)


# Booking statuses that count as real lending demand (cart/cancelled excluded).
_STATS_STATUSES = [
    Booking.Status.PENDING,
    Booking.Status.CONFIRMED,
    Booking.Status.HANDED_OUT,
    Booking.Status.RETURNED,
]


def product_stats(pool_ids, start, end):
    """Per-product lending statistics for [start, end) over the given pools.

    Returns a list (sorted by current bookings desc) of dicts with the product,
    its booking count and reserved hours in the window, the count in the equal
    window immediately before, and the trend (current - previous). Cancelled and
    cart bookings are excluded. Products active only in the previous window are
    included with 0 current bookings so falling trends are visible.
    """
    span = end - start
    base = BookingItem.objects.filter(
        booking__status__in=_STATS_STATUSES,
        resource__resource_pool_id__in=pool_ids,
    )

    # Seed every product with at least one resource in scope, so never-borrowed
    # products are visible too (candidates for retirement).
    products = {
        pid: {
            "id": pid,
            "title": title,
            "lending_type": lending_type,
            "bookings": 0,
            "booked_hours": 0.0,
        }
        for pid, title, lending_type in Product.objects.filter(
            resources__resource_pool_id__in=pool_ids
        )
        .distinct()
        .values_list("id", "title", "lending_type")
    }

    current_rows = base.filter(
        period__overlap=DateTimeTZRange(start, end)
    ).values_list(
        "resource__product_id",
        "resource__product__title",
        "resource__product__lending_type",
        "period",
    )
    previous_rows = base.filter(
        period__overlap=DateTimeTZRange(start - span, start)
    ).values_list(
        "resource__product_id",
        "resource__product__title",
        "resource__product__lending_type",
    )

    for pid, title, lending_type, period in current_rows:
        entry = products.setdefault(
            pid,
            {
                "id": pid,
                "title": title,
                "lending_type": lending_type,
                "bookings": 0,
                "booked_hours": 0.0,
            },
        )
        entry["bookings"] += 1
        lower = max(period.lower, start)
        upper = min(period.upper, end) if period.upper else end
        entry["booked_hours"] += max(0.0, (upper - lower).total_seconds() / 3600)

    previous_counts = defaultdict(int)
    for pid, title, lending_type, *_ in previous_rows:
        previous_counts[pid] += 1
        products.setdefault(
            pid,
            {
                "id": pid,
                "title": title,
                "lending_type": lending_type,
                "bookings": 0,
                "booked_hours": 0.0,
            },
        )

    for pid, entry in products.items():
        entry["booked_hours"] = round(entry["booked_hours"], 1)
        entry["prev_bookings"] = previous_counts.get(pid, 0)
        entry["trend"] = entry["bookings"] - entry["prev_bookings"]

    return sorted(
        products.values(),
        key=lambda e: (-e["bookings"], -e["booked_hours"], e["title"]),
    )


def _bucket_start(day, bucket):
    """Normalise a date to the start of its day/week(Mon)/month bucket."""
    if bucket == "month":
        return day.replace(day=1)
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    return day


def _bucket_next(day, bucket):
    if bucket == "month":
        return _add_months(day, 1)
    if bucket == "week":
        return day + timedelta(days=7)
    return day + timedelta(days=1)


def product_timeseries(product_id, pool_ids, start, end, bucket="week"):
    """How often one product was borrowed per day/week/month in [start, end).

    A booking is counted in the bucket of its pickup (period start). Returns a
    continuous, zero-filled series of ``{"start": iso_date, "bookings": n}``.
    """
    from_date = timezone.localtime(start).date()
    end_date = timezone.localtime(end).date()  # exclusive
    rows = BookingItem.objects.filter(
        booking__status__in=_STATS_STATUSES,
        resource__product_id=product_id,
        resource__resource_pool_id__in=pool_ids,
        period__overlap=DateTimeTZRange(start, end),
    ).values_list("period", flat=True)

    counts = defaultdict(int)
    for period in rows:
        pickup = timezone.localtime(period.lower).date()
        if from_date <= pickup < end_date:
            counts[_bucket_start(pickup, bucket)] += 1

    series = []
    cursor = _bucket_start(from_date, bucket)
    last = end_date - timedelta(days=1)
    while cursor <= last:
        series.append({"start": cursor.isoformat(), "bookings": counts.get(cursor, 0)})
        cursor = _bucket_next(cursor, bucket)
    return series


# Most-recent bookings shown per product in the lending overview.
def lending_tree(pool_ids):
    """Pools → products → resources with per-resource booking counts.

    The tree is bounded by inventory size (no booking history inline); the
    borrowings of a single resource are fetched separately and paginated. Pools
    sort by name, products by booking count (desc), resources by inventory no.
    """
    resources = (
        Resource.objects.filter(resource_pool_id__in=pool_ids)
        .select_related("product", "resource_pool")
        .annotate(
            booking_count=Count(
                "booking_items",
                filter=~Q(booking_items__booking__status=Booking.Status.CART),
            )
        )
        .order_by("resource_pool__name", "product__title", "inventory_number")
    )

    pools = {}
    for resource in resources:
        pool = resource.resource_pool
        product = resource.product
        pool_entry = pools.setdefault(
            pool.id, {"id": pool.id, "name": pool.name, "_products": {}}
        )
        product_entry = pool_entry["_products"].setdefault(
            product.id,
            {"id": product.id, "title": product.title, "booking_count": 0, "resources": []},
        )
        product_entry["resources"].append(
            {
                "id": resource.id,
                "inventory_number": resource.inventory_number,
                "status": resource.status,
                "booking_count": resource.booking_count,
            }
        )
        product_entry["booking_count"] += resource.booking_count

    result = []
    for pool_entry in sorted(pools.values(), key=lambda p: p["name"]):
        products = sorted(
            pool_entry["_products"].values(),
            key=lambda pr: (-pr["booking_count"], pr["title"]),
        )
        result.append(
            {"id": pool_entry["id"], "name": pool_entry["name"], "products": products}
        )
    return result


def mark_resource_defective(resource, note=""):
    """Flag a resource defective and rebook its upcoming bookings (concept §3.6).

    Future/ongoing, not-yet-returned bookings on the resource are moved to a
    free unit of the same product in the same pool where stock allows; borrowers
    whose bookings can't be moved are notified. Returns counts of what happened.
    """
    from .notifications import send_defect_notice, send_defect_pool_notice

    now = timezone.now()
    blocking = [
        Booking.Status.CART,
        Booking.Status.CANCELLED,
        Booking.Status.RETURNED,
    ]
    unfulfilled_by_booking = {}
    rebooked = 0
    with transaction.atomic():
        resource.status = Resource.Status.DEFECTIVE
        resource.defect_note = note
        resource.save(update_fields=["status", "defect_note", "updated_at"])

        affected = list(
            resource.booking_items.filter(
                is_active=True,
                returned_at__isnull=True,
                period__overlap=DateTimeTZRange(now, None),
            )
            .exclude(booking__status__in=blocking)
            .select_related("booking__borrower", "resource__resource_pool")
        )
        for item in affected:
            occupied = (
                BookingItem.objects.filter(
                    resource__product=resource.product,
                    resource__resource_pool=resource.resource_pool,
                    is_active=True,
                    period__overlap=item.period,
                )
                .exclude(pk=item.pk)
                .values_list("resource_id", flat=True)
            )
            candidate = (
                Resource.objects.filter(
                    product=resource.product,
                    resource_pool=resource.resource_pool,
                    status=Resource.Status.AVAILABLE,
                )
                .exclude(id__in=list(occupied))
                .first()
            )
            if candidate:
                item.resource = candidate
                item.save(update_fields=["resource"])
                rebooked += 1
            else:
                unfulfilled_by_booking.setdefault(
                    item.booking_id, (item.booking, [])
                )[1].append(item)

    # Notify the pool's contact (opt-in per pool) that a device went defective,
    # and — if the pool has a GitLab project configured — open a tracking issue.
    send_defect_pool_notice(resource, note)
    from .gitlab_service import create_defect_issue

    issue_url = create_defect_issue(resource.resource_pool, resource, note)
    if issue_url:
        # Record the link on the open defect so the lending desk can jump to it.
        # The signal guarantees a single open record per resource.
        ResourceDefect.objects.filter(
            resource=resource, resolved_at__isnull=True
        ).update(gitlab_issue_url=issue_url)

    unfulfilled = 0
    for booking, items in unfulfilled_by_booking.values():
        unfulfilled += len(items)
        send_defect_notice(booking, items)
    return {"rebooked": rebooked, "unfulfilled": unfulfilled}


def _rebook_missing_item(item):
    """Move ``item`` onto a free alternative unit of the same product/pool
    (best condition, longest idle first). Returns True on success."""
    occupied = (
        BookingItem.objects.filter(
            resource__product=item.resource.product,
            resource__resource_pool=item.resource.resource_pool,
            is_active=True,
            period__overlap=item.period,
        )
        .exclude(pk=item.pk)
        .values_list("resource_id", flat=True)
    )
    candidate = (
        Resource.objects.filter(
            product=item.resource.product,
            resource_pool=item.resource.resource_pool,
            status=Resource.Status.AVAILABLE,
        )
        .exclude(id__in=list(occupied))
        .exclude(id=item.resource_id)
        .annotate(last_return=Max("booking_items__returned_at"))
        .order_by("-condition_rating", F("last_return").asc(nulls_first=True), "id")
        .first()
    )
    if not candidate:
        return False
    try:
        with transaction.atomic():
            item.resource = candidate
            item.save(update_fields=["resource"])
        return True
    except IntegrityError:
        return False


def notify_missing_products(dry_run=False):
    """Warn upcoming borrowers whose assigned unit is still out (overdue prior
    holder) and can't be rebooked (issue #48). Tries to rebook onto a free unit
    first; otherwise sends one notice per booking and marks the items. The
    booking is kept (the holder may still return). Idempotent.

    In ``dry_run`` mode rebooking is intentionally skipped (it mutates), so the
    reported counts assume no rebooking: ``notified`` overstates, and
    ``rebooked`` (always 0) understates, what a real run would do — items a real
    run would silently rebook are counted as notices here."""
    from .notifications import send_missing_product_notice

    now = timezone.now()
    active = [Booking.Status.CONFIRMED, Booking.Status.PENDING]
    candidates = (
        BookingItem.objects.filter(
            is_active=True,
            handed_out_at__isnull=True,
            returned_at__isnull=True,
            missing_notified_at__isnull=True,
            booking__status__in=active,
            period__overlap=DateTimeTZRange(now, None),
        )
        .select_related(
            "booking__borrower", "resource__product", "resource__resource_pool"
        )
    )
    notify_by_booking = {}
    rebooked = 0
    for item in candidates:
        lead = missing_lead_delta(item.resource.product)
        if not lead:
            continue
        pickup = item.period.lower
        if pickup is None or now >= pickup or now < pickup - lead:
            continue  # outside the notice window (too early, or pickup passed)
        # "Still out" means another active item on this resource was handed out,
        # never returned, AND is already OVERDUE — its booked period ended at or
        # before now. A holder still within their period is on time (expected
        # back before this pickup), not missing. An active handed-out item can
        # never share a period with `item` (the no-overlap exclusion constraint
        # forbids two overlapping active bookings on the same resource), so the
        # blocker is always an earlier, non-overlapping booking; the overdue
        # test (`period.upper <= now`) is what distinguishes a genuinely late
        # return from a normal sequential loan that isn't due yet.
        still_out = (
            BookingItem.objects.filter(
                resource=item.resource,
                is_active=True,
                handed_out_at__isnull=False,
                returned_at__isnull=True,
                period__endswith__lte=now,
            )
            .exclude(pk=item.pk)
            .exists()
        )
        if not still_out:
            continue
        # In dry-run mode do NOT call _rebook_missing_item (it mutates); just
        # count what would be notified.
        if not dry_run and _rebook_missing_item(item):
            rebooked += 1
            continue
        notify_by_booking.setdefault(item.booking_id, (item.booking, []))[1].append(item)

    notified = 0
    if not dry_run:
        for booking, items in notify_by_booking.values():
            send_missing_product_notice(booking, items)
            BookingItem.objects.filter(
                pk__in=[i.pk for i in items]
            ).update(missing_notified_at=now)
            notified += len(items)
    else:
        notified = sum(len(v[1]) for v in notify_by_booking.values())
    return {"rebooked": rebooked, "notified": notified}


def _next_open_day(pool_id, from_day, max_days=400):
    """First day >= ``from_day`` on which the pool is open (not a closed weekday
    and not covered by a pool-wide/system block). ``None`` if none within range."""
    horizon = from_day + timedelta(days=max_days)
    closed = set(closed_days_for_pools([pool_id], from_day, horizon))
    day = from_day
    while day < horizon:
        if day.isoformat() not in closed:
            return day
        day += timedelta(days=1)
    return None


def _plan_block_item(item):
    """Decide what a newly-created closure does to one affected booking item.

    Returns ``("unchanged", None)``, ``("move", new_period)`` or
    ``("cancel", None)``. Day bookings shift a blocked pickup/return day to the
    next open day (mid-loan closures stay put); an hourly (single-day) booking
    on a blocked day, or a day booking with no open day left, is cancelled.
    """
    pool_id = item.resource.resource_pool_id
    if item.resource.product.lending_type != Product.LendingType.DAYS:
        return "cancel", None

    first_day = timezone.localtime(item.period.lower).date()
    last_day = timezone.localtime(item.period.upper - timedelta(microseconds=1)).date()
    closed = set(closed_days_for_pools([pool_id], first_day, last_day + timedelta(days=1)))
    booked = [first_day + timedelta(days=n) for n in range((last_day - first_day).days + 1)]
    if all(d.isoformat() in closed for d in booked):
        return "cancel", None

    new_first = _next_open_day(pool_id, first_day)
    new_last = _next_open_day(pool_id, last_day)
    if new_first is None or new_last is None or new_first > new_last:
        return "cancel", None
    if new_first == first_day and new_last == last_day:
        return "unchanged", None
    new_period = DateTimeTZRange(
        timezone.make_aware(datetime.combine(new_first, time.min)),
        timezone.make_aware(datetime.combine(new_last + timedelta(days=1), time.min)),
    )
    return "move", new_period


def _move_item(item, new_period):
    """Move ``item`` to ``new_period`` on the same unit, or onto a free unit of
    the same product/pool. Returns True on success, False if no slot is free."""
    try:
        with transaction.atomic():
            item.period = new_period
            item.save(update_fields=["period"])
        return True
    except IntegrityError:
        pass  # the unit is taken for the new period — look for another one
    occupied = (
        BookingItem.objects.filter(
            resource__product=item.resource.product,
            resource__resource_pool=item.resource.resource_pool,
            is_active=True,
            period__overlap=new_period,
        )
        .exclude(pk=item.pk)
        .values_list("resource_id", flat=True)
    )
    candidate = (
        Resource.objects.filter(
            product=item.resource.product,
            resource_pool=item.resource.resource_pool,
            status=Resource.Status.AVAILABLE,
        )
        .exclude(id__in=list(occupied))
        .exclude(id=item.resource_id)
        .first()
    )
    if not candidate:
        return False
    try:
        with transaction.atomic():
            item.resource = candidate
            item.period = new_period
            item.save(update_fields=["resource", "period"])
        return True
    except IntegrityError:
        return False


def apply_block_to_bookings(block):
    """Adjust existing bookings when a new closure (``block``) is created.

    Per booking (boundary-shift): a blocked pickup day moves the pickup to the
    next open day, a blocked return (last) day moves the return to the next open
    day; if a shifted day clashes with the unit, a free unit of the same
    product/pool is used, else the booking is cancelled. Single-day/hourly
    bookings on the blocked day are cancelled. Borrowers are emailed. Returns
    ``{"rescheduled": n, "cancelled": n}`` (booking counts).
    """
    from .notifications import send_booking_cancelled_closure, send_booking_rescheduled

    active = [Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT]
    block_row = {
        "resource_id": block.resource_id,
        "product_id": block.product_id,
        "resource_pool_id": block.resource_pool_id,
    }
    reschedule_out, cancel_out = [], []

    with transaction.atomic():
        items = list(
            BookingItem.objects.filter(
                is_active=True,
                returned_at__isnull=True,
                booking__status__in=active,
                period__overlap=block.period,
            ).select_related(
                "booking__borrower", "resource__product", "resource__resource_pool"
            )
        )
        rows = [(i.resource_id, i.resource.product_id, i.resource.resource_pool_id) for i in items]
        scoped = _blocked_ids(rows, [block_row])
        by_booking = defaultdict(list)
        for item in items:
            if item.resource_id in scoped:
                by_booking[item.booking].append(item)

        for booking, bitems in by_booking.items():
            plan, must_cancel = [], False
            for item in bitems:
                action, new_period = _plan_block_item(item)
                if action == "cancel":
                    must_cancel = True
                    break
                if action == "move":
                    plan.append((item, item.period, new_period))
            if must_cancel:
                cancel_out.append((booking, bitems))
                continue
            if not plan:
                continue  # mid-loan closure — nothing changes
            sid = transaction.savepoint()
            changes, ok = [], True
            for item, old_period, new_period in plan:
                if _move_item(item, new_period):
                    changes.append((item, old_period, new_period))
                else:
                    ok = False
                    break
            if ok:
                transaction.savepoint_commit(sid)
                reschedule_out.append((booking, changes))
            else:
                transaction.savepoint_rollback(sid)
                cancel_out.append((booking, bitems))

        for booking, _bitems in cancel_out:
            booking.cancel()

    for booking, changes in reschedule_out:
        send_booking_rescheduled(booking, changes, block)
    for booking, bitems in cancel_out:
        send_booking_cancelled_closure(booking, bitems, block)
    return {"rescheduled": len(reschedule_out), "cancelled": len(cancel_out)}


def defect_stats(pool_ids):
    """Defect statistics over the given pools (concept §3.6 reporting).

    Returns overall counts plus a per-product breakdown of defect incidents,
    sorted by incident count (which products break most), for procurement.
    """
    resources = Resource.objects.filter(resource_pool_id__in=pool_ids)
    incidents = ResourceDefect.objects.filter(
        resource__resource_pool_id__in=pool_ids
    )

    incidents_by_product = defaultdict(int)
    resources_by_product = defaultdict(set)
    titles = {}
    for pid, title, rid in incidents.values_list(
        "resource__product_id", "resource__product__title", "resource_id"
    ):
        incidents_by_product[pid] += 1
        resources_by_product[pid].add(rid)
        titles[pid] = title

    current_by_product = defaultdict(int)
    for pid in resources.filter(status=Resource.Status.DEFECTIVE).values_list(
        "product_id", flat=True
    ):
        current_by_product[pid] += 1

    products = [
        {
            "id": pid,
            "title": titles[pid],
            "incidents": incidents_by_product[pid],
            "defective_resources": len(resources_by_product[pid]),
            "currently_defective": current_by_product.get(pid, 0),
        }
        for pid in incidents_by_product
    ]
    products.sort(key=lambda p: (-p["incidents"], p["title"]))

    return {
        "resources_total": resources.count(),
        "currently_defective": resources.filter(
            status=Resource.Status.DEFECTIVE
        ).count(),
        "ever_defective": resources.filter(defects__isnull=False).distinct().count(),
        "incidents": incidents.count(),
        "products": products,
    }


def _set_product_period(product, start, end):
    """Per-product period for a set booking: hourly products use [start, end];
    daily products round up to the whole day(s) the span touches (concept §4.5)."""
    if product.lending_type == Product.LendingType.DAYS:
        first = timezone.localtime(start).date()
        last = timezone.localtime(end - timedelta(microseconds=1)).date()
        s = timezone.make_aware(datetime.combine(first, time.min))
        e = timezone.make_aware(datetime.combine(last + timedelta(days=1), time.min))
        return s, e
    return start, end


def set_availability(product_set, start, end):
    """Availability of a set in its pool — limited by the scarcest product."""
    pool_id = product_set.resource_pool_id
    rows = []
    for product in product_set.products.all():
        p_start, p_end = _set_product_period(product, start, end)
        rows.append(
            {
                "id": product.id,
                "title": product.title,
                "total": _available_base(product, {pool_id}).count(),
                "available": available_resources(
                    product, p_start, p_end, {pool_id}
                ).count(),
            }
        )
    available = min((r["available"] for r in rows), default=0)
    scarcest = min(rows, key=lambda r: r["available"]) if rows else None
    return {
        "available": available,
        "products": rows,
        "scarcest": scarcest["title"] if scarcest and available == 0 else None,
    }


def add_set_to_cart(borrower, product_set, start, end):
    """Add every product of a set to the cart from its pool (concept §4.5).

    All-or-nothing: if any product is unavailable, nothing is added and the
    scarce product is named in the error.
    """
    pool_id = product_set.resource_pool_id
    products = list(product_set.products.all())
    if not products:
        raise ValueError("This set is empty.")
    cart = get_active_cart(borrower)
    with transaction.atomic():
        allocations = []
        for product in products:
            p_start, p_end = _set_product_period(product, start, end)
            resource = available_resources(
                product, p_start, p_end, {pool_id}
            ).first()
            if resource is None:
                raise ValueError(
                    f"'{product.title}' is not available in the selected period."
                )
            allocations.append((resource, p_start, p_end))
        if cart is None:
            cart = Booking.objects.create(
                borrower=borrower, status=Booking.Status.CART
            )
            _assign_code(cart)
        cart.expires_at = timezone.now() + timedelta(minutes=cart_hold_minutes())
        cart.save(update_fields=["code", "expires_at", "updated_at"])
        for resource, p_start, p_end in allocations:
            BookingItem.objects.create(
                booking=cart, resource=resource,
                period=DateTimeTZRange(p_start, p_end),
            )
    return _hydrated_cart(cart.pk)


def set_availability_per_day(product_set, start_date, end_date):
    """Per-day set availability (min over products) for a daily set's calendar."""
    pool_id = product_set.resource_pool_id
    products = list(product_set.products.all())
    if pool_id is None or not products:
        return []
    per_product = [
        availability_per_day(p, start_date, end_date, {pool_id}) for p in products
    ]
    days = []
    for i in range(len(per_product[0])):
        cells = [pp[i] for pp in per_product]
        days.append(
            {
                "date": cells[0]["date"],
                "available": min(c["available"] for c in cells),
                "total": min(c["total"] for c in cells),
                "closed": any(c["closed"] for c in cells),
            }
        )
    return days


def set_hourly_utilization_per_day(product_set, start_date, end_date):
    """Per-day booked% for a set's hourly month grid (the busiest product drives)."""
    pool_id = product_set.resource_pool_id
    products = list(product_set.products.all())
    if pool_id is None or not products:
        return []
    hourly = [
        hourly_utilization_per_day(p, start_date, end_date, {pool_id})
        for p in products
        if p.lending_type == Product.LendingType.HOURS
    ]
    daily = [
        availability_per_day(p, start_date, end_date, {pool_id})
        for p in products
        if p.lending_type == Product.LendingType.DAYS
    ]
    length = len(hourly[0]) if hourly else (len(daily[0]) if daily else 0)
    days = []
    for i in range(length):
        date = (hourly[0] if hourly else daily[0])[i]["date"]
        pcts, closed = [], False
        for series in hourly:
            cell = series[i]
            if cell["closed"]:
                closed = True
            elif cell["booked_pct"] is not None:
                pcts.append(cell["booked_pct"])
        for series in daily:
            cell = series[i]
            if cell["closed"]:
                closed = True
            elif cell["total"]:
                pcts.append(round((cell["total"] - cell["available"]) / cell["total"] * 100))
        booked = max(pcts) if pcts else None
        days.append(
            {"date": date, "booked_pct": None if closed else booked, "closed": closed}
        )
    return days


def set_availability_per_hour(product_set, date):
    """Per-hour set availability for the hour grid: hourly products by the hour,
    daily products floored by their whole-day availability (concept §4.5)."""
    pool_id = product_set.resource_pool_id
    products = list(product_set.products.all())
    hourly_products = [p for p in products if p.lending_type == Product.LendingType.HOURS]
    daily_products = [p for p in products if p.lending_type == Product.LendingType.DAYS]
    if pool_id is None or not hourly_products:
        return []

    # Whole-day floor from the daily products of the set on this date.
    day_floor_avail = None
    day_floor_total = None
    if daily_products:
        on_date = availability_on_date(
            [p.id for p in daily_products], date, {pool_id}
        )
        day_floor_avail = min(v["available"] for v in on_date.values())
        day_floor_total = min(v["total"] for v in on_date.values())

    per = [availability_per_hour(p, date, {pool_id}) for p in hourly_products]
    by_start = {}
    for slots in per:
        for slot in slots:
            by_start.setdefault(slot["start"], []).append(slot)

    result = []
    for start in sorted(by_start):
        group = by_start[start]
        if len(group) < len(per):
            continue  # not open in every hourly product
        available = min(s["available"] for s in group)
        total = min(s["total"] for s in group)
        if daily_products:
            available = min(available, day_floor_avail)
            total = min(total, day_floor_total)
        sample = group[0]
        result.append(
            {
                "start": sample["start"],
                "end": sample["end"],
                "label": sample["label"],
                "available": available,
                "total": total,
            }
        )
    return result
