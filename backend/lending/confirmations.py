# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""When to send confirmation mails for multi-pool orders (#26).

A confirmation that completes the order is mailed at once (one combined mail).
Otherwise the mail is held until the daily send time and then sent as a clearly
marked partial confirmation — unless it is already past the send time, or a
confirmed part's pickup starts before the next send time.

Dispatch locks the order's rows (``select_for_update``) before deciding and
claims the parts it is about to mail with a conditional update, so two
callers racing on the same order — two lenders confirming both parts at
once, or an overlapping ``send_confirmation_mails`` run — can't both decide
to send and end up mailing the same confirmation twice.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from catalog.models import NotificationSetting

from .models import Booking
from .notifications import send_confirmation_email


def _today_send_time(now):
    t = NotificationSetting.load().confirmation_send_time
    local = timezone.localtime(now)
    return local.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def _pool_sort_key(part):
    """Same ordering as ``Booking.order_parts()`` (pool position, name, id)."""
    pool = part.resource_pool
    return (pool.position if pool else 0, pool.name if pool else "", part.id)


def dispatch_confirmation_mails(booking, now=None):
    """Send this order's due confirmation mail now, if it should go out yet.

    Returns ``True`` if the order was settled by this call — a mail was sent,
    or there was nothing left to send it to (no recipient address). Returns
    ``False`` if the mail is still being held until the send time, or if a
    send attempt failed and should be retried on a later call (e.g. by the
    ``send_confirmation_mails`` command).

    The whole decision — reading state, checking whether to hold, and
    claiming the parts about to be mailed — runs under a row lock on the
    order (``select_for_update``), so a concurrent call on the same order
    (another lender confirming the other part, or an overlapping command
    run) blocks until this one is done and then sees the parts already
    claimed, instead of both deciding to send.
    """
    now = now or timezone.now()
    with transaction.atomic():
        # Lock only the booking rows themselves (of=("self",)): resource_pool
        # is nullable, and Postgres refuses FOR UPDATE across the resulting
        # outer join.
        locked = Booking.objects.select_for_update(of=("self",)).select_related(
            "resource_pool"
        )
        if booking.checkout_id:
            locked = locked.filter(checkout_id=booking.checkout_id)
        else:
            locked = locked.filter(id=booking.id)
        # Lock in a fixed, id-based order so two overlapping orders' rows
        # are always acquired in the same sequence (avoids deadlocks); the
        # mail itself still lists parts pool-ordered, as order_parts() does.
        parts = sorted(locked.order_by("id"), key=_pool_sort_key)

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

        due_ids = [p.id for p in due]
        claimed = Booking.objects.filter(
            id__in=due_ids, confirmation_mailed_at__isnull=True
        ).update(confirmation_mailed_at=now)
        if not claimed:
            # Nothing left to claim — a concurrent call already took it.
            # Shouldn't happen while we hold the row lock, but stay
            # defensive rather than sending a mail nobody's waiting on.
            return False

        recipient = due[0].borrower.email
        sent = send_confirmation_email(due, open_parts=open_parts)
        if not sent and recipient:
            # A real send failure (e.g. an SMTP outage) — release the claim
            # so a later dispatch (the periodic command) retries. Only
            # touch rows still carrying our own stamp, in case something
            # else has already reclaimed them since.
            Booking.objects.filter(
                id__in=due_ids, confirmation_mailed_at=now
            ).update(confirmation_mailed_at=None)
            return False
        # No recipient: nothing to send and nothing to retry — leave the
        # parts marked mailed so they aren't re-checked on every run.
        return True
