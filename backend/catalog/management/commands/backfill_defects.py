# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Open defect-history records for resources that are already defective."""
from django.core.management.base import BaseCommand

from catalog.defects import backfill_open_defects


class Command(BaseCommand):
    help = "Open defect-history records for currently-defective resources."

    def handle(self, *args, **options):
        created = backfill_open_defects()
        self.stdout.write(
            self.style.SUCCESS(f"Backfilled {created} open defect record(s).")
        )
