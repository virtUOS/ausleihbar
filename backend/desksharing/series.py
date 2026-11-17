# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Weekly recurring reservations.

A series books every occurrence up front through ``booking.book`` (so rules,
the exclusion constraint and rights apply to each one). A date that cannot be
booked becomes a ``Conflict`` with alternatives instead of failing the series;
closed days are skipped silently.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from . import booking, cycles, hours, notify
from .booking import BookingError
from .models import Place, ReleaseRequest, Reservation, Series

logger = logging.getLogger(__name__)

@dataclass
class Conflict:
    day: date
    alternatives: list[Place] = field(default_factory=list)
    code: str = "taken"


@dataclass
class SeriesResult:
    series: Series
    created: list[Reservation]
    conflicts: list[Conflict]
    requests: list[ReleaseRequest] = field(default_factory=list)


def _today() -> date:
    return timezone.localtime(timezone.now(), hours.TZ).date()


def _manager_check(series: Series, actor) -> str:
    """Holder, booker (while an assistant of the department) or an admin of
    the place's department; returns the role (see ``booking.manager_role``)."""
    role = booking.manager_role(
        actor,
        holder_id=series.holder_id,
        booked_by_id=series.booked_by_id,
        pool_id=series.place.room.floor.pool_id,
    )
    if role is None:
        raise BookingError("not_allowed", detail="You may not change this series.")
    return role


def _lock(series: Series) -> None:
    """Row-lock the series and reload it (call inside a transaction)."""
    Series.objects.select_for_update().get(pk=series.pk)
    series.refresh_from_db()


def _book_days(
    series: Series, start: date, end: date, actor, warnings: list | None = None
) -> tuple[list, list]:
    created, conflicts = [], []
    today = _today()
    day = max(start, today)
    while day <= end:
        if day.weekday() in series.weekdays:
            try:
                created.extend(
                    booking.book(
                        actor=actor, holder=series.holder, places=[series.place],
                        day=day, start_hour=series.start_hour, end_hour=series.end_hour,
                        comment=series.comment, series=series, notify_holder=False,
                        warnings=warnings,
                    )
                )
            except BookingError as exc:
                if exc.code == "closed":
                    pass  # holiday, block or closed weekday: nothing to book
                elif exc.code in ("not_allowed", "advance_days", "advance_places", "series_window"):
                    raise
                else:
                    conflicts.append(Conflict(day, exc.alternatives, exc.code))
        day += timedelta(days=1)
    return created, conflicts


def _notify_booked(series: Series, created: list, actor) -> None:
    """One "booked for you" mail per series action, not per occurrence."""
    if not created or series.holder_id is None or actor.pk == series.holder_id:
        return
    try:
        notify.notify(
            series.holder, notify.BOOKED_FOR_YOU, {"reservations": created, "series": series}
        )
    except Exception:
        logger.exception("Notification failed for series %s", series.pk)


def _check_business_hours(pool, weekdays, start_hour: int, end_hour: int) -> None:
    """Refuse a series whose hours fit on none of the open selected weekdays
    (it could only ever produce conflicts)."""
    monday = date(2024, 1, 1)  # any Monday: only the weekday matters
    spans = [
        hours.business_hours(pool, monday + timedelta(days=d)) for d in weekdays
    ]
    spans = [sp for sp in spans if sp]
    if spans and not any(sp[0] <= start_hour and end_hour <= sp[1] for sp in spans):
        raise BookingError("outside_hours", detail="Outside the business hours.")


