# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Cancel never-collected reservations whose lending period has passed.

A confirmed/pending reservation that was never picked up and whose booked
period is entirely in the past is a no-show: it held its slots pointlessly
(issue #45). This command cancels those bookings (freeing the slots; history
is kept). Idempotent — safe to run on a daily schedule.

Usage:
    python manage.py expire_uncollected_bookings
    python manage.py expire_uncollected_bookings --dry-run
"""
from django.core.management.base import BaseCommand

from lending.services import cancel_uncollected_bookings


class Command(BaseCommand):
    help = "Cancel never-collected reservations whose lending period has passed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many would be cancelled without changing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        count = cancel_uncollected_bookings(dry_run=dry_run)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Would cancel {count} uncollected reservation(s) (dry run)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Cancelled {count} uncollected reservation(s).")
            )
