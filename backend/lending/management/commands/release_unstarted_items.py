# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Release check-in items that were not started by their deadline.

Items of products with check-in (spec §6.3) that nobody checked in by their
release deadline are released: their slot is free again and the borrower is
told by mail. Idempotent — meant to run every 5 minutes.

Usage:
    python manage.py release_unstarted_items
    python manage.py release_unstarted_items --dry-run
"""
from django.core.management.base import BaseCommand

from lending.checkin import release_due_items


class Command(BaseCommand):
    help = "Release check-in items that were not started by their deadline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many would be released without changing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        count = release_due_items(dry_run=dry_run)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Would release {count} unstarted item(s) (dry run)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Released {count} unstarted item(s).")
            )
