# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Cancel never-collected reservations whose lending period has passed.

A confirmed/pending reservation that was never picked up and whose booked
period is entirely in the past is a no-show: it held its slots pointlessly
(issue #45). This command cancels those bookings (freeing the slots; history
is kept). It also closes self-service on-site items (#116) whose period has
ended as used. Idempotent — safe to run on a daily schedule.

Usage:
    python manage.py expire_uncollected_bookings
    python manage.py expire_uncollected_bookings --dry-run
"""
from django.core.management.base import BaseCommand

from lending.services import (
    cancel_uncollected_bookings,
    complete_self_service_items,
)


class Command(BaseCommand):
    help = (
        "Cancel never-collected reservations whose lending period has passed "
        "and close ended self-service on-site items."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many would be cancelled without changing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        count = cancel_uncollected_bookings(dry_run=dry_run)
        closed = complete_self_service_items(dry_run=dry_run)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Would cancel {count} uncollected reservation(s) and close "
                    f"{closed} on-site item(s) as used (dry run)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cancelled {count} uncollected reservation(s); "
                    f"{closed} on-site item(s) closed as used."
                )
            )
