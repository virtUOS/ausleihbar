# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Department overview, "free now", "who sits with me" and the per-place
status (used by displays in spec 3). Every name goes through ``privacy``."""
from datetime import date, datetime

from django.utils import timezone

from . import absences, booking, hours, privacy, rights
from .models import Floor, Place, Reservation

STATES = ("free", "booked", "potentially_free", "checked_in", "closed")


def _active_places(pool):
    return (
        Place.objects.filter(
            room__floor__pool=pool, is_active=True, room__is_active=True,
            room__floor__is_active=True,
        )
        .select_related("room__floor__pool", "fixed_owner")
        .prefetch_related("features")
        .order_by("room__floor__building", "room__floor__position", "room__name", "name", "pk")
    )


def _reservation_state(res) -> str:
    if res.checked_in_at is not None:
        return "checked_in"
    if res.potentially_free_at is not None:
        return "potentially_free"
    return "booked"


def _fixed_taken(place, period) -> bool:
    """A fixed place counts as taken by its owner unless the owner is absent."""
    return bool(place.fixed_owner_id) and not absences.fixed_place_available(place, period)


def _iso(dt):
    """Local (Europe/Berlin) ISO time."""
    return timezone.localtime(dt, hours.TZ).isoformat() if dt else None


# Place status -------------------------------------------------------------


def _status(place, at: datetime, *, viewer, anonymous: bool) -> dict:
    result = {"state": "closed", "until": None, "next": None, "holder": None}
    local = timezone.localtime(at, hours.TZ)
    day, hour = local.date(), local.hour
    day_end = hours.local_dt(day, 24)
    upcoming = (
        Reservation.objects.filter(
            place=place, status=Reservation.Status.ACTIVE,
            period__startswith__gt=at, period__startswith__lt=day_end,
        )
        .order_by("period")
        .first()
    )
    if upcoming is not None:
        result["next"] = {"start": _iso(upcoming.period.lower), "end": _iso(upcoming.period.upper)}
    if not place.is_bookable:
        return result
    open_hours = hours.business_hours(place.pool, day)
    closed = hours.closed_hours(place.pool, day)
    if open_hours is None or not open_hours[0] <= hour < open_hours[1] or hour in closed:
        return result
    # End of the open stretch containing ``hour``.
    stretch_end = hour + 1
    while stretch_end < open_hours[1] and stretch_end not in closed:
        stretch_end += 1
    current = (
        Reservation.objects.filter(
            place=place, status=Reservation.Status.ACTIVE, period__contains=at
        )
        .select_related("holder", "place")
        .first()
    )
    if current is not None:
        result.update(state=_reservation_state(current), until=_iso(current.period.upper))
        if not anonymous:
            result["holder"] = privacy.holder_label(current, viewer=viewer)
        return result
    if _fixed_taken(place, hours.local_range(day, hour, hour + 1)):
        result.update(state="booked", until=_iso(hours.local_dt(day, stretch_end)))
        if not anonymous:
            result["holder"] = privacy.fixed_owner_label(place, viewer=viewer)
        return result
    until = hours.local_dt(day, stretch_end)
    if upcoming is not None and upcoming.period.lower < until:
        until = upcoming.period.lower
    result.update(state="free", until=_iso(until))
    return result


def place_status(place, *, at: datetime, anonymous: bool) -> dict:
    """``{"state", "until", "next": {"start", "end"} | None, "holder"}`` of a
    place at ``at``. ``holder`` is public (hidden desk holders never) and
    always ``None`` when ``anonymous`` (lending-style resources)."""
    return _status(place, at, viewer=None, anonymous=anonymous)


# Department overview ------------------------------------------------------


def department_day(pool, day: date, *, viewer, now=None) -> dict:
    """Floors with plan and per-hour place states, plus the meeting room
    timelines of ``day``. ``now`` (default: the current time) adds each
    place's current status when ``day`` is today."""
    now = now or timezone.now()
    is_today = timezone.localtime(now, hours.TZ).date() == day
    open_hours = hours.business_hours(pool, day)
    closed = hours.closed_hours(pool, day) if open_hours else set()
    grid = list(range(open_hours[0], open_hours[1])) if open_hours else []
    places = list(_active_places(pool))
    day_range = hours.local_range(day, 0, 24)
    reservations = list(
        Reservation.objects.filter(
            place__in=places, status=Reservation.Status.ACTIVE, period__overlap=day_range
        )
        .select_related("holder", "place__room__floor")
        .order_by("period", "pk")
    )
    by_place: dict[int, list[Reservation]] = {}
    for res in reservations:
        by_place.setdefault(res.place_id, []).append(res)
    viewer_pk = getattr(viewer, "pk", None)

    def place_hours(place):
        rows = by_place.get(place.pk, [])
        fixed_taken = bool(grid) and _fixed_taken(place, hours.local_range(day, grid[0], grid[-1] + 1))
        fixed_label = privacy.fixed_owner_label(place, viewer=viewer) if fixed_taken else None
        out = []
        for hour in grid:
            slot = hours.local_range(day, hour, hour + 1)
            entry = {"hour": hour, "state": "free", "reservation_id": None, "holder": None,
                     "mine": False}
            if hour in closed:
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
    for floor in Floor.objects.filter(pool=pool, is_active=True).prefetch_related("rooms"):
        data = {
            "id": floor.pk, "name": floor.name, "building": floor.building, "plan": floor.plan,
            "rooms": [
                {"id": r.pk, "name": r.name, "kind": r.kind} for r in floor.rooms.all() if r.is_active
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
            "hours": place_hours(place),
            "now": _status(place, now, viewer=viewer, anonymous=False) if is_today else None,
        })
        if place.kind == Place.Kind.MEETING_ROOM:
            meeting_rooms.append({
                "id": place.pk, "name": place.name, "room": place.room.name,
                "floor": place.room.floor.name, "capacity": place.capacity,
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
        "open_hours": list(open_hours) if open_hours else None,
        "closed_hours": sorted(closed),
        "floors": floors,
        "meeting_rooms": meeting_rooms,
    }


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
    rows = []
    for k in kinds:
        for place in booking.free_places(
            pool, k, day, hour, hour + 1, for_user=viewer, features=features
        ):
            status_ = _status(place, now, viewer=viewer, anonymous=True)
            if status_["state"] != "free":
                continue
            rows.append({
                "id": place.pk, "name": place.name, "kind": place.kind,
                "capacity": place.capacity, "room": place.room.name,
                "floor": place.room.floor.name, "building": place.room.floor.building,
                "features": [f.pk for f in place.features.all()],
                "free_until": status_["until"],
            })
    return rows


def room_neighbours(reservation, *, viewer) -> list[str | None]:
    """The other people booked in the same room during the reservation:
    names (sorted), then ``None`` per hidden person."""
    others = (
        Reservation.objects.filter(
            place__room_id=reservation.place.room_id,
            status=Reservation.Status.ACTIVE,
            period__overlap=reservation.period,
            holder__isnull=False,
        )
        .exclude(place_id=reservation.place_id)
        .exclude(holder_id=reservation.holder_id)
        .select_related("holder", "place")
    )
    seen, names, hidden = set(), [], 0
    for res in others:
        if res.holder_id in seen:
            continue
        seen.add(res.holder_id)
        label = privacy.holder_label(res, viewer=viewer)
        if label is None:
            hidden += 1
        else:
            names.append(label)
    return sorted(names, key=str.casefold) + [None] * hidden
