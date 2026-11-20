# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Email borrowers about missed pickups and missed returns (#221).

Intended to run daily. Schedules (first mail, interval, maximum count) are
set per kind in the notification settings; per-booking counters make running
it more often harmless. After the last return reminder the pool's contact is
told once (``lending.services.send_overdue_reminders``).
"""
from django.core.management.base import BaseCommand

from lending.services import send_overdue_reminders


class Command(BaseCommand):
    help = "Email borrowers about overdue pickups/returns (and pools after the last one)."

    def handle(self, *args, **options):
        sent = send_overdue_reminders()
        self.stdout.write(self.style.SUCCESS(
            f"Sent {sent['pickup']} pickup reminder(s), {sent['return']} return "
            f"reminder(s), {sent['pool']} pool notice(s)."
        ))
