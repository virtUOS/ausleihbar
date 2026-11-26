# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Cancel never-collected reservations whose lending period has passed.

A confirmed/pending reservation that was never picked up and whose booked
period is entirely in the past is a no-show: it held its slots pointlessly
(issue #45). This command cancels those bookings (freeing the slots; history
is kept). It also closes self-service on-site items (#116) whose period has
ended as used. First it releases items that require a check-in and missed it
(``lending.checkin.release_due_items``, normally done every 5 minutes by
``release_unstarted_items``) — a fallback so such items never stay open when
that job is missing. Idempotent — safe to run on a daily schedule.

Usage:
    python manage.py expire_uncollected_bookings
    python manage.py expire_uncollected_bookings --dry-run
"""
from django.core.management.base import BaseCommand

from lending.checkin import release_due_items
from lending.services import (
    cancel_uncollected_bookings,
    complete_self_service_items,
)


class Command(BaseCommand):
    help = (
        "Cancel never-collected reservations whose lending period has passed "
        "and close ended self-service on-site items (releases missed "
        "check-ins first)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many would be cancelled without changing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        # Before the others: a released item no longer counts as uncollected
        # or as a self-service use to close.
        released = release_due_items(dry_run=dry_run)
        count = cancel_uncollected_bookings(dry_run=dry_run)
        closed = complete_self_service_items(dry_run=dry_run)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Would cancel {count} uncollected reservation(s) and close "
                    f"{closed} on-site item(s) as used; would release {released} "
                    "unstarted item(s) (dry run)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cancelled {count} uncollected reservation(s); "
                    f"{closed} on-site item(s) closed as used; released {released} "
                    "unstarted item(s)."
                )
            )
