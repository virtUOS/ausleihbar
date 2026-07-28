# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Remind lenders to retire or reactivate long-standing defective resources.

Finds resources that have been defective for at least --days (default 14) and
emails the lenders of each affected pool (falling back to admins). Idempotent in
effect — running it again just re-sends the reminder. Intended to run on a
schedule (concept §3.6).

Usage: python manage.py review_defects [--days 14]
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import PoolMembership, User
from catalog.models import ResourceDefect
from lending.notifications import send_defect_review


class Command(BaseCommand):
    help = "Email lenders about resources defective for too long (concept §3.6)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["days"])
        open_defects = (
            ResourceDefect.objects.filter(
                resolved_at__isnull=True, created_at__lte=cutoff
            )
            .select_related("resource__product", "resource__resource_pool")
            .order_by("resource__resource_pool__name", "resource__inventory_number")
        )

        by_pool = {}
        for defect in open_defects:
            resource = defect.resource
            if resource.status != resource.Status.DEFECTIVE:
                continue
            pool = resource.resource_pool
            by_pool.setdefault(pool.id, (pool, []))[1].append(
                (resource, timezone.localtime(defect.created_at).date())
            )

        admin_emails = list(
            User.objects.filter(is_superuser=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )
        sent = 0
        for pool, rows in by_pool.values():
            lender_emails = list(
                PoolMembership.objects.filter(resource_pool=pool)
                .exclude(user__email="")
                .values_list("user__email", flat=True)
            )
            recipients = set(lender_emails or admin_emails)
            for recipient in recipients:
                if send_defect_review(recipient, pool, rows):
                    sent += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Reviewed {len(by_pool)} pool(s); sent {sent} reminder(s)."
            )
        )
