# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Department overview, "free now", "who sits with me" and the per-place
status (used by displays in spec 3). Every name goes through ``privacy``."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from . import absences, booking, hours, privacy, rights
from .models import Floor, Place, Reservation, Room

STATES = ("free", "booked", "potentially_free", "checked_in", "closed")


def pool_floors(pool):
    """Active floors holding places of ``pool`` (floors are campus-wide)."""
    return Floor.objects.filter(
        Exists(Place.objects.filter(room__floor=OuterRef("pk"), pool=pool)), is_active=True
    )


def _active_places(pool):
    return (
        Place.objects.filter(
            pool=pool, is_active=True, room__is_active=True,
            room__floor__is_active=True,
        )
        .select_related("pool", "room__floor__building", "fixed_owner")
        .prefetch_related("features", "access_groups")
        .order_by("room__floor__building__code", "room__floor__position", "room__name", "name", "pk")
    )


def floor_location(floor) -> dict:
    """Position and building of a floor for the location picker
    (select_related ``building``)."""
    b = floor.building if floor.building_id else None
    return {
        "position": floor.position,
        "building_id": floor.building_id,
        "building": b.code if b else "",
        "building_description": b.description if b else "",
    }


def _reservation_state(res) -> str:
    if res.checked_in_at is not None:
        return "checked_in"
    if res.potentially_free_at is not None:
        return "potentially_free"
    return "booked"


def _iso(dt):
    """Local (Europe/Berlin) ISO time."""
    return timezone.localtime(dt, hours.TZ).isoformat() if dt else None


@dataclass
class _Day:
    """Everything the place states of one department day need, loaded with
    a fixed number of queries whatever the number of places."""

    day: date
    open_hours: tuple[int, int] | None
    closed: set[int]
    # Active reservations per place overlapping the day, ordered by start.
    rows: dict[int, list[Reservation]] = field(default_factory=dict)
    # Fixed owners absent the whole day / opted out of being named.
    absent: set[int] = field(default_factory=set)
    hidden: set[int] = field(default_factory=set)


def _load_day(pool, day: date, places) -> _Day:
    open_hours = hours.business_hours(pool, day)
    ctx = _Day(day, open_hours, hours.closed_hours(pool, day) if open_hours else set())
    for res in (
        Reservation.objects.filter(
            place__in=[p.pk for p in places], status=Reservation.Status.ACTIVE,
            period__overlap=hours.local_range(day, 0, 24),
        )
        .select_related("holder", "place__room__floor__building")
        .order_by("period", "pk")
    ):
        ctx.rows.setdefault(res.place_id, []).append(res)
    owners = {p.fixed_owner_id for p in places if p.fixed_owner_id}
    if owners:
        ctx.absent = absences.fully_absent_user_ids(owners, hours.local_range(day, 0, 24))
        ctx.hidden = privacy.hidden_user_ids(owners)
    return ctx


def _fixed_taken(place, ctx: _Day) -> bool:
    """A fixed place counts as taken by its owner unless the owner is absent."""
    return bool(place.fixed_owner_id) and place.fixed_owner_id not in ctx.absent


# Place status -------------------------------------------------------------


def _status_from(place, at: datetime, ctx: _Day, *, viewer, anonymous: bool,
                 ignore_fixed: bool = False) -> dict:
    """Pure: the status of ``place`` at ``at`` (a time on ``ctx.day``)."""
    result = {"state": "closed", "until": None, "next": None, "holder": None}
    hour = timezone.localtime(at, hours.TZ).hour
    rows = ctx.rows.get(place.pk, [])
    upcoming = next((r for r in rows if r.period.lower > at), None)
    if upcoming is not None:
        result["next"] = {"start": _iso(upcoming.period.lower), "end": _iso(upcoming.period.upper)}
    open_hours = ctx.open_hours
    if (
        not place.is_bookable or open_hours is None
        or not open_hours[0] <= hour < open_hours[1] or hour in ctx.closed
    ):
        return result
    # End of the open stretch containing ``hour``.
    stretch_end = hour + 1
    while stretch_end < open_hours[1] and stretch_end not in ctx.closed:
        stretch_end += 1
    current = next((r for r in rows if r.period.lower <= at < r.period.upper), None)
    if current is not None:
        result.update(state=_reservation_state(current), until=_iso(current.period.upper))
        if not anonymous:
            result["holder"] = privacy.holder_label(current, viewer=viewer)
        return result
    if not ignore_fixed and _fixed_taken(place, ctx):
        result.update(state="booked", until=_iso(hours.local_dt(ctx.day, stretch_end)))
        if not anonymous:
            result["holder"] = privacy.fixed_owner_label(
                place, viewer=viewer, hidden_ids=ctx.hidden
            )
        return result
    until = hours.local_dt(ctx.day, stretch_end)
    if upcoming is not None and upcoming.period.lower < until:
        until = upcoming.period.lower
    result.update(state="free", until=_iso(until))
    return result


