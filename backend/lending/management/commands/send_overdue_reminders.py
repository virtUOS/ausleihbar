# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Email borrowers about overdue pickups and returns.

Intended to run on a daily schedule. A reservation is reminded at most once
per ``RESEND_AFTER_HOURS`` so running it more often does not spam.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from lending.models import Booking
from lending.notifications import send_overdue_reminder
from lending.services import overdue_items

RESEND_AFTER_HOURS = 20


class Command(BaseCommand):
    help = "Email borrowers about overdue pickups/returns."

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(hours=RESEND_AFTER_HOURS)
        bookings = (
            Booking.objects.filter(
                status__in=[Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT]
            )
            .select_related("borrower")
            .prefetch_related(
                "items__resource__product", "items__resource__resource_pool"
            )
        )
        sent = 0
        for booking in bookings:
            if booking.overdue_reminded_at and booking.overdue_reminded_at > cutoff:
                continue
            pickups, returns = overdue_items(booking)
            if not pickups and not returns:
                continue
            if send_overdue_reminder(booking, pickups, returns):
                Booking.objects.filter(pk=booking.pk).update(overdue_reminded_at=now)
                sent += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} overdue reminder(s)."))
