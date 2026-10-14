# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Email borrowers the day before their pickup.

Intended to run hourly; each booking is reminded at most once
(``Booking.pickup_reminded_at``), so running it more often does not spam.
"""
from django.core.management.base import BaseCommand

from lending.services import send_pickup_reminders


class Command(BaseCommand):
    help = "Email borrowers whose confirmed booking is to be picked up tomorrow."

    def handle(self, *args, **options):
        sent = send_pickup_reminders()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} pickup reminder(s)."))
