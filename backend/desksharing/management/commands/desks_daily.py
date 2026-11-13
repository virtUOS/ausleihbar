# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Daily desksharing housekeeping.

- Retention: anonymizes ended reservations and series after the
  department's ``retention_days`` (opted-out desk holders right after the
  end), deletes old absences and ended swap/release requests.
- Cancels future reservations whose holders no longer have the right to
  book the place (e.g. group membership by claim changed).

- Sends the daily summary mails (from ``DESKS_SUMMARY_HOUR`` on, once per
  person and day) and the series extension reminders (28 and 7 days before
  the end). Run it at or after the summary hour, e.g. daily at 07:00.

Usage: python manage.py desks_daily
"""
from django.core.management.base import BaseCommand

from desksharing import absences, privacy, reminders


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
        summaries = reminders.send_daily_summaries()
        extensions = reminders.send_series_reminders()
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {summaries} daily summary mail(s) and {extensions} series reminder(s)."
            )
        )
