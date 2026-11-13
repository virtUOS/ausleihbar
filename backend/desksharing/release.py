# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Grace and scarcity: release or mark unused reservations.

Without check-in, a reservation is **released** once its short grace has
passed (measured from its start, or from an announced later arrival) while
places of its kind are scarce in the department. Otherwise, after the normal
grace, it becomes **potentially free**: the holder keeps it, but it is
released as soon as places become scarce. Both count as a no-show.
Fixed places' own reservations and checked-in ones are never touched.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F

from . import absences, booking, hours, notify
from .models import DeskSettings, Place, Reservation

RELEASED_NO_SHOW = "released_no_show"
GRACE_NUDGE = "grace_nudge"


@dataclass
class TickResult:
    released: int = 0
    marked: int = 0


def _prefix(kind: str) -> str:
    return "room" if kind == Place.Kind.MEETING_ROOM else "desk"


def _setting(settings_, kind, name) -> int:
    return getattr(settings_, f"{_prefix(kind)}_{name}")


def _hour_range(at: datetime):
    """The local grid hour containing ``at``."""
    local = at.astimezone(hours.TZ)
    return hours.local_range(local.date(), local.hour, local.hour + 1)


def free_count(pool, kind, at: datetime) -> int:
    """Bookable places of ``pool`` and ``kind`` without an active reservation
    covering ``at``, regardless of anyone's rights. A fixed place counts as
    taken unless its owner is absent. Potentially free reservations count
    as taken (they are not offered to others)."""
    places = list(
        Place.objects.filter(
            room__floor__pool=pool, kind=kind, is_active=True,
            room__is_active=True, room__floor__is_active=True,
        )
    )
    taken = set(
        Reservation.objects.filter(
            place_id__in=[p.pk for p in places],
            status=Reservation.Status.ACTIVE,
            period__contains=at,
        ).values_list("place_id", flat=True)
    )
    hour = _hour_range(at)
    return sum(
        1
        for p in places
        if p.pk not in taken
        and not (p.fixed_owner_id and not absences.fixed_place_available(p, hour))
    )


def is_scarce(pool, kind, at: datetime, settings_=None) -> bool:
    settings_ = settings_ or DeskSettings.for_pool(pool)
    return free_count(pool, kind, at) < _setting(settings_, kind, "scarcity_free_below")


def _alternatives(reservation, now) -> list[Place]:
    """Free places of the same kind for the rest of the reservation."""
    if reservation.holder is None:
        return []
    day, _start, end_hour = hours.local_day_hours(reservation.period)
    hour = now.astimezone(hours.TZ).hour
    if hour >= end_hour:
        return []
    place = reservation.place
    return [
        p
        for p in booking.free_places(
            place.pool, place.kind, day, hour, end_hour, for_user=reservation.holder
        )
        if p.pk != place.pk
    ]


def _evaluate(pk, now, settings_cache) -> str | None:
    """Release or mark one reservation; returns "released", "marked" or None."""
    with transaction.atomic():
        res = (
            Reservation.objects.select_for_update(skip_locked=True)
            .filter(
                pk=pk,
                status=Reservation.Status.ACTIVE,
                checked_in_at__isnull=True,
            )
            .first()
        )
        if res is None:
            return None
        place = Place.objects.select_related("room__floor__pool").get(pk=res.place_id)
        res.place = place
        pool = place.pool
        if pool.pk not in settings_cache:
            settings_cache[pool.pk] = DeskSettings.for_pool(pool)
        settings_ = settings_cache[pool.pk]
        start = res.period.lower
        base = max(start, res.late_until) if res.late_until else start
        short = timedelta(minutes=_setting(settings_, place.kind, "grace_short_min"))
        normal = timedelta(minutes=_setting(settings_, place.kind, "grace_normal_min"))
        if now >= base + short and is_scarce(pool, place.kind, now, settings_):
            res.status = Reservation.Status.RELEASED
            res.released_at = now
            res.release_reason = Reservation.ReleaseReason.NO_SHOW
            res.no_show = True
            res.save(update_fields=["status", "released_at", "release_reason", "no_show"])
            action = "released"
        elif (
            res.potentially_free_at is None
            and now >= start + normal
            and (res.late_until is None or res.late_until <= now)
        ):
            res.potentially_free_at = now
            res.no_show = True
            res.save(update_fields=["potentially_free_at", "no_show"])
            action = "marked"
        else:
            return None
    # Outside the transaction: the row lock is not held while mailing.
    if res.holder_id:
        if action == "released":
            notify.notify(
                res.holder,
                RELEASED_NO_SHOW,
                {"reservation": res, "alternatives": _alternatives(res, now)},
            )
        else:
            notify.notify(res.holder, GRACE_NUDGE, {"reservation": res})
    return action


def tick(now: datetime) -> TickResult:
    """One pass over the running, not checked-in reservations. Idempotent;
    rows locked by a concurrent transaction are skipped until the next run."""
    candidates = (
        Reservation.objects.filter(
            status=Reservation.Status.ACTIVE,
            checked_in_at__isnull=True,
            period__startswith__lte=now,
            period__endswith__gt=now,
        )
        .exclude(holder_id=F("place__fixed_owner_id"))
        .order_by("period", "pk")
        .values_list("pk", flat=True)
    )
    result = TickResult()
    settings_cache = {}
    for pk in list(candidates):
        action = _evaluate(pk, now, settings_cache)
        if action == "released":
            result.released += 1
        elif action == "marked":
            result.marked += 1
    return result
