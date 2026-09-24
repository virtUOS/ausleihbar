# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""When to send confirmation mails for multi-pool orders (#26).

A confirmation that completes the order is mailed at once (one combined mail).
Otherwise the mail is held until the daily send time and then sent as a clearly
marked partial confirmation — unless it is already past the send time, or a
confirmed part's pickup starts before the next send time.
"""
from datetime import timedelta

from django.utils import timezone

from catalog.models import NotificationSetting

from .models import Booking
from .notifications import send_confirmation_email


def _today_send_time(now):
    t = NotificationSetting.load().confirmation_send_time
    local = timezone.localtime(now)
    return local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def dispatch_confirmation_mails(booking, now=None):
    """Send this order's due confirmation mail now, if it should go out yet.

    Returns ``True`` if a mail was sent. A "due" part is one that has been
    confirmed but not yet mailed. If every part of the order is confirmed,
    all due parts go out together as one full confirmation. Otherwise the
    mail is held until the pool's daily send time (as a partial confirmation
    naming the still-open parts) unless we're already past that time, or a
    due part's pickup starts before the next send time (urgent).
    """
    now = now or timezone.now()
    parts = booking.order_parts()
    open_parts = [p for p in parts if p.status == Booking.Status.PENDING]
    due = [
        p for p in parts
        if p.confirmed_at and not p.confirmation_mailed_at
        and p.status != Booking.Status.CANCELLED
    ]
    if not due:
        return False
    send_at = _today_send_time(now)
    next_send = send_at if now < send_at else send_at + timedelta(days=1)
    pickups = [
        i.period.lower
        for p in due for i in p.items.filter(is_active=True)
        if i.period.lower is not None
    ]
    urgent = bool(pickups) and min(pickups) < next_send
    if open_parts and now < send_at and not urgent:
        return False  # hold until the send time
    send_confirmation_email(due, open_parts=open_parts)
    Booking.objects.filter(id__in=[p.id for p in due]).update(confirmation_mailed_at=now)
    return True
