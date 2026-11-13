# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Daily desksharing housekeeping.

- Retention: anonymizes ended reservations and series after the
  department's ``retention_days`` (opted-out desk holders right after the
  end), deletes old absences and ended swap/release requests.
- Cancels future reservations whose holders no longer have the right to
  book the place (e.g. group membership by claim changed).

Later tasks add series reminders and the daily summary here.

Usage: python manage.py desks_daily
"""
from django.core.management.base import BaseCommand

from desksharing import absences, privacy


class Command(BaseCommand):
    help = "Daily desksharing housekeeping (retention, lost rights, ...)."

    def handle(self, *args, **options):
        counts = privacy.anonymize_due()
        self.stdout.write(
            self.style.SUCCESS(
                "Retention: anonymized {reservations} reservation(s) and {series} series, "
                "deleted {absences} absence(s) and {requests} request(s).".format(**counts)
            )
        )
        cancelled = absences.revoke_lost_rights()
        self.stdout.write(
            self.style.SUCCESS(f"Cancelled {cancelled} reservation(s) after lost rights.")
        )
