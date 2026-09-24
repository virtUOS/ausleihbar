# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Flush confirmation mails that were held for a multi-pool order (#26).

A confirmation that completes an order is mailed immediately; otherwise it is
held until the daily send time (or sent sooner if already past it, or if a
due part's pickup is urgent) — see ``lending.confirmations``. This command
catches every order with a due-but-unmailed confirmation and flushes it via
the same dispatch logic. Idempotent — safe to run frequently on a schedule
(e.g. every 10 minutes).

Usage: python manage.py send_confirmation_mails
"""
from django.core.management.base import BaseCommand

from lending.confirmations import dispatch_confirmation_mails
from lending.models import Booking


class Command(BaseCommand):
    help = "Send held (partial) confirmation mails that are due (#26). Run every 10 min."

    def handle(self, *args, **options):
        due = (
            Booking.objects.filter(confirmed_at__isnull=False, confirmation_mailed_at__isnull=True)
            .exclude(status=Booking.Status.CANCELLED)
        )
        seen, sent = set(), 0
        for booking in due:
            key = booking.checkout_id or f"b{booking.id}"
            if key in seen:
                continue
            seen.add(key)
            if dispatch_confirmation_mails(booking):
                sent += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} confirmation mail(s)."))