def create_series(
    *, actor, holder, place, weekdays, start_hour: int, end_hour: int,
    valid_from: date, valid_until: date, comment: str = "",
    on_taken: str = "conflict", show_name: bool = False, warnings: list | None = None,
) -> SeriesResult:
    weekdays = sorted(set(weekdays))
    if not weekdays or any(not isinstance(d, int) or not 0 <= d <= 6 for d in weekdays):
        raise ValueError("Weekdays must be numbers from 0 (Monday) to 6.")
    if valid_until < valid_from:
        raise ValueError("The series ends before it starts.")
    if not hours.FIRST_HOUR <= start_hour < end_hour <= hours.LAST_HOUR:
        raise BookingError("outside_hours", detail="Hours must lie within 06-20.")
    # Fail early (and with the right reason) when the holder may not book this.
    booking._check_rights(actor, holder, [place])
    pool = place.room.floor.pool
    _check_business_hours(pool, weekdays, start_hour, end_hour)
    window = cycles.booking_window(pool)
    if valid_until > window.open_until:
        error = BookingError(
            "series_window", detail="A series may not reach beyond the booking window.",
            extra={"open_until": window.open_until.isoformat()},
        )
        if not cycles.is_privileged(actor, holder, pool):
            raise error
        if warnings is not None and error.code not in warnings:
            warnings.append(error.code)
    with transaction.atomic():
        series = Series.objects.create(
            holder=holder, booked_by=actor, place=place, weekdays=weekdays,
            start_hour=start_hour, end_hour=end_hour, valid_from=valid_from,
            valid_until=valid_until, comment=comment,
        )
        created, conflicts = _book_days(series, valid_from, valid_until, actor, warnings)
        requests = []
        if on_taken == "request":
            conflicts, requests = _request_taken(
                series, conflicts, actor=actor, show_name=show_name, warnings=warnings
            )
    _notify_booked(series, created, actor)
    return SeriesResult(series, created, conflicts, requests)


def _request_taken(
    series: Series, conflicts: list[Conflict], *, actor, show_name: bool, warnings: list | None
) -> tuple[list[Conflict], list[ReleaseRequest]]:
    """Turn the conflicts whose date is blocked by exactly one other
    reservation (``booking.plan_days`` rule) into one release-request batch;
    every other conflict stays. Call inside the series transaction."""
    from . import requests as requests_svc

    slots, remaining = [], []
    for conflict in conflicts:
        slot = None
        if conflict.code == "taken":
            try:
                free, requestable = booking.plan_days(
                    actor=actor, holder=series.holder, places=[series.place],
                    days=[conflict.day], start_hour=series.start_hour, end_hour=series.end_hour,
                )
            except BookingError:
                pass
            else:
                if not free and len(requestable) == 1:
                    slot = requestable[0]
        if slot is None:
            remaining.append(conflict)
        else:
            slots.append(slot)
    if not slots:
        return remaining, []
    booking._lock_holder(series.holder)
    booking._lock_places([series.place.pk])
    limit_warnings = cycles.check_limits(
        actor=actor, holder=series.holder, places=[series.place],
        slots=[(s.day, s.place.pk) for s in slots],
    )
    if warnings is not None:
        warnings.extend(w for w in limit_warnings if w not in warnings)
    created = requests_svc.create_batch(
        requester=series.holder, slots=slots, start_hour=series.start_hour,
        end_hour=series.end_hour, show_name=show_name, batch=uuid.uuid4(),
    )
    return remaining, created


def extend_series(series: Series, *, actor, warnings: list | None = None) -> SeriesResult:
    """Extend to the end of the booking window; open while that lies beyond
    the series' end (also after it: the new part then starts today)."""
    _manager_check(series, actor)
    today = _today()
    pool = series.place.room.floor.pool
    with transaction.atomic():
        _lock(series)  # concurrent extends queue up and see the new end
        if series.cancelled_at or series.holder_id is None:
            raise BookingError("not_allowed", detail="This series cannot be extended.")
        end = cycles.booking_window(pool).open_until
        if end <= series.valid_until:
            raise BookingError("not_allowed", detail="The extension is not open yet.")
        start = max(series.valid_until + timedelta(days=1), today)
        series.valid_until = end
        series.reminder_28_sent = series.reminder_7_sent = False
        series.save(update_fields=["valid_until", "reminder_28_sent", "reminder_7_sent"])
        created, conflicts = _book_days(series, start, end, actor, warnings)
    _notify_booked(series, created, actor)
    return SeriesResult(series, created, conflicts)


def resolve_conflict(series: Series, day: date, place: Place, *, actor=None) -> Reservation:
    """Book ``place`` instead of the series' place for one conflicting date."""
    actor = actor or series.booked_by or series.holder
    with transaction.atomic():
        _lock(series)
        return _resolve_locked(series, day, place, actor)


