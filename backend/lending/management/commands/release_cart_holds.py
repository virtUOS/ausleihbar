# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Release expired cart holds, freeing their reserved resources.

A cart holds its resources until ``expires_at`` (configurable via the cart
setting, default 30 minutes; renewed on every cart action). Availability already
treats an expired cart as free, so this command is a tidiness/consistency pass:
it cancels lapsed carts and deactivates their items. Idempotent — safe to run
frequently on a schedule (e.g. every 5–10 minutes).

Usage: python manage.py release_cart_holds
"""
from django.core.management.base import BaseCommand

from lending.services import release_expired_holds


class Command(BaseCommand):
    help = "Release expired cart holds (free their reserved resources)."

    def handle(self, *args, **options):
        released = release_expired_holds()
        self.stdout.write(
            self.style.SUCCESS(f"Released {released} expired cart hold(s).")
        )
