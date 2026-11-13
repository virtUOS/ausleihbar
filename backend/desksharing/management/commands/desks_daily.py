# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Daily desksharing housekeeping.

Cancels future reservations whose holders no longer have the right to book
the place (e.g. group membership by claim changed). Later tasks add more
daily jobs here.

Usage: python manage.py desks_daily
"""
from django.core.management.base import BaseCommand

from desksharing import absences


class Command(BaseCommand):
    help = "Daily desksharing housekeeping (lost rights, ...)."

    def handle(self, *args, **options):
        cancelled = absences.revoke_lost_rights()
        self.stdout.write(
            self.style.SUCCESS(f"Cancelled {cancelled} reservation(s) after lost rights.")
        )
