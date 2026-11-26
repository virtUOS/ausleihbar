# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Item check-in rules and the release of unstarted items (spec §6.3).

Only items with ``BookingItem.checkin_required`` (a snapshot of the product
setting) take part; every other item behaves as before. The check-in window
opens :data:`CHECKIN_EARLY` before the item's start and closes at its release
deadline (:func:`deadline`); an item not checked in by then is released by
:func:`release_due_items` (``release_unstarted_items`` command): inactive,
never handed out, its slot free again, the borrower told by mail.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Booking, BookingItem

CHECKIN_EARLY = timedelta(minutes=15)

# Static English texts for the 409 responses (the frontend translates by code).
CHECKIN_MESSAGES = {
    "not_required": "This item does not need a check-in.",
    "not_confirmed": "The booking is not confirmed yet.",
    "too_early": "Check-in opens 15 minutes before the start.",
    "too_late": "The check-in time has passed.",
    "already": "Already checked in.",
    "inactive": "This booking position is no longer active.",
}

# Booking statuses whose items hold their slot (and may be released).
HOLDING_STATUSES = (
    Booking.Status.PENDING,
    Booking.Status.CONFIRMED,
    Booking.Status.HANDED_OUT,
)
# Check-in needs a confirmed booking; HANDED_OUT covers mixed bookings whose
# loan items are already out.
_CHECKIN_STATUSES = (Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT)


def deadline(item):
    """When ``item`` is released unless checked in: the later of its start
    and the booking's submission (``created_at`` for older bookings) plus the
    product's ``checkin_release_minutes`` (read now, not snapshotted) —
    but never after the period's end (a check-in after the end would close
    the item handed out after it was returned)."""
    booking = item.booking
    submitted = booking.submitted_at or booking.created_at
    start = item.period.lower
    minutes = item.resource.product.checkin_release_minutes
    result = max(start, submitted) + timedelta(minutes=minutes)
    if item.period.upper is not None:
        result = min(result, item.period.upper)
    return result


def _holds_slot(item):
    return (
        item.is_active
        and item.handed_out_at is None
        and item.released_at is None
        and item.booking.status in HOLDING_STATUSES
    )


def state(item, now):
    """The item's check-in state at ``now``: ``"upcoming"`` (before the
    window), ``"open"`` (window open, before the start), ``"late"`` (started,
    not checked in — also past the deadline until the release job ran),
    ``"checked_in"`` or ``"released"``. ``None`` for items without check-in
    and for cancelled/closed ones."""
    if not item.checkin_required:
        return None
    if item.released_at is not None:
        return "released"
    if item.checked_in_at is not None:
        return "checked_in"
    if not _holds_slot(item):
        return None
    start = item.period.lower
    if now < start - CHECKIN_EARLY:
        return "upcoming"
    if now < start:
        return "open"
    return "late"


def late_minutes(item, now):
    """Whole minutes since the item's start (0 before it)."""
    seconds = (now - item.period.lower).total_seconds()
    return max(0, int(seconds // 60))


def checkin_error(item, now):
    """Why ``item`` can't be checked in at ``now``, or ``None`` if it can.

    Keys: ``"not_required"``, ``"already"``, ``"inactive"``,
    ``"not_confirmed"``, ``"too_early"``, ``"too_late"``.
    """
    if not item.checkin_required:
        return "not_required"
    if item.checked_in_at is not None:
        return "already"
    if not _holds_slot(item):
        return "inactive"
    if item.booking.status not in _CHECKIN_STATUSES:
        return "not_confirmed"
    if now < item.period.lower - CHECKIN_EARLY:
        return "too_early"
    if item.period.upper is not None and now >= item.period.upper:
        return "too_late"
    if now >= deadline(item):
        return "too_late"
    return None


def _locked(item_id):
    """The item re-read under a row lock (only the item row is locked)."""
    return (
        BookingItem.objects.select_for_update(of=("self",))
        .select_related("booking__borrower", "resource__product")
        .get(pk=item_id)
    )


def check_in(item, *, now=None):
    """Check ``item`` in (borrower or a lender on their behalf).

    Locks the row so a concurrent release cannot also win. Raises
    ``ValueError(key)`` with a :func:`checkin_error` key when refused.
    """
    now = now or timezone.now()
    with transaction.atomic():
        locked = _locked(item.pk)
        error = checkin_error(locked, now)
        if error:
            raise ValueError(error)
        locked.checked_in_at = now
        locked.save(update_fields=["checked_in_at"])
    return locked


def _settle_booking(booking):
    """Roll the booking up after a release: cancelled once nothing is left
    active or handed out (like a cancelled booking, no new status),
    otherwise the usual item rollup."""
    remaining = booking.items.filter(
        Q(is_active=True) | Q(handed_out_at__isnull=False)
    )
    if remaining.exists():
        booking._sync_status()
    else:
        booking.cancel()


def release_due_items(now=None, dry_run=False):
    """Release flagged items not checked in by their deadline (idempotent).

    A released item gets ``released_at`` and turns inactive (its slot is free
    again); it is never handed out. The borrower is mailed once per item.
    Returns the number of items released (or that would be, for a dry run).
    """
    from .notifications import send_release_mail

    now = now or timezone.now()
    candidates = BookingItem.objects.filter(
        checkin_required=True,
        is_active=True,
        checked_in_at__isnull=True,
        handed_out_at__isnull=True,
        released_at__isnull=True,
        booking__status__in=HOLDING_STATUSES,
        period__startswith__lte=now,
    ).select_related("booking", "resource__product")
    due = [item.pk for item in candidates if deadline(item) <= now]
    if dry_run:
        return len(due)
    released = []
    for item_id in due:
        with transaction.atomic():
            item = _locked(item_id)
            # Re-check under the lock: a check-in may have won meanwhile.
            if (
                item.checked_in_at is not None
                or not _holds_slot(item)
                or deadline(item) > now
            ):
                continue
            item.released_at = now
            item.is_active = False
            item.save(update_fields=["released_at", "is_active"])
            _settle_booking(item.booking)
        released.append(item)
    for item in released:
        send_release_mail(item)
    return len(released)
