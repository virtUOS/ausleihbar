# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""What a room's door sign shows: a pure data model (no rendering).

``build_door_view`` turns the state of the places in a room into a
``DoorView``; later layers turn it into button sessions and pixels. Every
name goes through ``privacy`` with the public viewer (``viewer=None``).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from . import checkin, door_actions, hours, overview, privacy, qr, release
from .models import DeskSettings, Place

# User-facing literals (German UI of the sign).
LABEL_HIDDEN = "belegt"
LABEL_FREE = "frei"
TITLE_ANONYMOUS = "Spontan belegt"
FREE_NOTE = "ab {time} gebucht"

UNTIL_LIMIT = timedelta(hours=5)
WAKE_OPEN = 300
WAKE_MAX = 14400
WAKE_MIN = 60
WAKE_LEAD = timedelta(minutes=5)
SCHEDULE_MAX = 6


@dataclass
class DeskTile:
    place_id: int
    name: str
    state: str  # free | booked | checked_in | potentially_free | closed
    label: str | None
    until: datetime | None
    free_note: str | None
    reservation_id: int | None
    actionable: str | None  # "check_in" | "check_out" | None
    qr_url: str


@dataclass
class MeetingSlot:
    start: datetime
    end: datetime
    label: str


@dataclass
class MeetingInfo:
    state: str
    title: str | None
    holder: str | None
    start: datetime | None
    end: datetime | None
    free_until: datetime | None
    next_label: str | None
    release_at: datetime | None
    reservation_id: int | None
    max_hours: int
    schedule: list[MeetingSlot] = field(default_factory=list)


@dataclass
class DoorView:
    room_name: str
    kind: str  # meeting | office | single | empty | closed
    now: datetime
    desks: list[DeskTile]
    meeting: MeetingInfo | None
    free_count: int
    total: int
    room_qr_url: str | None
    next_wake: int


def _is_open(pool, now) -> bool:
    if pool is None:
        return False
    local = timezone.localtime(now, hours.TZ)
    open_hours = hours.business_hours(pool, local.date())
    return (
        open_hours is not None
        and open_hours[0] <= local.hour < open_hours[1]
        and local.hour not in hours.closed_hours(pool, local.date())
    )


def next_wake_seconds(pool, now) -> int:
    """Seconds until the sign should wake: 300 while open, otherwise until
    5 minutes before the next opening (capped at 4 h, at least 60 s)."""
    if pool is None:
        return WAKE_MAX
    if _is_open(pool, now):
        return WAKE_OPEN
    local = timezone.localtime(now, hours.TZ)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        open_hours = hours.business_hours(pool, day)
        if open_hours is None:
            continue
        closed = hours.closed_hours(pool, day)
        for hour in range(*open_hours):
            if hour in closed:
                continue
            opening = hours.local_dt(day, hour)
            if opening > now:
                # Compare in UTC: aware wall-clock arithmetic ignores DST shifts.
                seconds = int(
                    (opening.astimezone(dt_timezone.utc) - WAKE_LEAD - now.astimezone(dt_timezone.utc))
                    .total_seconds()
                )
                return max(WAKE_MIN, min(WAKE_MAX, seconds))
            break
    return WAKE_MAX


def _parse(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso) if iso else None


def _local(dt: datetime) -> datetime:
    return timezone.localtime(dt, hours.TZ)


def _current(rows, now):
    return next((r for r in rows if r.period.lower <= now < r.period.upper), None)


def _upcoming(rows, now):
    return next((r for r in rows if r.period.lower > now), None)


def _actionable(res, now) -> str | None:
    if res is None:
        return None
    if res.checked_in_at is not None:
        return "check_out" if res.period.lower <= now else None
    return "check_in" if checkin._window_open(res, now) else None


def _desk_tile(place, ctx, now) -> DeskTile:
    status = overview._status_from(place, now, ctx, viewer=None, anonymous=False)
    state = status["state"]
    rows = ctx.rows.get(place.pk, [])
    current = _current(rows, now) if state != "closed" else None
    candidate = current
    if candidate is None and state != "closed":
        nxt = _upcoming(rows, now)
        if nxt is not None and checkin._window_open(nxt, now):
            candidate = nxt
    label = None
    until = None
    if state not in ("free", "closed"):
        label = status["holder"] or LABEL_HIDDEN
        until = _parse(status["until"])
        if until is not None and until - now >= UNTIL_LIMIT:
            until = None
    free_note = None
    if state == "free" and status["next"]:
        start = _local(_parse(status["next"]["start"]))
        free_note = FREE_NOTE.format(time=f"{start:%H:%M}")
    return DeskTile(
        place_id=place.pk,
        name=place.name,
        state=state,
        label=label,
        until=until,
        free_note=free_note,
        reservation_id=candidate.pk if candidate is not None else None,
        actionable=_actionable(candidate, now),
        qr_url=qr.place_qr_url(place),
    )