def place_status(place, *, at: datetime, anonymous: bool) -> dict:
    """``{"state", "until", "next": {"start", "end"} | None, "holder"}`` of a
    place at ``at``. ``holder`` is public (hidden desk holders never) and
    always ``None`` when ``anonymous`` (lending-style resources)."""
    if place.pool_id is None:
        # Unassigned: no business hours, never bookable.
        return {"state": "closed", "until": None, "next": None, "holder": None}
    ctx = _load_day(place.pool, timezone.localtime(at, hours.TZ).date(), [place])
    return _status_from(place, at, ctx, viewer=None, anonymous=anonymous)


# Department overview ------------------------------------------------------


def department_day(pool, day: date, *, viewer, now=None) -> dict:
    """Floors with plan and per-hour place states, plus the meeting room
    timelines of ``day``. ``now`` (default: the current time) adds each
    place's current status when ``day`` is today."""
    now = now or timezone.now()
    is_today = timezone.localtime(now, hours.TZ).date() == day
    places = list(_active_places(pool))
    ctx = _load_day(pool, day, places)
    grid = list(range(*ctx.open_hours)) if ctx.open_hours else []
    by_place = ctx.rows
    viewer_pk = getattr(viewer, "pk", None)

    def place_hours(place):
        rows = by_place.get(place.pk, [])
        fixed_taken = bool(grid) and _fixed_taken(place, ctx)
        fixed_label = (
            privacy.fixed_owner_label(place, viewer=viewer, hidden_ids=ctx.hidden)
            if fixed_taken else None
        )
        out = []
        for hour in grid:
            slot = hours.local_range(day, hour, hour + 1)
            entry = {"hour": hour, "state": "free", "reservation_id": None, "holder": None,
                     "mine": False}
            if hour in ctx.closed:
                entry["state"] = "closed"
            else:
                res = next(
                    (r for r in rows if r.period.lower < slot.upper and slot.lower < r.period.upper),
                    None,
                )
                if res is not None:
                    entry.update(
                        state=_reservation_state(res), reservation_id=res.pk,
                        holder=privacy.holder_label(res, viewer=viewer),
                        mine=res.holder_id is not None and res.holder_id == viewer_pk,
                    )
                elif fixed_taken:
                    entry.update(state="booked", holder=fixed_label,
                                 mine=place.fixed_owner_id == viewer_pk)
            out.append(entry)
        return out

    floors = []
    floor_index = {}
    # Floors are shared: only the rooms holding this department's places.
    room_ids = {p.room_id for p in places}
    for floor in pool_floors(pool).select_related("building").prefetch_related("rooms"):
        data = {
            "id": floor.pk, "name": floor.name, **floor_location(floor),
            "building_address": floor.building.address if floor.building_id else "",
            "plan": floor.plan,
            "scale_px_per_m": floor.scale_px_per_m,
            "rooms": [
                {"id": r.pk, "name": r.name, "kind": r.kind}
                for r in floor.rooms.all() if r.is_active and r.pk in room_ids
            ],
            "places": [],
        }
        floor_index[floor.pk] = data
        floors.append(data)
    meeting_rooms = []
    for place in places:
        floor = floor_index.get(place.room.floor_id)
        if floor is None:
            continue
        floor["places"].append({
            "id": place.pk, "name": place.name, "kind": place.kind, "room_id": place.room_id,
            "capacity": place.capacity, "is_special": place.is_special,
            "plan_symbol": place.plan_symbol, "features": [f.pk for f in place.features.all()],
            "fixed": bool(place.fixed_owner_id),
            # The viewer may book it (hour selection in the overview).
            "bookable": rights.can_book_place(viewer, place),
            "hours": place_hours(place),
            "now": (
                _status_from(place, now, ctx, viewer=viewer, anonymous=False)
                if is_today else None
            ),
        })
        if place.kind == Place.Kind.MEETING_ROOM:
            meeting_rooms.append({
                "id": place.pk, "name": place.name, "room": place.room.name,
                "floor": place.room.floor.name, "floor_id": place.room.floor_id,
                "capacity": place.capacity,
                # The viewer may book it (timeline selection in the overview;
                # the places are active already).
                "bookable": rights.can_book_place(viewer, place),
                "reservations": [
                    {
                        "id": res.pk,
                        "start_hour": hours.local_day_hours(res.period)[1],
                        "end_hour": hours.local_day_hours(res.period)[2],
                        "state": _reservation_state(res),
                        "holder": privacy.holder_label(res, viewer=viewer),
                        "comment": privacy.comment_for(res, viewer=viewer),
                        "mine": res.holder_id is not None and res.holder_id == viewer_pk,
                    }
                    for res in by_place.get(place.pk, [])
                ],
            })
    return {
        "pool": pool.pk,
        "day": day.isoformat(),
        "open_hours": list(ctx.open_hours) if ctx.open_hours else None,
        "closed_hours": sorted(ctx.closed),
        "floors": floors,
        "meeting_rooms": meeting_rooms,
        "last_floor_id": last_floor_id(pool, viewer),
    }


def last_floor_id(pool, viewer) -> int | None:
    """Floor of the viewer's most recently made booking in ``pool`` (still an
    active floor): the overview opens there."""
    if getattr(viewer, "pk", None) is None:
        return None
    return (
        Reservation.objects.filter(
            booked_by=viewer, place__pool=pool, place__room__floor__is_active=True
        )
        .order_by("-created_at", "-pk")
        .values_list("place__room__floor_id", flat=True)
        .first()
    )


