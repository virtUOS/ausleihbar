# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Import public holidays as blocks.

Usage: python manage.py import_holidays --country DE --subdiv NI --year 2026
Add --pool <id> to scope the holidays to a single resource pool.
"""
from django.core.management.base import BaseCommand, CommandError

from catalog.models import ResourcePool
from lending.services import import_holidays


class Command(BaseCommand):
    help = "Create blocks for public holidays of a country/subdivision."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="DE")
        parser.add_argument("--subdiv", default="", help="e.g. NI for Lower Saxony")
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--pool", type=int, help="Resource pool id (optional)")

    def handle(self, *args, **options):
        pool = None
        if options["pool"]:
            try:
                pool = ResourcePool.objects.get(pk=options["pool"])
            except ResourcePool.DoesNotExist as exc:
                raise CommandError(f"Pool {options['pool']} not found.") from exc

        created = import_holidays(
            options["country"], options["subdiv"], options["year"], pool
        )
        self.stdout.write(
            self.style.SUCCESS(f"Imported {len(created)} new holiday block(s).")
        )
