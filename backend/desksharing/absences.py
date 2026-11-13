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
from .models import Absence, Reservation

logger = logging.getLogger(__name__)

MAX_ABSENCE_DAYS = 366
RELEASED_OTHER = "released_other"


def _day_range(start: date, end: date):
    """Local [start 00:00, end+1 00:00) as a datetime range."""
    return hours.local_dt(start, 0), hours.local_dt(end + timedelta(days=1), 0)


def _period_days(period) -> tuple[date, date]:
    first = period.lower.astimezone(hours.TZ).date()
    last = (period.upper - timedelta(microseconds=1)).astimezone(hours.TZ).date()
    return first, last


def fixed_place_available(place, period) -> bool:
    """Whether a fixed place is free for others during ``period``: its owner
    has absences covering every local day of the period."""
    if not place.fixed_owner_id:
        return False
    first, last = _period_days(period)
    covered = set()
    for start, end in Absence.objects.filter(
        user_id=place.fixed_owner_id, start_date__lte=last, end_date__gte=first
    ).values_list("start_date", "end_date"):
        day = max(start, first)
        while day <= min(end, last):
            covered.add(day)
            day += timedelta(days=1)
    return (last - first).days + 1 == len(covered)


def _notify(user, reservation, reason: str) -> None:
    if user is None:
        return
    try:
        notify.notify(user, RELEASED_OTHER, {"reservation": reservation, "reason": reason})
    except Exception:
        logger.exception("Notification %s failed for reservation %s", RELEASED_OTHER, reservation.pk)


def _release(reservations, reason: str, *, notify_holders: bool = True) -> int:
    """Release the given active, not yet ended reservations (status
    ``released``; period unchanged, no no-show)."""
    now = timezone.now()
    count = 0
    for res in list(reservations.select_related("holder")):
        with transaction.atomic():
            updated = Reservation.objects.filter(
                pk=res.pk, status=Reservation.Status.ACTIVE
            ).update(
                status=Reservation.Status.RELEASED,
                released_at=now,
                release_reason=reason,
            )
        if not updated:
            continue
        count += 1
        res.status = Reservation.Status.RELEASED
        res.released_at = now
        res.release_reason = reason
        if notify_holders:
            _notify(res.holder, res, reason)
    return count


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
            "invalid_absence", detail=f"End must not precede start; at most {MAX_ABSENCE_DAYS} days."
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
        _release(
            _current(Reservation.objects.filter(holder=user, period__overlap=(lower, upper))),
            Reservation.ReleaseReason.ABSENCE,
            notify_holders=actor.pk != user.pk,
        )
    return absence


def on_block_saved(block) -> int:
    """Release reservations overlapping a system- or pool-scoped block (the
    same scoping as ``hours.closed_hours``); other scopes do not affect
    desksharing."""
    if block.product_id or block.resource_id or block.period is None:
        return 0
    qs = _current(Reservation.objects.filter(period__overlap=block.period))
    if block.resource_pool_id:
        qs = qs.filter(place__room__floor__pool_id=block.resource_pool_id)
    return _release(qs, Reservation.ReleaseReason.BLOCK)


def revoke_lost_rights(user=None, place=None) -> int:
    """Cancel future reservations (not yet started) whose holder may no longer
    book the place. Limited to one user and/or place when given."""
    qs = Reservation.objects.filter(
        status=Reservation.Status.ACTIVE,
        holder__isnull=False,
        period__startswith__gt=timezone.now(),
    ).select_related("place__room__floor", "holder")
    if user is not None:
        qs = qs.filter(holder=user)
    if place is not None:
        qs = qs.filter(place=place)
    users = {}
    verdicts = {}
    count = 0
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
            count += 1
            _notify(res.holder, res, Reservation.ReleaseReason.RIGHTS)
    return count
