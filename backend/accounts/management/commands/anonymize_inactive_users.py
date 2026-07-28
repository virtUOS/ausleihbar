# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Anonymize accounts inactive past the retention window (GDPR).

Anonymizes accounts that have had no activity for the configured period and
have no open lending process; their device/booking history is kept under a
neutral placeholder. Off unless enabled in the retention setting. Meant to run
on a schedule (e.g. weekly).

Usage:
    python manage.py anonymize_inactive_users [--dry-run] [--retention-days N] [--force]
"""
from django.core.management.base import BaseCommand

from accounts import retention


class Command(BaseCommand):
    help = "Anonymize long-inactive accounts (data retention / GDPR)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be anonymized without changing anything.",
        )
        parser.add_argument(
            "--retention-days", type=int, default=None,
            help="Override the inactivity window (days) from the retention setting.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Run even if the retention setting is disabled.",
        )

    def handle(self, *args, **options):
        result = retention.run(
            retention_days=options["retention_days"],
            dry_run=options["dry_run"],
            force=options["force"],
        )
        if not result["enabled"]:
            self.stdout.write(
                "Data retention is disabled — enable it in the retention "
                "setting or pass --force. Nothing done."
            )
            return
        verb = "Would anonymize" if result["dry_run"] else "Anonymized"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {result['candidates']} inactive account(s) "
                f"(window: {result['retention_days']} days)."
            )
        )
