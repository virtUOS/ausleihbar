# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Warn upcoming borrowers when their reserved unit is still out.

When a device is overdue (not returned) and a new pickup approaches, this
command rebooks the upcoming booking onto a free unit where possible, and
otherwise notifies the borrower a configurable lead time before pickup
(Product.missing_notice_lead). Idempotent — safe on a periodic schedule.

Usage:
    python manage.py notify_missing_products
    python manage.py notify_missing_products --dry-run
"""
from django.core.management.base import BaseCommand

from lending.services import notify_missing_products


class Command(BaseCommand):
    help = "Rebook or warn upcoming borrowers when their unit is still out."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts without rebooking, mailing, or marking.",
        )

    def handle(self, *args, **options):
        result = notify_missing_products(dry_run=options["dry_run"])
        msg = (
            f"rebooked {result['rebooked']}, notified {result['notified']}"
            + (" (dry run)" if options["dry_run"] else "")
        )
        self.stdout.write(self.style.SUCCESS(msg))
