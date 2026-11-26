# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""What an item's door sign shows: a pure data model (no rendering).

``build_item_view`` turns today's bookings of one lendable unit into an
``ItemView`` (spec §6.5); ``door_render_layouts.item_small`` / ``item_wide``
draw it. The sign is public: it carries times and booking codes only —
never the borrower, the booking note or any other person data (the query
does not even join the borrower).
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from catalog.models import Resource
from lending import checkin, opening
from lending.models import Block, BookingItem

from .door_view import WAKE_LEAD, WAKE_MAX, WAKE_MIN, WAKE_OPEN
from .hours import TZ

UPCOMING_MAX = 3
OUT_OF_SERVICE = (Resource.Status.BLOCKED, Resource.Status.DEFECTIVE)


@dataclass
class ItemSlot:
    start: datetime
    end: datetime
    code: str


@dataclass
class ItemView:
    title: str
    inventory_number: str
    state: str  # free | reserved | late | in_use | closed | out_of_service
    now: datetime
    slot: ItemSlot | None
    late_minutes: int | None
    release_at: datetime | None
    next_start: datetime | None
    next_open: datetime | None
    upcoming: list[ItemSlot] = field(default_factory=list)
    next_wake: int = WAKE_OPEN


def _seconds(later, now) -> int:
    # Compare in UTC: aware wall-clock arithmetic ignores DST shifts.
    delta = later.astimezone(dt_timezone.utc) - now.astimezone(dt_timezone.utc)
    return math.ceil(delta.total_seconds())


def _today(now):
    day = timezone.localtime(now, TZ).date()
    start = datetime.combine(day, time.min, tzinfo=TZ)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ)
    return start, end


def _items(resource, now):
    """Today's items that hold the unit and haven't ended (period order)."""
    day_start, day_end = _today(now)
    items = list(
        BookingItem.objects.filter(
            resource=resource,
            is_active=True,
            returned_at__isnull=True,
            booking__status__in=checkin.HOLDING_STATUSES,
            period__overlap=(day_start, day_end),
            period__endswith__gt=now,
        )
        .select_related("booking")
        .order_by("period")
    )
    for item in items:
        item.resource = resource  # deadline() reads the product, no extra query
    return items, day_end


def _slot(item) -> ItemSlot:
    return ItemSlot(item.period.lower, item.period.upper, item.booking.code)


def _awaits_checkin(item) -> bool:
    return item.checkin_required and item.checked_in_at is None and item.handed_out_at is None


def _resource_blocked(resource, now) -> bool:
    return Block.objects.filter(resource=resource, period__contains=now).exists()


def _next_wake(pool, now, is_open, items) -> int:
    if is_open:
        wake = WAKE_OPEN
    else:
        opening_at = opening.next_opening(pool, now)
        wake = WAKE_MAX if opening_at is None else _seconds(opening_at - WAKE_LEAD, now)
    for item in items:
        start, end = item.period.lower, item.period.upper
        moments = [start - checkin.CHECKIN_EARLY, start, end]
        if _awaits_checkin(item):
            moments.append(checkin.deadline(item))
        for moment in moments:
            if moment is not None and moment > now:
                wake = min(wake, _seconds(moment, now))
    return max(WAKE_MIN, min(WAKE_MAX, wake))


def build_item_view(resource, *, now: datetime) -> ItemView:
    pool = resource.resource_pool
    items, day_end = _items(resource, now)
    is_open = opening.is_open(pool, now)
    running = next((i for i in items if i.period.lower <= now), None)
    later = [i for i in items if i.period.lower > now and i.period.lower < day_end]
    soon = next(
        (i for i in later if i.period.lower - checkin.CHECKIN_EARLY <= now), None
    )

    slot = late = release_at = next_start = next_open = None
    if resource.status in OUT_OF_SERVICE or _resource_blocked(resource, now):
        state = "out_of_service"
    elif running is not None:
        slot = _slot(running)
        if _awaits_checkin(running):
            state = "late"
            late = checkin.late_minutes(running, now)
            release_at = checkin.deadline(running)
        else:
            state = "in_use"
    elif soon is not None:
        state, slot = "reserved", _slot(soon)
    elif not is_open:
        state = "closed"
        next_open = opening.next_opening(pool, now)
    else:
        state = "free"
        next_start = later[0].period.lower if later else None

    upcoming = [
        _slot(i) for i in later if slot is None or i.period.lower != slot.start
    ][:UPCOMING_MAX]
    return ItemView(
        title=resource.product.title,
        inventory_number=resource.inventory_number,
        state=state,
        now=now,
        slot=slot,
        late_minutes=late,
        release_at=release_at,
        next_start=next_start,
        next_open=next_open,
        upcoming=upcoming,
        next_wake=_next_wake(pool, now, is_open, items),
    )
