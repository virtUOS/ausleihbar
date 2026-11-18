# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""The desksharing booking engine.

Reservations are whole local hours of one day inside the department's
business hours. Several places booked in one action share a ``group`` and
are created all or nothing. Overlaps are refused by the database exclusion
constraint; a friendly pre-check reports them with alternatives first.
"""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone
from psycopg import errors as pg_errors

from lending.services import add_months

from . import absences, cycles, hours, notify, privacy, rights
from .models import DeskSettings, Place, ReleaseRequest, Reservation, Series

CODES = (
    "not_allowed", "outside_hours", "closed", "horizon", "taken",
    "advance_days", "advance_places", "series_window",
)
EXCLUSION_CONSTRAINT = "desk_no_overlapping_active_reservations"
# Upper bound for a multi-day range when the pool sets no booking horizon.
MAX_RANGE_DAYS = 366


class BookingError(Exception):
    """A refused booking. ``code`` is one of ``CODES`` (or
    ``"reason_required"`` for an admin cancel without a reason)."""

    def __init__(
        self, code: str, alternatives: list[Place] | None = None, detail: str = "",
        extra: dict | None = None,
    ):
        super().__init__(detail or code)
        self.code = code
        self.extra = extra or {}
        self.alternatives = alternatives or []
        self.detail = detail or code


def _is_fixed_for_others(place, holder, period) -> bool:
    return bool(
        place.fixed_owner_id
        and place.fixed_owner_id != getattr(holder, "pk", None)
        and not absences.fixed_place_available(place, period)
    )


def _taken_place_ids(place_ids, period, exclude_pk=None) -> set[int]:
    qs = Reservation.objects.filter(
        place_id__in=place_ids,
        status=Reservation.Status.ACTIVE,
        period__overlap=period,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return set(qs.values_list("place_id", flat=True))


def _check_hours(pool, day: date, start_hour: int, end_hour: int) -> None:
    """Grid, business hours and blocks of one day."""
    if not (
        hours.FIRST_HOUR <= start_hour < end_hour <= hours.LAST_HOUR
    ):
        raise BookingError("outside_hours", detail="Hours must lie within 06-20.")
    open_hours = hours.business_hours(pool, day)
    if open_hours is None:
        raise BookingError("closed", detail="The department is closed that day.")
    if start_hour < open_hours[0] or end_hour > open_hours[1]:
        raise BookingError("outside_hours", detail="Outside the business hours.")
    if hours.closed_hours(pool, day) & set(range(start_hour, end_hour)):
        raise BookingError("closed", detail="These hours are closed.")


def _check_horizon(
    pool, day: date, start_hour: int, end_hour: int, *, check_past: bool = True
) -> None:
    now = timezone.now()
    local_now = timezone.localtime(now, hours.TZ)
    if check_past:
        # Today the current hour may still be booked, earlier ones not.
        if day < local_now.date() or (day == local_now.date() and start_hour < local_now.hour):
            raise BookingError("horizon", detail="This time has passed.")
        if hours.local_dt(day, end_hour) <= now:
            raise BookingError("horizon", detail="This time has passed.")
    months = pool.max_booking_months or 0
    if months and day > add_months(local_now.date(), months):
        raise BookingError("horizon", detail="Too far ahead.")


def _check_same_kind(places) -> None:
    if len({p.kind for p in places}) > 1:
        raise BookingError(
            "not_allowed", detail="Desks and meeting rooms cannot be booked together."
        )


def _check_rights(actor, holder, places) -> None:
    for place in places:
        if not place.is_bookable or not rights.can_book_place(holder, place):
            raise BookingError("not_allowed", detail="This place cannot be booked.")
        if actor.pk != holder.pk and place.pool.pk not in rights.assistant_pool_ids(actor):
            raise BookingError("not_allowed", detail="You may not book for others here.")


def _alternatives(places, day, start_hour, end_hour, holder) -> list[Place]:
    first = places[0]
    requested = {p.pk for p in places}
    return [
        p
        for p in free_places(
            first.pool, first.kind, day, start_hour, end_hour, for_user=holder
        )
        if p.pk not in requested
    ]


def _validate_day(actor, holder, places, day, start_hour, end_hour) -> None:
    """Everything except overlaps with other reservations."""
    _check_rights(actor, holder, places)
    for pool in {p.pool.pk: p.pool for p in places}.values():
        _check_hours(pool, day, start_hour, end_hour)
        _check_horizon(pool, day, start_hour, end_hour)
    period = hours.local_range(day, start_hour, end_hour)
    if any(_is_fixed_for_others(p, holder, period) for p in places):
        raise BookingError(
            "taken",
            _alternatives(places, day, start_hour, end_hour, holder),
            detail="This place is assigned to someone else.",
        )
    if _taken_place_ids([p.pk for p in places], period):
        raise BookingError(
            "taken",
            _alternatives(places, day, start_hour, end_hour, holder),
            detail="A place is already booked at this time.",
        )


def _is_conflict(exc) -> bool:
    """Our exclusion violation, or a deadlock between two conflicting inserts.
    Any other database error is a bug and propagates."""
    cause = exc.__cause__
    if isinstance(exc, IntegrityError):
        return (
            isinstance(cause, pg_errors.ExclusionViolation)
            and getattr(cause.diag, "constraint_name", None) == EXCLUSION_CONSTRAINT
        )
    return isinstance(cause, pg_errors.DeadlockDetected)


def _lock_places(place_ids) -> None:
    """Row locks on the places, always in pk order, so that concurrent
    bookings of the same place queue up instead of deadlocking."""
    list(
        Place.objects.select_for_update()
        .filter(pk__in=place_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _lock_holder(holder) -> None:
    """Row lock on the holder, so that concurrent bookings of one person
    cannot both pass the advance-quota check. ``no_key``: reservation inserts
    take FOR KEY SHARE on the referenced user rows, which a plain FOR UPDATE
    would conflict with (deadlocks); FOR NO KEY UPDATE still serializes
    bookings of the same holder."""
    list(
        get_user_model().objects.select_for_update(no_key=True).filter(pk=holder.pk).values_list("pk", flat=True)
    )


def _entries(places, slots) -> list[tuple]:
    """``(day, start, end, place)`` for every slot and place (places by pk)."""
    ordered = sorted(places, key=lambda p: p.pk)
    return [(day, start, end, place) for day, start, end in slots for place in ordered]


def _create(
    actor, holder, entries, comment, series, notify_holder=True, warnings=None,
    extra_slots=(), after_check=None,
) -> list[Reservation]:
    """Create one reservation per entry ``(day, start, end, place)``, all or
    nothing, sharing one group; the exclusion constraint is the final word
    on overlaps. ``extra_slots`` (``(day, place)``, e.g. requested slots) are
    only counted by the limit check; ``after_check`` runs under the same
    locks once the limits passed."""
    group = uuid.uuid4()
    hides = privacy.hides_name(holder)
    rows = []
    places = list({
        p.pk: p for p in [e[3] for e in entries] + [place for _, place in extra_slots]
    }.values())
    try:
        with transaction.atomic():
            _lock_holder(holder)
            _lock_places([p.pk for p in places])
            limit_warnings = cycles.check_limits(
                actor=actor, holder=holder, places=places,
                slots=[(day, place.pk) for day, _, _, place in entries]
                + [(day, place.pk) for day, place in extra_slots],
            )
            if after_check is not None:
                after_check()
            if warnings is not None:
                warnings.extend(limit_warnings)
            for day, start_hour, end_hour, place in entries:
                rows.append(
                    Reservation.objects.create(
                        place=place,
                        holder=holder,
                        booked_by=actor,
                        group=group,
                        period=hours.local_range(day, start_hour, end_hour),
                        comment=comment,
                        series=series,
                        holder_hidden=hides and place.kind == Place.Kind.DESK,
                    )
                )
    except (IntegrityError, OperationalError) as exc:
        if not _is_conflict(exc):
            raise
        if not entries:  # only requests: a deadlock while locking blockers
            raise BookingError("taken", detail="A place was booked at the same time.") from None
        day, start_hour, end_hour, _ = entries[0]
        raise BookingError(
            "taken",
            _alternatives(places, day, start_hour, end_hour, holder),
            detail="A place was booked at the same time.",
        ) from None
    if notify_holder and rows and actor.pk != holder.pk:
        notify.notify(holder, notify.BOOKED_FOR_YOU, {"reservations": rows})
    return rows


def book(
    *, actor, holder, places: list[Place], day: date, start_hour: int, end_hour: int,
    comment: str = "", series=None, notify_holder: bool = True,
    warnings: list[str] | None = None,
) -> list[Reservation]:
    """Book ``places`` for ``holder`` on one day; one shared group.
    ``notify_holder=False``: the caller sends one mail for several bookings."""
    places = list(dict.fromkeys(places))
    if not places:
        raise BookingError("not_allowed", detail="No place given.")
    _check_same_kind(places)
    _validate_day(actor, holder, places, day, start_hour, end_hour)
    return _create(
        actor, holder, _entries(places, [(day, start_hour, end_hour)]), comment, series,
        notify_holder, warnings,
    )


def book_range(
    *, actor, holder, places: list[Place], day: date, last_day: date,
    start_hour: int, end_hour: int, comment: str = "", series=None,
    warnings: list[str] | None = None,
) -> list[Reservation]:
    """Multi-day meeting room booking: one reservation per place and open day
    in ``day..last_day``, the hours clamped to that day's business hours.
    Closed days (weekday without hours, a block within the hours) are skipped."""
    places = list(dict.fromkeys(places))
    if not places or last_day < day:
        raise BookingError("not_allowed", detail="No place or an empty range.")
    _check_same_kind(places)
    if last_day > day and any(p.kind != Place.Kind.MEETING_ROOM for p in places):
        raise BookingError("not_allowed", detail="Only meeting rooms span several days.")
    if not (hours.FIRST_HOUR <= start_hour < end_hour <= hours.LAST_HOUR):
        raise BookingError("outside_hours", detail="Hours must lie within 06-20.")
    # Cheap checks first, so a huge range never reaches the per-day loop.
    _check_rights(actor, holder, places)
    pools = {p.pool.pk: p.pool for p in places}.values()
    if (last_day - day).days >= MAX_RANGE_DAYS:
        raise BookingError("horizon", detail="This range is too long.")
    for pool in pools:
        _check_horizon(pool, last_day, start_hour, end_hour)
    slots = []
    current = day
    while current <= last_day:
        start, end = start_hour, end_hour
        is_open = True
        for pool in pools:
            open_hours = hours.business_hours(pool, current)
            if open_hours is None:
                is_open = False
                break
            start, end = max(start, open_hours[0]), min(end, open_hours[1])
            if start >= end or hours.closed_hours(pool, current) & set(range(start, end)):
                is_open = False
                break
        if is_open:
            slots.append((current, start, end))
        current += timedelta(days=1)
    if not slots:
        raise BookingError("closed", detail="No open day in this range.")
    for slot_day, start, end in slots:
        _validate_day(actor, holder, places, slot_day, start, end)
    return _create(
        actor, holder, _entries(places, slots), comment, series, warnings=warnings
    )


@dataclass
class Slot:
    """One (day, place) of a multi-day booking; ``blocker`` is the one
    reservation in the way (requestable), ``None`` when the slot is free."""

    day: date
    place: Place
    blocker: Reservation | None = None


def _overlaps_by_place(place_ids, periods, related: bool = True) -> dict[int, list[Reservation]]:
    """Active reservations on ``place_ids`` overlapping any of ``periods``,
    with chunked OR queries."""
    found: dict[int, dict[int, Reservation]] = {}
    for i in range(0, len(periods), 200):
        cond = Q()
        for period in periods[i : i + 200]:
            cond |= Q(period__overlap=period)
        rows = Reservation.objects.filter(
            cond, place_id__in=place_ids, status=Reservation.Status.ACTIVE
        )
        if related:
            rows = rows.select_related("holder")
        for res in rows:
            found.setdefault(res.place_id, {})[res.pk] = res
    return {pid: list(d.values()) for pid, d in found.items()}


def classify_slots(
    holder, places, days, start_hour: int, end_hour: int, *, overlaps=None, is_fixed=None,
    own_distinct: bool = True,
):
    """Per (day, place) without raising: ``(day, place, state, hits)`` with
    ``state`` "free", "taken" (exactly one other reservation overlaps, so it
    can be requested) or "unavailable" (fixed for others, several overlaps or
    an own one). ``overlaps`` (place id -> reservations) and ``is_fixed``
    (``place, holder, period`` -> bool) may be supplied by callers that
    already hold them for a long span. ``own_distinct=False`` counts the
    holder's own reservations like anybody else's (somebody else looking:
    it would tell where an opted-out person sits)."""
    is_fixed = is_fixed or _is_fixed_for_others
    periods = {day: hours.local_range(day, start_hour, end_hour) for day in days}
    if overlaps is None:
        overlaps = _overlaps_by_place([p.pk for p in places], list(periods.values()))
    rows = []
    for day in days:
        period = periods[day]
        for place in sorted(places, key=lambda p: p.pk):
            hits = [
                r for r in overlaps.get(place.pk, [])
                if r.period.lower < period.upper and period.lower < r.period.upper
            ]
            if is_fixed(place, holder, period) or len(hits) > 1 or (
                own_distinct and any(r.holder_id == holder.pk for r in hits)
            ):
                rows.append((day, place, "unavailable", hits))
            elif hits:
                rows.append((day, place, "taken", hits))
            else:
                rows.append((day, place, "free", hits))
    return rows


def plan_days(
    *, actor, holder, places: list[Place], days: list[date], start_hour: int, end_hour: int
) -> tuple[list[Slot], list[Slot]]:
    """Split ``days`` x ``places`` into (free, requestable) slots. Raises for
    the first closed / outside-hours / too-far day and when any slot is fixed
    for someone else, overlaps the holder's own reservation or more than one
    reservation (those can never be requested)."""
    places = list(dict.fromkeys(places))
    days = sorted(set(days))
    if not places or not days:
        raise BookingError("not_allowed", detail="No place or day given.")
    _check_same_kind(places)
    _check_rights(actor, holder, places)
    pools = list({p.pool.pk: p.pool for p in places}.values())
    for day in days:
        for pool in pools:
            try:
                _check_hours(pool, day, start_hour, end_hour)
                _check_horizon(pool, day, start_hour, end_hour)
            except BookingError as exc:
                exc.extra = {**exc.extra, "day": day.isoformat()}
                raise
    free, requestable, unavailable = [], [], []
    for day, place, state, hits in classify_slots(
        holder, places, days, start_hour, end_hour, own_distinct=actor.pk == holder.pk,
    ):
        if state == "unavailable":
            unavailable.append({"day": day.isoformat(), "place_id": place.pk})
        elif state == "taken":
            requestable.append(Slot(day, place, hits[0]))
        else:
            free.append(Slot(day, place))
    if unavailable:
        raise BookingError(
            "taken", detail="Some dates cannot be requested.",
            extra={"unavailable": unavailable},
        )
    return free, requestable


def book_days(
    *, actor, holder, places: list[Place], days: list[date], start_hour: int,
    end_hour: int, comment: str = "", on_taken: str = "fail", show_name: bool = False,
    warnings: list[str] | None = None,
) -> tuple[list[Reservation], list[ReleaseRequest]]:
    """Book every free (day, place) in one group; all or nothing. Slots taken
    by someone else refuse the whole call (``on_taken="fail"``) or, with
    ``"request"``, are asked of their holders (``requests.create_batch``) in
    the same transaction. The booking limits cover free and requested slots."""
    from . import requests as requests_svc

    free, requestable = plan_days(
        actor=actor, holder=holder, places=places, days=days,
        start_hour=start_hour, end_hour=end_hour,
    )
    if requestable and on_taken != "request":
        raise BookingError(
            "taken", detail="Some dates are already booked.",
            extra={"taken": [
                {"day": s.day.isoformat(), "place_id": s.place.pk} for s in requestable
            ]},
        )
    entries = [(s.day, start_hour, end_hour, s.place) for s in free]
    created: list[ReleaseRequest] = []

    def request_taken():
        if requestable:
            created.extend(requests_svc.create_batch(
                requester=holder, slots=requestable, start_hour=start_hour,
                end_hour=end_hour, show_name=show_name, batch=uuid.uuid4(), actor=actor,
            ))

    with transaction.atomic():
        rows = _create(
            actor, holder, entries, comment, None, notify_holder=False, warnings=warnings,
            extra_slots=[(s.day, s.place) for s in requestable], after_check=request_taken,
        )
    if rows and actor.pk != holder.pk:
        notify.notify(holder, notify.BOOKED_FOR_YOU, {"reservations": rows})
    return rows, created


def manager_role(actor, *, holder_id, booked_by_id, pool_id) -> str | None:
    """Who ``actor`` is for a reservation or series: ``"holder"``,
    ``"booker"`` (booked it for the holder and still has assistant rights in
    the department), ``"admin"`` (department admin) or ``None``."""
    if actor.pk == holder_id:
        return "holder"
    if actor.pk == booked_by_id and pool_id in rights.assistant_pool_ids(actor):
        return "booker"
    if pool_id in rights.admin_pool_ids(actor):
        return "admin"
    return None


def _role(reservation, actor) -> str | None:
    return manager_role(
        actor,
        holder_id=reservation.holder_id,
        booked_by_id=reservation.booked_by_id,
        pool_id=reservation.place.room.floor.pool_id,
    )


def _check_changeable(reservation, actor) -> str:
    role = _role(reservation, actor)
    if role is None:
        raise BookingError("not_allowed", detail="You may not change this reservation.")
    if reservation.status != Reservation.Status.ACTIVE or reservation.period.upper <= timezone.now():
        raise BookingError("not_allowed", detail="This reservation is over.")
    return role


def cancel(reservation, *, actor, reason: str = "", notify_holder: bool = True) -> None:
    """Cancel by the holder, the booker or a department admin. An admin
    acting on someone else's reservation needs a reason; whenever the actor
    is not the holder, the holder is told."""
    role = _check_changeable(reservation, actor)
    reason = (reason or "").strip()
    if role == "admin" and not reason:
        raise BookingError("reason_required", detail="Please give a reason.")
    now = timezone.now()
    reservation.release_reason = (
        Reservation.ReleaseReason.ADMIN if role == "admin" else Reservation.ReleaseReason.HOLDER
    )
    if reservation.period.lower <= now:
        # Already started: hand back only the remaining hours (from the
        # current full hour) so the used hours stay in the statistics.
        reservation.status = Reservation.Status.RELEASED
        reservation.released_at = timezone.localtime(now, hours.TZ).replace(
            minute=0, second=0, microsecond=0
        )
    else:
        reservation.status = Reservation.Status.CANCELLED
        reservation.released_at = now
    reservation.save(update_fields=["status", "released_at", "release_reason"])
    if notify_holder and role != "holder" and reservation.holder_id:
        notify.notify(
            reservation.holder,
            notify.ADMIN_CHANGED,
            {"reservation": reservation, "action": "cancel", "reason": reason},
        )


def move(reservation, *, actor, to_place) -> Reservation:
    """Move to another place for the same hours (id, group, check-in kept)."""
    role = _check_changeable(reservation, actor)
    if to_place.pk == reservation.place_id:
        return reservation
    holder = reservation.holder
    if to_place.kind != reservation.place.kind:
        raise BookingError(
            "not_allowed", detail="A reservation can only move to a place of the same kind."
        )
    # The holder must be allowed to book the target, whoever moves it.
    if not to_place.is_bookable or holder is None or not rights.can_book_place(holder, to_place):
        raise BookingError("not_allowed", detail="This place cannot be booked.")
    target_pool = to_place.room.floor.pool_id
    if role == "admin" and target_pool not in rights.admin_pool_ids(actor):
        raise BookingError("not_allowed", detail="You do not administer that department.")
    if role == "booker" and target_pool not in rights.assistant_pool_ids(actor):
        raise BookingError("not_allowed", detail="You may not book for others here.")
    day, start_hour, end_hour = hours.local_day_hours(reservation.period)
    _check_hours(to_place.pool, day, start_hour, end_hour)
    # An in-progress reservation may still be moved; the booking horizon applies.
    _check_horizon(
        to_place.pool, day, start_hour, end_hour,
        check_past=reservation.period.lower > timezone.now(),
    )
    period = reservation.period
    if _is_fixed_for_others(to_place, holder, period) or _taken_place_ids(
        [to_place.pk], period, exclude_pk=reservation.pk
    ):
        raise BookingError(
            "taken",
            move_targets(reservation, actor=actor),
            detail="This place is already booked at this time.",
        )
    # Same kind only, so the opt-out snapshot (desks) stays valid.
    old_place, old_owner_use = reservation.place, reservation.owner_use
    try:
        with transaction.atomic():
            _lock_places([to_place.pk])
            reservation.place = to_place
            reservation.owner_use = to_place.fixed_owner_id == holder.pk
            reservation.save(update_fields=["place", "owner_use"])
    except (IntegrityError, OperationalError) as exc:
        reservation.place = old_place
        reservation.owner_use = old_owner_use
        if not _is_conflict(exc):
            raise
        raise BookingError("taken", detail="This place was booked at the same time.") from None
    if role != "holder" and reservation.holder_id:
        notify.notify(
            reservation.holder,
            notify.ADMIN_CHANGED,
            {"reservation": reservation, "action": "move", "from_place": old_place},
        )
    return reservation


def move_targets(reservation, *, actor) -> list[Place]:
    """Free places of the same kind and department for the reservation's
    hours that its holder may book, without its current place. A hidden
    holder's own fixed place is left out unless the holder asks: it would
    tell others who the hidden person is (#208)."""
    holder = reservation.holder
    if holder is None:
        return []
    place = reservation.place
    day, start_hour, end_hour = hours.local_day_hours(reservation.period)
    hide_own = privacy.is_hidden(reservation) and actor.pk != holder.pk
    return [
        p
        for p in free_places(
            place.room.floor.pool, place.kind, day, start_hour, end_hour, for_user=holder
        )
        if p.pk != place.pk and not (hide_own and p.fixed_owner_id == holder.pk)
    ]


def _pool_places(pool, kind, features=()) -> list[Place]:
    """Active places of ``pool`` and ``kind`` (with all their equipment
    features) in display order, prepared for ``rights.can_book_place``."""
    qs = (
        Place.objects.filter(
            room__floor__pool=pool, kind=kind, is_active=True,
            room__is_active=True, room__floor__is_active=True,
        )
        .select_related("room__floor__pool", "room__floor__building")
        .order_by("room__floor__building__code", "room__floor__position", "room__name", "name", "pk")
    )
    for feature_id in set(features or ()):
        qs = qs.filter(features__id=feature_id)
    return list(qs.distinct().prefetch_related("features", "access_groups"))


def free_places(
    pool, kind, day: date, start_hour: int, end_hour: int, *, for_user, features=()
) -> list[Place]:
    """Active places of ``pool`` and ``kind`` that ``for_user`` may book and
    that are free for the whole time (fixed places only for their owner,
    or while the owner is absent)."""
    try:
        _check_hours(pool, day, start_hour, end_hour)
    except BookingError:
        return []
    period = hours.local_range(day, start_hour, end_hour)
    places = _pool_places(pool, kind, features)
    taken = _taken_place_ids([p.pk for p in places], period)
    # One absence query for all fixed places (owners absent the whole time).
    absent = absences.fully_absent_user_ids({p.fixed_owner_id for p in places}, period)
    user_pk = getattr(for_user, "pk", None)
    return [
        p
        for p in places
        if p.pk not in taken
        and not (p.fixed_owner_id and p.fixed_owner_id != user_pk and p.fixed_owner_id not in absent)
        and rights.can_book_place(for_user, p)
    ]


def availability(
    pool, kind, days: list[date], start_hour: int, end_hour: int, *, holder, features=(),
    viewer=None,
) -> list[dict]:
    """Multi-day availability of the places ``holder`` may book: per place
    the days that are ``taken`` (one other reservation — can be requested) or
    ``unavailable`` (fixed for others, several or an own overlap; also every
    day the department is closed for those hours). For a ``viewer`` other
    than the holder (an assistant) the holder's own reservations count like
    anybody else's. A constant number of queries; no holders or reservation
    ids leave this function."""
    own_distinct = viewer is None or viewer.pk == holder.pk
    days = sorted(set(days))
    places = [p for p in _pool_places(pool, kind, features) if p.is_bookable and rights.can_book_place(holder, p)]
    if not places or not days:
        return []
    cfg = DeskSettings.for_pool(pool)
    closed = hours.closed_hours_by_day(pool, days[0], days[-1])
    wanted = set(range(start_hour, end_hour))
    open_days = []
    for day in days:
        span = hours.business_hours(pool, day, cfg)
        if span and span[0] <= start_hour and end_hour <= span[1] and not (closed.get(day, set()) & wanted):
            open_days.append(day)
    closed_days = [d for d in days if d not in open_days]
    first, last = days[0], days[-1]
    overlaps = _overlaps_by_place(
        [p.pk for p in places], [DateTimeTZRange(hours.local_dt(first, 0), hours.local_dt(last, 24))],
        related=False,
    )
    absent = absences.absent_days_by_user({p.fixed_owner_id for p in places}, first, last)

    def is_fixed(place, who, period):
        if not place.fixed_owner_id or place.fixed_owner_id == who.pk:
            return False
        return period.lower.astimezone(hours.TZ).date() not in absent.get(place.fixed_owner_id, set())

    taken: dict[int, list[str]] = {p.pk: [] for p in places}
    unavailable: dict[int, list[str]] = {p.pk: [d.isoformat() for d in closed_days] for p in places}
    for day, place, state, _hits in classify_slots(
        holder, places, open_days, start_hour, end_hour, overlaps=overlaps, is_fixed=is_fixed,
        own_distinct=own_distinct,
    ):
        if state == "taken":
            taken[place.pk].append(day.isoformat())
        elif state == "unavailable":
            unavailable[place.pk].append(day.isoformat())
    return [
        {
            "id": p.pk, "name": p.name, "floor_id": p.room.floor_id, "room": p.room.name,
            "where": ", ".join(x for x in (
                p.room.name, " ".join(y for y in (p.room.floor.building_code, p.room.floor.name) if y)
            ) if x),
            "features": sorted(f.pk for f in p.features.all()),
            "taken_days": taken[p.pk], "unavailable_days": sorted(unavailable[p.pk]),
        }
        for p in places
    ]


def retire_places(places) -> None:
    """Deactivate places, cancelling their reservations that are not over yet
    (holders are told). Past reservations stay for the statistics."""
    now = timezone.now()
    place_ids = [p.pk for p in places]
    pending = Reservation.objects.filter(
        place_id__in=place_ids,
        status=Reservation.Status.ACTIVE,
        period__endswith__gt=now,
    ).select_related("holder", "place__room__floor__building")
    cancelled = []
    for res in pending:
        res.status = Reservation.Status.CANCELLED
        res.released_at = now
        res.release_reason = Reservation.ReleaseReason.ADMIN
        res.save(update_fields=["status", "released_at", "release_reason"])
        cancelled.append(res)
    transaction.on_commit(
        lambda: notify.notify_grouped(
            cancelled, notify.ADMIN_CHANGED, action="cancel", reason="place_removed"
        )
    )
    # A series of a retired place can never be booked again: end it (its
    # occurrences on other places, booked for conflicts, stay).
    Series.objects.filter(place_id__in=place_ids, cancelled_at__isnull=True).update(
        cancelled_at=now
    )
    Place.objects.filter(pk__in=place_ids).update(is_active=False, updated_at=now)
