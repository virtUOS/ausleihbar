# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""The single place that decides whether a person may be shown.

- **Opt-out** (``DeskProfile.hide_name``, off by default) hides the holder of
  **desks** from everyone but the holder — department admins and assistants
  included. Meeting room holders are always shown.
- Reservations snapshot the opt-out in ``holder_hidden`` when they are
  created (moves and swaps stay within one kind of place, so the snapshot
  stays valid); ``set_hide_name`` updates the person's reservations that
  have not ended yet.
- For a hidden holder no user id (holder or booker) and no comment leaves
  the API either, except to the holder; admins act on the reservation id.
- Retention: ``anonymize_due`` clears holder, booker and comment once a
  reservation ended ``retention_days`` ago (hidden desk holders right after
  the end) and deletes absences and ended requests after the retention.

Viewer ``None`` means the public (displays): never a hidden name.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Func, Q, UUIDField
from django.utils import timezone

from . import hours, rights
from .models import (
    Absence, DeskProfile, DeskSettings, Floor, Place, ReleaseRequest, Reservation, Series,
    SwapRequest,
)

DEFAULT_RETENTION_DAYS = DeskSettings._meta.get_field("retention_days").default
NEUTRAL_RELEASE_REASON = "other"


def display_name(user) -> str:
    return (user.get_full_name() or user.get_username()) if user else ""


def hides_name(user) -> bool:
    """The person's current opt-out."""
    if user is None or not getattr(user, "pk", None):
        return False
    return DeskProfile.objects.filter(user_id=user.pk, hide_name=True).exists()


def snapshot_hidden(holder, place) -> bool:
    """``holder_hidden`` for a new reservation of ``place``."""
    return place.kind == Place.Kind.DESK and hides_name(holder)


def is_hidden(reservation) -> bool:
    return bool(reservation.holder_hidden and reservation.place.kind == Place.Kind.DESK)


def _is_self(viewer, user_id) -> bool:
    return bool(viewer is not None and user_id is not None and getattr(viewer, "pk", None) == user_id)


def _visible_to(reservation, viewer) -> bool:
    """Whether ``viewer`` may see who holds ``reservation``."""
    return not is_hidden(reservation) or _is_self(viewer, reservation.holder_id)


def holder_label(reservation, *, viewer) -> str | None:
    """The holder's name for ``viewer``; ``None`` when anonymized or hidden
    (the UI shows "Person (verborgen)")."""
    if reservation.holder_id is None or not _visible_to(reservation, viewer):
        return None
    return display_name(reservation.holder) or None


def user_id_for(reservation, user_id, *, viewer):
    """A user id of the reservation (holder or booker), or ``None`` when the
    holder is hidden from ``viewer``."""
    return user_id if _visible_to(reservation, viewer) else None


def comment_for(reservation, *, viewer) -> str:
    """Desk comments of a hidden holder might name the person."""
    return reservation.comment if _visible_to(reservation, viewer) else ""


def release_reason_for(reservation, *, viewer) -> str:
    """An absence is shown only to the holder and the department's current
    admins and assistants; everyone else sees a neutral reason."""
    reason = reservation.release_reason
    if reason != Reservation.ReleaseReason.ABSENCE:
        return reason
    if _is_self(viewer, reservation.holder_id):
        return reason
    if viewer is not None and reservation.place.room.floor.pool_id in rights.assistant_pool_ids(viewer):
        return reason
    return NEUTRAL_RELEASE_REASON


def series_hidden(series) -> bool:
    """Series have no snapshot: the holder's current opt-out (desks only)."""
    return series.place.kind == Place.Kind.DESK and hides_name(series.holder)


def series_user_id(series, user_id, *, viewer):
    if series_hidden(series) and not _is_self(viewer, series.holder_id):
        return None
    return user_id


def hidden_user_ids(user_ids) -> set[int]:
    """Of ``user_ids``, those who opted out (one query)."""
    user_ids = {u for u in user_ids if u}
    if not user_ids:
        return set()
    return set(
        DeskProfile.objects.filter(user_id__in=user_ids, hide_name=True).values_list(
            "user_id", flat=True
        )
    )


def fixed_owner_label(place, *, viewer, hidden_ids=None) -> str | None:
    """Name of a fixed place's owner (no reservation to snapshot: the
    owner's current opt-out counts). ``hidden_ids`` (from
    ``hidden_user_ids``) avoids a query per place."""
    owner = place.fixed_owner
    if owner is None:
        return None
    hidden = owner.pk in hidden_ids if hidden_ids is not None else hides_name(owner)
    if hidden and not _is_self(viewer, owner.pk):
        return None
    return display_name(owner) or None


def get_hide_name(user) -> bool:
    return hides_name(user)


