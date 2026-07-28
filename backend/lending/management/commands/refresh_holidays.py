# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Refresh public holidays for the configured region across the booking horizon.

Reads the system HolidaySetting (country + subdivision) and ensures holiday
blocks exist from this year through the longest pool booking horizon. Idempotent
— safe to run on a schedule (e.g. monthly) so the rolling horizon stays covered.

Usage: python manage.py refresh_holidays
"""
from django.core.management.base import BaseCommand

from lending.services import refresh_holidays


class Command(BaseCommand):
    help = "Load public holidays for the configured region across the booking horizon."

    def handle(self, *args, **options):
        created = refresh_holidays()
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(created)} new holiday block(s).")
        )
