# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""One-click actions from the grace nudge mail ("Ich komme später",
"Freigeben"), authorized by a signed token (``notify.make_action_token``)."""
from datetime import datetime

from django.core import signing
from django.utils import timezone

from . import booking, checkin, notify
from .booking import BookingError
from .models import Reservation


class ActionError(Exception):
    """``status`` is the HTTP status, ``code`` a machine-readable reason."""

    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.status, self.code, self.detail = status, code, detail or code


def _resolve(token: str, user) -> Reservation:
    """The reservation of a valid token owned by ``user``."""
    try:
        reservation_id, user_id = notify.read_action_token(token)
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ActionError(400, "invalid_token", "This link is invalid.") from None
    if user.pk != user_id:
        raise ActionError(403, "wrong_user", "This link belongs to someone else.")
    reservation = (
        Reservation.objects.select_related("place__room__floor__pool", "holder")
        .filter(pk=reservation_id, holder_id=user.pk)
        .first()
    )
    if reservation is None:
        raise ActionError(404, "not_found", "The reservation no longer exists.")
    return reservation


def context(token: str, *, user, now=None) -> dict:
    """What the action page shows before acting; changes nothing."""
    now = now or timezone.now()
    reservation = _resolve(token, user)
    place = reservation.place
    return {
        "reservation": {
            "id": reservation.pk,
            "place": place.name,
            "room": place.room.name,
            "floor": place.room.floor.name,
            "start": reservation.period.lower,
            "end": reservation.period.upper,
            "status": reservation.status,
            "checked_in": reservation.checked_in_at is not None,
        },
        "expired": reservation.period.upper <= now,
    }


def perform(token: str, action: str, *, user, until: datetime | None = None, now=None) -> Reservation:
    now = now or timezone.now()
    reservation = _resolve(token, user)
    if reservation.period.upper <= now:
        raise ActionError(410, "expired", "This link has expired.")
    if reservation.status != Reservation.Status.ACTIVE:
        raise ActionError(409, "already_released", "The reservation was already released.")
    try:
        if action == "later":
            if until is None:
                raise ActionError(400, "until_required", "Choose until when.")
            checkin.come_later(reservation, user=user, until=until, now=now)
        elif action == "release":
            booking.cancel(reservation, actor=user)
        else:
            raise ActionError(400, "invalid_action", "Unknown action.")
    except BookingError as exc:
        raise ActionError(409, exc.code, exc.detail) from None
    return reservation