def set_hide_name(user, hide: bool) -> None:
    """Store the opt-out. Hiding applies to all of the person's desk
    reservations that still carry the holder (ended ones are anonymized by
    the next ``anonymize_due``); un-hiding only to those not ended yet."""
    with transaction.atomic():
        DeskProfile.objects.update_or_create(user=user, defaults={"hide_name": bool(hide)})
        rows = Reservation.objects.filter(holder=user, place__kind=Place.Kind.DESK)
        if hide:
            # Ended ones too: the next retention pass anonymizes them.
            rows.update(holder_hidden=True)
        else:
            # Ended reservations stay hidden (and are anonymized anyway).
            rows.filter(period__endswith__gt=timezone.now()).update(holder_hidden=False)


# Retention ----------------------------------------------------------------


def _retention_by_pool() -> dict[int, int]:
    """Retention days of every pool that has floors (default when unset)."""
    pool_ids = set(Floor.objects.values_list("pool_id", flat=True).distinct())
    configured = dict(
        DeskSettings.objects.filter(pool_id__in=pool_ids).values_list("pool_id", "retention_days")
    )
    return {pid: configured.get(pid, DEFAULT_RETENTION_DAYS) for pid in pool_ids}


def _personal_data():
    return Q(holder__isnull=False) | Q(booked_by__isnull=False) | ~Q(comment="") | Q(
        series__isnull=False
    )


def _anonymize(qs) -> int:
    rows = qs.filter(_personal_data())
    # Record a no-show before the holder link goes (same rule as
    # ``desks_tick``, which skips anonymized rows).
    rows.filter(
        status=Reservation.Status.ACTIVE, checked_in_at__isnull=True, no_show=False,
        owner_use=False,
    ).update(no_show=True)
    # A fresh group per row: the shared group would re-link the anonymized
    # rows of one booking action.
    return rows.update(
        holder=None, booked_by=None, comment="", series=None,
        group=Func(function="gen_random_uuid", output_field=UUIDField()),
    )


def _anonymize_series(qs) -> int:
    return qs.filter(
        Q(holder__isnull=False) | Q(booked_by__isnull=False) | ~Q(comment="")
    ).update(holder=None, booked_by=None, comment="")


def anonymize_due(now=None) -> dict:
    """Retention pass (``desks_daily``). Idempotent; returns counts."""
    now = now or timezone.now()
    today = timezone.localtime(now, hours.TZ).date()
    counts = {"reservations": 0, "series": 0, "absences": 0, "requests": 0}
    retention = _retention_by_pool()
    with transaction.atomic():
        # Opted-out desk holders: right after the end (series: after the
        # last day or the cancellation).
        counts["series"] += _anonymize_series(
            Series.objects.filter(
                place__kind=Place.Kind.DESK,
                holder__desk_profile__hide_name=True,
            ).filter(Q(valid_until__lt=today) | Q(cancelled_at__lte=now))
        )
        counts["reservations"] += _anonymize(
            Reservation.objects.filter(
                holder_hidden=True, place__kind=Place.Kind.DESK, period__endswith__lte=now
            )
        )
        for pool_id, days in retention.items():
            cutoff = now - timedelta(days=days)
            in_pool = Q(place__room__floor__pool_id=pool_id)
            # Ended requests go before their reservations lose the holder.
            counts["requests"] += _delete_requests(in_pool, cutoff)
            counts["reservations"] += _anonymize(
                Reservation.objects.filter(in_pool, period__endswith__lte=cutoff)
            )
            last_day = today - timedelta(days=days)
            counts["series"] += _anonymize_series(
                Series.objects.filter(in_pool).filter(
                    Q(valid_until__lt=last_day) | Q(cancelled_at__lte=cutoff)
                )
            )
        counts["absences"] = _delete_absences(today, retention)
    return counts


def _delete_requests(in_pool: Q, cutoff) -> int:
    """Requests touching a reservation that ended before ``cutoff`` (open
    ones are long stale by then)."""
    ended = Reservation.objects.filter(in_pool, period__endswith__lte=cutoff)
    release = ReleaseRequest.objects.filter(reservation__in=ended)
    swap = SwapRequest.objects.filter(
        Q(from_reservation__in=ended) | Q(to_reservation__in=ended)
    )
    deleted = release.delete()[1].get(ReleaseRequest._meta.label, 0)
    deleted += swap.delete()[1].get(SwapRequest._meta.label, 0)
    return deleted


def _delete_absences(today, retention: dict[int, int]) -> int:
    """Absences have no department: the shortest retention of the person's
    departments applies (the default when they belong to none)."""
    shortest = min([DEFAULT_RETENTION_DAYS, *retention.values()])
    candidates = Absence.objects.filter(end_date__lt=today - timedelta(days=shortest)).select_related("user")
    doomed = []
    for absence in candidates:
        pools = rights.member_pool_ids(absence.user)
        days = min((retention.get(p, DEFAULT_RETENTION_DAYS) for p in pools), default=DEFAULT_RETENTION_DAYS)
        if absence.end_date < today - timedelta(days=days):
            doomed.append(absence.pk)
    Absence.objects.filter(pk__in=doomed).delete()
    return len(doomed)
