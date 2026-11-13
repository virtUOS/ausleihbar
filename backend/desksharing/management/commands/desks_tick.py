# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Release or mark unused desksharing reservations (grace and scarcity).

Reservations without check-in are released after the short grace while places
of their kind are scarce, otherwise marked "potentially free" after the normal
grace. Idempotent; run every 5 minutes.

Usage: python manage.py desks_tick
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from desksharing.release import tick
from desksharing.requests import expire_requests


class Command(BaseCommand):
    help = "Release or mark unused desksharing reservations (grace and scarcity)."

    def handle(self, *args, **options):
        now = timezone.now()
        result = tick(now)
        expired = expire_requests(now)
        self.stdout.write(
            self.style.SUCCESS(
                f"Released {result.released} reservation(s), "
                f"marked {result.marked} as potentially free, "
                f"expired {expired} request(s)."
            )
        )
