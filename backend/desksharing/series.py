# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Weekly recurring reservations.

A series books every occurrence up front through ``booking.book`` (so rules,
the exclusion constraint and rights apply to each one). A date that cannot be
booked becomes a ``Conflict`` with alternatives instead of failing the series;
closed days are skipped silently.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from lending.services import add_months

from . import booking, hours, rights
from .booking import BookingError
from .models import Place, Reservation, Series

# A series spans at most three months and is extended by three months; the
# extension opens this many days before its end.
SERIES_MONTHS = 3
EXTEND_WINDOW_DAYS = 28


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


def _today() -> date:
    return timezone.localtime(timezone.now(), hours.TZ).date()


def _manager_check(series: Series, actor) -> None:
    """Holder, booker or an assistant/admin of the place's department."""
    if actor.pk in (series.holder_id, series.booked_by_id):
        return
    if series.place.room.floor.pool_id in rights.assistant_pool_ids(actor):
        return
    raise BookingError("not_allowed", detail="You may not change this series.")


def _book_days(series: Series, start: date, end: date, actor) -> tuple[list, list]:
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
                        comment=series.comment, series=series,
                    )
                )
            except BookingError as exc:
                if exc.code == "closed":
                    pass  # holiday, block or closed weekday: nothing to book
                elif exc.code == "not_allowed":
                    raise
                else:
                    conflicts.append(Conflict(day, exc.alternatives, exc.code))
        day += timedelta(days=1)
    return created, conflicts


def create_series(
    *, actor, holder, place, weekdays, start_hour: int, end_hour: int,
    valid_from: date, valid_until: date, comment: str = "",
) -> SeriesResult:
    weekdays = sorted(set(weekdays))
    if not weekdays or any(not isinstance(d, int) or not 0 <= d <= 6 for d in weekdays):
        raise ValueError("Weekdays must be numbers from 0 (Monday) to 6.")
    if valid_until < valid_from:
        raise ValueError("The series ends before it starts.")
    if valid_until > add_months(valid_from, SERIES_MONTHS):
        raise ValueError("A series spans at most three months.")
    # Fail early (and with the right reason) when the holder may not book this.
    booking._check_rights(actor, holder, [place])
    with transaction.atomic():
        series = Series.objects.create(
            holder=holder, booked_by=actor, place=place, weekdays=weekdays,
            start_hour=start_hour, end_hour=end_hour, valid_from=valid_from,
            valid_until=valid_until, comment=comment,
        )
        created, conflicts = _book_days(series, valid_from, valid_until, actor)
    return SeriesResult(series, created, conflicts)


def extend_series(series: Series, *, actor) -> SeriesResult:
    """Extend by three months; allowed from 28 days before the end on, also
    after it (the new window then starts today)."""
    _manager_check(series, actor)
    today = _today()
    if series.cancelled_at or series.holder_id is None:
        raise BookingError("not_allowed", detail="This series cannot be extended.")
    if today < series.valid_until - timedelta(days=EXTEND_WINDOW_DAYS):
        raise BookingError("not_allowed", detail="The extension is not open yet.")
    start = max(series.valid_until + timedelta(days=1), today)
    end = add_months(start, SERIES_MONTHS)
    with transaction.atomic():
        series.valid_until = end
        series.save(update_fields=["valid_until"])
        created, conflicts = _book_days(series, start, end, actor)
    return SeriesResult(series, created, conflicts)


def resolve_conflict(series: Series, day: date, place: Place, *, actor=None) -> Reservation:
    """Book ``place`` instead of the series' place for one conflicting date."""
    actor = actor or series.booked_by or series.holder
    if (
        series.cancelled_at
        or series.holder_id is None
        or not series.valid_from <= day <= series.valid_until
        or day.weekday() not in series.weekdays
    ):
        raise BookingError("not_allowed", detail="This date is not part of the series.")
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


def cancel_occurrence(reservation: Reservation, *, actor, reason: str = "") -> None:
    booking.cancel(reservation, actor=actor, reason=reason)


def move_occurrence(reservation: Reservation, *, actor, to_place: Place) -> Reservation:
    return booking.move(reservation, actor=actor, to_place=to_place)


def delete_series(series: Series, *, actor, reason: str = "") -> int:
    """Cancel the occurrences that have not started yet; past ones stay."""
    _manager_check(series, actor)
    upcoming = list(
        series.reservations.filter(
            status=Reservation.Status.ACTIVE, period__startswith__gt=timezone.now()
        ).select_related("place__room__floor__pool", "holder")
    )
    with transaction.atomic():
        for reservation in upcoming:
            booking.cancel(reservation, actor=actor, reason=reason)
        series.cancelled_at = timezone.now()
        series.save(update_fields=["cancelled_at"])
    return len(upcoming)
