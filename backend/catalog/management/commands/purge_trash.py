# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Hard-delete trashed catalog objects past the retention window (#7).

Soft-deleted rows (``deleted_at`` set) are kept for ``TrashSetting.retention_days``
(default 30) so admins can restore them via the trash API. This command purges
anything older than the cutoff for good.

Models are processed in dependency-safe order so PROTECT FKs (Resource ->
Product/ResourcePool, Product -> ProductType) don't raise ``ProtectedError``:
Resource is purged before Product and ResourcePool, and Product before
ProductType. The deletion collector sees trashed rows too, since these models
use ``base_manager_name = "all_objects"``.

Defense in depth: the manage endpoints already block trashing a Resource with
any booking history (``lending.BookingItem.resource`` is PROTECT), so a
trashed Resource should never be referenced by a live BookingItem. But in
case an older/legacy row slips through, each model's batch delete is wrapped
in try/except ``ProtectedError`` — a protected row is skipped (with a warning)
rather than aborting the whole run, so one bad row can't brick the schedule.

Usage: python manage.py purge_trash [--dry-run]
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import ProtectedError
from django.utils import timezone

from catalog.models import (
    Category,
    Product,
    ProductSet,
    ProductType,
    Resource,
    ResourcePool,
    Section,
    TrashSetting,
)

# Dependency-safe order: dependents before their PROTECT-ed referents.
MODELS = [Resource, Product, ProductSet, ProductType, Category, Section, ResourcePool]


class Command(BaseCommand):
    help = "Hard-delete trashed catalog objects past the retention window (#7)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count what would be purged without deleting anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=TrashSetting.load().retention_days)
        total = 0
        for model in MODELS:
            qs = model.all_objects.dead().filter(deleted_at__lt=cutoff)
            n = qs.count()
            if not n:
                continue
            if dry_run:
                total += n
                continue
            try:
                qs.delete()
            except ProtectedError:
                self.stderr.write(
                    self.style.WARNING(
                        f"Skipped {n} trashed {model.__name__} row(s): still "
                        "referenced by a protected object; leaving them in "
                        "the trash for manual cleanup."
                    )
                )
                continue
            total += n
        prefix = "DRY-RUN: would purge" if dry_run else "Purged"
        self.stdout.write(f"{prefix} {total} trashed object(s).")
