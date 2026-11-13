# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Absences, fixed places, blocks and lost rights.

Releasing for an absence, block or lost right is not a no-show: the
reservation is ``released`` (``cancelled`` for lost rights), the period stays
unchanged, and the holder is told. A failing notification never aborts the
run.
"""
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import hours, notify, rights
from .models import Absence, Reservation, Series

logger = logging.getLogger(__name__)

MAX_ABSENCE_DAYS = 366  # also in the static message of ``add_absence``
RELEASED_OTHER = "released_other"


def _day_range(start: date, end: date):
    """Local [start 00:00, end+1 00:00) as a datetime range."""
    return hours.local_dt(start, 0), hours.local_dt(end + timedelta(days=1), 0)


def _period_days(period) -> tuple[date, date]:
    first = period.lower.astimezone(hours.TZ).date()
    last = (period.upper - timedelta(microseconds=1)).astimezone(hours.TZ).date()
    return first, last


def fully_absent_user_ids(user_ids, period) -> set[int]:
    """Users (of ``user_ids``) whose absences cover every local day of
    ``period`` — one query for any number of users."""
    user_ids = {u for u in user_ids if u}
    if not user_ids:
        return set()
    first, last = _period_days(period)
    covered: dict[int, set] = {}
    for user_id, start, end in Absence.objects.filter(
        user_id__in=user_ids, start_date__lte=last, end_date__gte=first
    ).values_list("user_id", "start_date", "end_date"):
        days = covered.setdefault(user_id, set())
        day = max(start, first)
        while day <= min(end, last):
            days.add(day)
            day += timedelta(days=1)
    needed = (last - first).days + 1
    return {u for u, days in covered.items() if len(days) == needed}


def fixed_place_available(place, period) -> bool:
    """Whether a fixed place is free for others during ``period``: its owner
    has absences covering every local day of the period."""
    if not place.fixed_owner_id:
        return False
    return place.fixed_owner_id in fully_absent_user_ids([place.fixed_owner_id], period)


def _release(reservations, reason: str) -> list[Reservation]:
    """Release the given active, not yet ended reservations (status
    ``released``; period unchanged, no no-show). Returns the released ones;
    notifying is the caller's business."""
    now = timezone.now()
    released = []
    for res in list(reservations.select_related("holder")):
        updated = Reservation.objects.filter(
            pk=res.pk, status=Reservation.Status.ACTIVE
        ).update(
            status=Reservation.Status.RELEASED,
            released_at=now,
            release_reason=reason,
        )
        if not updated:
            continue
        res.status = Reservation.Status.RELEASED
        res.released_at = now
        res.release_reason = reason
        released.append(res)
    return released


def _notify_all(reservations, reason: str) -> None:
    """One mail per holder, once the surrounding transaction committed."""
    reservations = list(reservations)
    transaction.on_commit(
        lambda: notify.notify_grouped(reservations, RELEASED_OTHER, reason=reason, log=logger)
    )


def _current(qs):
    """Active reservations that have not ended yet."""
    return qs.filter(
        status=Reservation.Status.ACTIVE, period__endswith__gt=timezone.now()
    )


def add_absence(*, actor, user, start_date, end_date, kind) -> Absence:
    """Record an absence and release the user's reservations in it. A person
    records their own; assistants and admins those of members of their
    departments."""
    from .booking import BookingError  # circular: booking imports this module

    if kind not in Absence.Kind.values:
        raise BookingError("invalid_absence", detail="Unknown kind.")
    if end_date < start_date or (end_date - start_date).days + 1 > MAX_ABSENCE_DAYS:
        raise BookingError(
            # Static text (the frontend translates it as a catalog key).
            "invalid_absence", detail="End must not precede start; at most 366 days."
        )
    if actor.pk != user.pk and not (
        rights.assistant_pool_ids(actor) & rights.member_pool_ids(user)
    ):
        raise BookingError("not_allowed", detail="You may not mark this person absent.")
    with transaction.atomic():
        absence = Absence.objects.create(
            user=user, start_date=start_date, end_date=end_date, kind=kind, created_by=actor
        )
        lower, upper = _day_range(start_date, end_date)
        released = _release(
            _current(Reservation.objects.filter(holder=user, period__overlap=(lower, upper))),
            Reservation.ReleaseReason.ABSENCE,
        )
        if actor.pk != user.pk:
            _notify_all(released, Reservation.ReleaseReason.ABSENCE)
    absence.released_count = len(released)
    return absence