def _resolve_locked(series, day, place, actor) -> Reservation:
    if (
        series.cancelled_at
        or series.holder_id is None
        or not series.valid_from <= day <= series.valid_until
        or day.weekday() not in series.weekdays
    ):
        raise BookingError("not_allowed", detail="This date is not part of the series.")
    if place.kind != series.place.kind:
        raise BookingError(
            "not_allowed", detail="A reservation can only move to a place of the same kind."
        )
    already = Reservation.objects.filter(
        series=series, status=Reservation.Status.ACTIVE,
        period__overlap=hours.local_range(day, series.start_hour, series.end_hour),
    ).exists()
    if already:
        raise BookingError("not_allowed", detail="This date is already booked.")
    [reservation] = booking.book(
        actor=actor, holder=series.holder, places=[place], day=day,
        start_hour=series.start_hour, end_hour=series.end_hour,
        comment=series.comment, series=series,
    )
    return reservation


def open_conflicts(series: Series) -> list[Conflict]:
    """Future dates of the series that have no occurrence yet (never booked
    because the place was taken, never resolved), with the places free then.
    A date the holder cancelled single-handedly has a (cancelled) occurrence
    and is not listed; closed days, past hours and dates beyond the booking
    horizon are not offered."""
    if series.cancelled_at or series.holder_id is None:
        return []
    pool = series.place.room.floor.pool
    present = {
        hours.local_day_hours(period)[0]
        for period in series.reservations.values_list("period", flat=True)
    }
    today = _today()
    now = timezone.now()
    horizon = cycles.booking_window(pool).advance_until
    result: list[Conflict] = []
    day = max(series.valid_from, today)
    while day <= series.valid_until:
        if day.weekday() in series.weekdays and day not in present:
            span = hours.business_hours(pool, day)
            open_ = (
                span is not None
                and span[0] <= series.start_hour
                and series.end_hour <= span[1]
                and not hours.closed_hours(pool, day) & set(range(series.start_hour, series.end_hour))
                and hours.local_dt(day, series.end_hour) > now
                and not (day == today and series.start_hour < timezone.localtime(now, hours.TZ).hour)
                and day <= horizon
            )
            if open_:
                alternatives = booking.free_places(
                    pool, series.place.kind, day, series.start_hour, series.end_hour,
                    for_user=series.holder,
                )
                result.append(Conflict(day, alternatives, "taken"))
        day += timedelta(days=1)
    return result


def cancel_occurrence(reservation: Reservation, *, actor, reason: str = "") -> None:
    booking.cancel(reservation, actor=actor, reason=reason)


def move_occurrence(reservation: Reservation, *, actor, to_place: Place) -> Reservation:
    return booking.move(reservation, actor=actor, to_place=to_place)


def delete_series(series: Series, *, actor, reason: str = "") -> int:
    """End the series: cancel the occurrences that have not started yet and
    that ``actor`` may cancel one by one; past ones stay. Occurrences that
    are no longer the actor's (booked by someone else, e.g. an admin's
    extension, or moved to another department) stay untouched (#209).
    Returns the number cancelled."""
    role = _manager_check(series, actor)
    reason = (reason or "").strip()
    if role == "admin" and not reason:
        raise BookingError("reason_required", detail="Please give a reason.")

    def may_cancel(reservation) -> bool:
        occurrence_role = booking._role(reservation, actor)
        return occurrence_role is not None and (occurrence_role != "admin" or bool(reason))

    upcoming = [
        r
        for r in series.reservations.filter(
            status=Reservation.Status.ACTIVE, period__startswith__gt=timezone.now()
        ).select_related("place__room__floor__pool", "place__room__floor__building", "holder")
        if may_cancel(r)
    ]
    with transaction.atomic():
        for reservation in upcoming:
            booking.cancel(reservation, actor=actor, reason=reason, notify_holder=False)
        series.cancelled_at = timezone.now()
        series.save(update_fields=["cancelled_at"])
        if actor.pk != series.holder_id:
            # One mail for the whole series, once the cancellation is committed.
            transaction.on_commit(
                lambda: notify.notify_grouped(
                    upcoming, notify.ADMIN_CHANGED, action="cancel", reason=reason
                )
            )
    return len(upcoming)