# Room popularity ---------------------------------------------------------

POPULARITY_DAYS = 90


def room_popularity(pool, *, now=None) -> list[int]:
    """Active rooms holding active places of ``pool``, most popular first:
    booked hours of the last ``POPULARITY_DAYS`` days per bookable place of
    ``pool``. Only places without a fixed owner count — a fixed desk's figures would reveal its owner's absences
    (same rule as the statistics) — and only the order leaves the API, no
    figures. Rooms without such places come last; ties by name."""
    now = now or timezone.now()
    rooms = list(
        Room.objects.filter(
            Exists(Place.objects.filter(room=OuterRef("pk"), pool=pool, is_active=True)),
            floor__is_active=True, is_active=True,
        ).order_by("name", "pk")
    )
    places = dict(
        Place.objects.filter(
            room__in=rooms, pool=pool, is_active=True, fixed_owner__isnull=True
        ).values_list("pk", "room_id")
    )
    per_room: dict[int, int] = {}
    for room_id in places.values():
        per_room[room_id] = per_room.get(room_id, 0) + 1
    hours_by_room: dict[int, float] = {}
    since = now - timedelta(days=POPULARITY_DAYS)
    for place_id, period in Reservation.objects.filter(
        place_id__in=list(places), period__overlap=DateTimeTZRange(since, now)
    ).exclude(status=Reservation.Status.CANCELLED).values_list("place_id", "period"):
        start, end = max(period.lower, since), min(period.upper, now)
        if end > start:
            room_id = places[place_id]
            hours_by_room[room_id] = hours_by_room.get(room_id, 0) + (end - start).total_seconds() / 3600

    def score(room) -> float:
        count = per_room.get(room.pk, 0)
        return hours_by_room.get(room.pk, 0) / count if count else -1

    return [r.pk for r in sorted(rooms, key=lambda r: -score(r))]


# Free now and neighbours --------------------------------------------------


def free_now(pool, *, viewer, kind=None, features=(), now=None) -> list[dict]:
    """Places ``viewer`` may book that are free for the current hour, with
    ``free_until`` (next reservation, closed hour or business end)."""
    if pool.pk not in rights.member_pool_ids(viewer):
        return []
    now = now or timezone.now()
    local = timezone.localtime(now, hours.TZ)
    day, hour = local.date(), local.hour
    if not hours.FIRST_HOUR <= hour < hours.LAST_HOUR:
        return []
    kinds = [kind] if kind else [Place.Kind.DESK, Place.Kind.MEETING_ROOM]
    places = [
        place
        for k in kinds
        for place in booking.free_places(
            pool, k, day, hour, hour + 1, for_user=viewer, features=features
        )
    ]
    ctx = _load_day(pool, day, places)
    rows = []
    for place in places:
        # ``free_places`` already settled fixed places for the viewer.
        status_ = _status_from(place, now, ctx, viewer=viewer, anonymous=True, ignore_fixed=True)
        if status_["state"] != "free":
            continue
        rows.append({
            "id": place.pk, "name": place.name, "kind": place.kind,
            "capacity": place.capacity, "room": place.room.name,
            "floor": place.room.floor.name, "building": place.room.floor.building_code,
            "floor_id": place.room.floor_id,
            "features": [f.pk for f in place.features.all()],
            "free_until": status_["until"],
        })
    return rows


def room_neighbours_bulk(reservations, *, viewer) -> dict[int, list[str | None]]:
    """Per reservation id: the other people booked in the same room during
    it, names (sorted) then ``None`` per hidden person; one query per chunk
    of rows. Desks only: meeting-room reservations map to ``[]``."""
    desks = [r for r in reservations if r.place.kind == Place.Kind.DESK]
    result = {r.pk: [] for r in reservations}
    if not desks:
        return result
    # One query per chunk of rows: an OR of (room, overlapping period) per row,
    # so far-apart bookings don't load the whole span between them.
    by_room: dict[int, dict[int, Reservation]] = {}
    for i in range(0, len(desks), 200):
        cond = Q()
        for r in desks[i : i + 200]:
            cond |= Q(place__room_id=r.place.room_id, period__overlap=r.period)
        for res in Reservation.objects.filter(
            cond, status=Reservation.Status.ACTIVE, holder__isnull=False
        ).select_related("holder", "place"):
            by_room.setdefault(res.place.room_id, {})[res.pk] = res
    for r in desks:
        seen, names, hidden = set(), [], 0
        for res in by_room.get(r.place.room_id, {}).values():
            if (
                res.place_id == r.place_id
                or res.holder_id == r.holder_id
                or res.holder_id in seen
                or not (res.period.lower < r.period.upper and r.period.lower < res.period.upper)
            ):
                continue
            seen.add(res.holder_id)
            label = privacy.holder_label(res, viewer=viewer)
            if label is None:
                hidden += 1
            else:
                names.append(label)
        result[r.pk] = sorted(names, key=str.casefold) + [None] * hidden
    return result