def delete_absence(absence) -> int:
    """Delete ``absence`` and return how many of others' bookings on the
    owner's fixed places stay although the owner is now back for them.

    They are kept on purpose (user decision): whoever booked the free fixed
    desk keeps it; the owner is only told, so they can book elsewhere or ask
    for a release."""
    from .models import Place

    with transaction.atomic():
        user_id, start, end = absence.user_id, absence.start_date, absence.end_date
        absence.delete()
        place_ids = list(
            Place.objects.filter(fixed_owner_id=user_id).values_list("pk", flat=True)
        )
        if not place_ids:
            return 0
        lower, upper = _day_range(start, end)
        others = _current(
            Reservation.objects.filter(place_id__in=place_ids, period__overlap=(lower, upper))
            .exclude(holder_id=user_id)
            .select_related("place")
        )
        return sum(1 for r in others if not fixed_place_available(r.place, r.period))


def warnings_for(holder, reservations) -> list[str]:
    """Non-blocking warnings for new reservations of ``holder``: ``"absent"``
    when an absence overlaps any of their days."""
    days = {hours.local_day_hours(r.period)[0] for r in reservations}
    if holder is None or not days:
        return []
    for start, end in Absence.objects.filter(
        user=holder, start_date__lte=max(days), end_date__gte=min(days)
    ).values_list("start_date", "end_date"):
        if any(start <= d <= end for d in days):
            return ["absent"]
    return []


def on_block_saved(block) -> int:
    """Release reservations overlapping a system- or pool-scoped block (the
    same scoping as ``hours.closed_hours``); other scopes do not affect
    desksharing."""
    if block.product_id or block.resource_id or block.period is None:
        return 0
    qs = _current(Reservation.objects.filter(period__overlap=block.period))
    if block.resource_pool_id:
        qs = qs.filter(place__room__floor__pool_id=block.resource_pool_id)
    released = _release(qs, Reservation.ReleaseReason.BLOCK)
    _notify_all(released, Reservation.ReleaseReason.BLOCK)
    return len(released)


def revoke_lost_rights(user=None, place=None) -> int:
    """Cancel future reservations (not yet started) whose holder may no longer
    book the place. Limited to one user and/or place when given. A series
    whose holder may no longer book the series' own place ends as well
    (``cancelled_at``; no more reminders or extensions)."""
    qs = Reservation.objects.filter(
        status=Reservation.Status.ACTIVE,
        holder__isnull=False,
        period__startswith__gt=timezone.now(),
        # A switched-off (or deactivated) department keeps its reservations.
        place__room__floor__pool__desk_settings__enabled=True,
        place__room__floor__pool__is_active=True,
    ).select_related("place__room__floor", "holder", "series__place__room__floor")
    if user is not None:
        qs = qs.filter(holder=user)
    if place is not None:
        qs = qs.filter(place=place)
    users = {}
    verdicts = {}
    cancelled = []
    for res in qs:
        # A fresh user instance: never a stale roles cache.
        holder = users.get(res.holder_id)
        if holder is None:
            holder = users[res.holder_id] = get_user_model().objects.get(pk=res.holder_id)
        key = (res.holder_id, res.place_id)
        if key not in verdicts:
            verdicts[key] = rights.can_book_place(holder, res.place)
        if verdicts[key]:
            continue
        now = timezone.now()
        updated = Reservation.objects.filter(
            pk=res.pk, status=Reservation.Status.ACTIVE
        ).update(
            status=Reservation.Status.CANCELLED,
            released_at=now,
            release_reason=Reservation.ReleaseReason.RIGHTS,
        )
        if updated:
            cancelled.append(res)
            series = res.series
            if series is not None and series.cancelled_at is None:
                skey = (res.holder_id, series.place_id)
                if skey not in verdicts:
                    verdicts[skey] = rights.can_book_place(holder, series.place)
                if not verdicts[skey]:
                    Series.objects.filter(pk=series.pk, cancelled_at__isnull=True).update(
                        cancelled_at=now
                    )
                    series.cancelled_at = now
    _notify_all(cancelled, Reservation.ReleaseReason.RIGHTS)
    return len(cancelled)
