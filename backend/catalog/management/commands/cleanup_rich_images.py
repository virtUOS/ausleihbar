# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Delete orphaned rich-text images (#43).

Uploads to the rich editor land in ``rich/`` in the default storage. Images
that are no longer referenced by any rich field (resource pools, welcome
text, pages — all language columns, trashed rows included) and are older than
``--days`` are removed. The age guard protects images just uploaded into a
form that has not been saved yet.

Usage: python manage.py cleanup_rich_images [--days N] [--dry-run]
"""
from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import Page, ResourcePool, WelcomeSetting
from catalog.richtext import rich_media_names

MODELS = [ResourcePool, WelcomeSetting, Page]


def referenced_rich_images():
    names = set()
    for model in MODELS:
        manager = getattr(model, "all_objects", model._base_manager)
        for field in model.rich_fields:
            for value in manager.values_list(field, flat=True):
                names |= rich_media_names(value)
    return names


class Command(BaseCommand):
    help = "Delete unreferenced rich-text images older than --days (#43)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7,
                            help="Only delete files older than this (default 7).")
        parser.add_argument("--dry-run", action="store_true",
                            help="List the files without deleting them.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=options["days"])
        try:
            _, files = default_storage.listdir("rich")
        except FileNotFoundError:
            files = []
        referenced = referenced_rich_images()
        orphans = []
        for filename in sorted(files):
            name = f"rich/{filename}"
            if name in referenced:
                continue
            modified = default_storage.get_modified_time(name)
            if timezone.is_naive(modified):
                modified = timezone.make_aware(modified)
            if modified < cutoff:
                orphans.append(name)
        for name in orphans:
            self.stdout.write(f"  {name}")
            if not dry_run:
                default_storage.delete(name)
        prefix = "DRY-RUN: would delete" if dry_run else "Deleted"
        self.stdout.write(f"{prefix} {len(orphans)} orphaned rich image(s).")