def _slot_label(res) -> str:
    if res.display_id:
        return TITLE_ANONYMOUS
    return (
        privacy.comment_for(res, viewer=None)
        or privacy.holder_label(res, viewer=None)
        or LABEL_HIDDEN
    )


def _schedule(rows, ctx, current, now) -> list[MeetingSlot]:
    cursor = current.period.upper if current else _local(now).replace(
        minute=0, second=0, microsecond=0
    )
    slots: list[MeetingSlot] = []
    for res in rows:
        if res.period.lower < cursor or res is current or res.period.lower <= now:
            continue
        if res.period.lower > cursor:
            slots.append(MeetingSlot(cursor, res.period.lower, LABEL_FREE))
        slots.append(MeetingSlot(res.period.lower, res.period.upper, _slot_label(res)))
        cursor = res.period.upper
    if slots and ctx.open_hours:
        end = hours.local_dt(ctx.day, ctx.open_hours[1])
        if cursor < end:
            slots.append(MeetingSlot(cursor, end, LABEL_FREE))
    return slots[:SCHEDULE_MAX]


def _meeting_info(place, ctx, now) -> MeetingInfo:
    status = overview._status_from(place, now, ctx, viewer=None, anonymous=False)
    state = status["state"]
    rows = ctx.rows.get(place.pk, [])
    current = _current(rows, now) if state != "closed" else None
    nxt = _upcoming(rows, now)
    candidate = current
    if candidate is None and state != "closed" and nxt is not None and checkin._window_open(nxt, now):
        candidate = nxt
    title = holder = start = end = release_at = free_until = next_label = None
    if current is not None:
        title = _slot_label(current) if (current.display_id or current.comment) else None
        holder = privacy.holder_label(current, viewer=None)
        start, end = current.period.lower, current.period.upper
        if current.checked_in_at is None:
            settings_ = DeskSettings.for_pool(place.pool)
            base = max(start, current.late_until) if current.late_until else start
            scarce = release.is_scarce(place.pool, place.kind, now, settings_)
            grace = settings_.room_grace_short_min if scarce else settings_.room_grace_normal_min
            release_at = base + timedelta(minutes=grace)
    elif state == "free":
        free_until = _parse(status["until"])
    if nxt is not None and state != "closed":
        next_label = (
            f"{_local(nxt.period.lower):%H:%M}–{_local(nxt.period.upper):%H:%M} {_slot_label(nxt)}"
        )
    return MeetingInfo(
        state=state,
        title=title,
        holder=holder,
        start=start,
        end=end,
        free_until=free_until,
        next_label=next_label,
        release_at=release_at,
        reservation_id=candidate.pk if candidate is not None else None,
        max_hours=door_actions.max_anonymous_hours(place, now),
        schedule=_schedule(rows, ctx, current, now),
    )


def build_door_view(room, *, panel: str, now: datetime) -> DoorView:
    """The model of ``room``'s door sign at ``now``. Loads the day once per
    department (places of a mixed room may belong to another one)."""
    places = list(
        Place.objects.filter(
            room=room, is_active=True, room__is_active=True, room__floor__is_active=True,
            pool__isnull=False,
        )
        .select_related("pool", "room__floor__building", "fixed_owner")
        .order_by("name", "pk")
    )
    pool = room.pool
    wake = next_wake_seconds(pool, now)

    def result(kind, desks=(), meeting=None, free=0, total=0, room_qr=None):
        return DoorView(
            room_name=room.name, kind=kind, now=now, desks=list(desks), meeting=meeting,
            free_count=free, total=total, room_qr_url=room_qr, next_wake=wake,
        )

    if not places:
        return result("empty")
    if not _is_open(pool, now):
        return result("closed", total=len(places))

    day = _local(now).date()
    ctxs = {}
    for place in places:
        ctxs.setdefault(place.pool_id, (place.pool, []))[1].append(place)
    loaded = {
        pool_id: overview._load_day(p, day, group) for pool_id, (p, group) in ctxs.items()
    }

    meeting_place = next((p for p in places if p.kind == Place.Kind.MEETING_ROOM), None)
    if meeting_place is not None:
        info = _meeting_info(meeting_place, loaded[meeting_place.pool_id], now)
        return result("meeting", meeting=info, free=int(info.state == "free"), total=1)

    tiles = [_desk_tile(p, loaded[p.pool_id], now) for p in places]
    free = sum(1 for t in tiles if t.state == "free")
    kind = "single" if len(tiles) == 1 else "office"
    room_qr = qr.room_qr_url(room) if kind == "office" and free > 0 else None
    return result(kind, desks=tiles, free=free, total=len(tiles), room_qr=room_qr)
