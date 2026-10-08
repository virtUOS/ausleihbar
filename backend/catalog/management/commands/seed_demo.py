# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Populate the database with demo catalog data for the shop.

Idempotent: running it repeatedly does not create duplicates.
Usage: python manage.py seed_demo
"""
from django.core.management.base import BaseCommand

from catalog.models import (
    Category,
    Product,
    ProductType,
    Resource,
    ResourcePool,
    Section,
)


def _category_in_section(section, name):
    """A live top-level category ``name`` placed in ``section`` (appended to
    its display order) — the shop navigation (#78). Idempotent."""
    category = Category.objects.filter(name=name, parent__isnull=True).first()
    if category is None:
        category = Category.objects.create(name=name)
    section.categories.add(category)
    if category.id not in section.category_order:
        section.category_order = [*section.category_order, category.id]
        section.save(update_fields=["category_order"])
    return category


class Command(BaseCommand):
    help = "Create demo sections, product types, products and resources."

    def handle(self, *args, **options):
        pool, _ = ResourcePool.objects.get_or_create(
            pool_id="DigiLab",
            defaults={"name": "DigiLab", "address": "Building A", "room": "Room 1.01"},
        )

        camera_type, _ = ProductType.objects.get_or_create(
            name="Camera",
            defaults={
                "attribute_schema": [
                    {"key": "resolution", "label": "Resolution", "type": "short_text",
                     "visible": True, "required": False, "default": ""},
                    {"key": "sensor", "label": "Sensor", "type": "short_text",
                     "visible": True, "required": False, "default": ""},
                    {"key": "internal_note", "label": "Internal note", "type": "long_text",
                     "visible": False, "required": False, "default": ""},
                ]
            },
        )

        products_data = [
            {
                "title": "Sony Alpha 7 IV",
                "lending_type": Product.LendingType.DAYS,
                "attributes": {"resolution": "33 MP", "sensor": "Full-frame",
                               "internal_note": "Handle with care"},
                "count": 3,
            },
            {
                "title": "GoPro Hero 12",
                "lending_type": Product.LendingType.HOURS,
                "attributes": {"resolution": "5.3K", "sensor": "1/1.9\""},
                "count": 5,
            },
            {
                "title": "Canon EOS R6",
                "lending_type": Product.LendingType.DAYS,
                "attributes": {"resolution": "20 MP", "sensor": "Full-frame"},
                "count": 2,
            },
        ]

        section, _ = Section.objects.get_or_create(
            title="Recording Technology",
            defaults={"description": "Cameras and audio/video gear."},
        )

        cameras = _category_in_section(section, "Cameras")

        for data in products_data:
            product, _ = Product.objects.get_or_create(
                title=data["title"],
                defaults={
                    "product_type": camera_type,
                    "lending_type": data["lending_type"],
                    "attributes": data["attributes"],
                    "description": f"<p>{data['title']} available from the {pool.name}.</p>",
                },
            )
            product.categories.add(cameras)

            for index in range(1, data["count"] + 1):
                inventory_number = f"{pool.pool_id}-{product.id:02d}{index:02d}"
                Resource.objects.get_or_create(
                    inventory_number=inventory_number,
                    defaults={
                        "product": product,
                        "resource_pool": pool,
                        "qr_code_id": f"QR-{inventory_number}",
                    },
                )

        self._seed_podcast(section)
        self._seed_booking()
        self.stdout.write(self.style.SUCCESS("Demo data ready."))

    def _seed_podcast(self, section):
        """An hourly-booked podcast room in its own pool with opening hours."""
        weekday_hours = [["09:00", "18:00"]]
        studio, _ = ResourcePool.objects.get_or_create(
            pool_id="Podcast",
            defaults={
                "name": "Podcast Studio",
                "address": "Building C",
                "room": "Room 0.05",
                "opening_hours": {
                    "mon": weekday_hours, "tue": weekday_hours, "wed": weekday_hours,
                    "thu": weekday_hours, "fri": weekday_hours,
                },
                "lead_time_hours": 0,
            },
        )
        room_type, _ = ProductType.objects.get_or_create(
            name="Room",
            defaults={
                "attribute_schema": [
                    {"key": "capacity", "label": "Capacity (people)", "type": "number",
                     "visible": True, "required": False, "default": ""},
                    {"key": "equipment", "label": "Equipment", "type": "long_text",
                     "visible": True, "required": False, "default": ""},
                ]
            },
        )
        product, _ = Product.objects.get_or_create(
            title="Podcast Room",
            defaults={
                "product_type": room_type,
                "lending_type": Product.LendingType.HOURS,
                "min_duration": 1,
                "max_duration": 4,
                "attributes": {"capacity": "4", "equipment": "2 mics, mixer, acoustic panels"},
                "description": "<p>Bookable by the hour at the Podcast Studio.</p>",
            },
        )
        product.categories.add(_category_in_section(section, "Rooms"))
        for index in range(1, 3):
            inventory_number = f"{studio.pool_id}-{index:03d}"
            Resource.objects.get_or_create(
                inventory_number=inventory_number,
                defaults={
                    "product": product,
                    "resource_pool": studio,
                    "qr_code_id": f"QR-{inventory_number}",
                },
            )

    def _seed_booking(self):
        """Create one demo reservation so availability is below the total."""
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from lending.models import Booking
        from lending.services import create_reservation

        if Booking.objects.exists():
            return

        borrower, _ = get_user_model().objects.get_or_create(
            username="demo.borrower", defaults={"email": "demo@example.org"}
        )
        product = Product.objects.filter(title="GoPro Hero 12").first()
        resource = product.resources.first() if product else None
        if resource:
            start = timezone.now() + timedelta(days=1)
            create_reservation(borrower, [(resource, start, start + timedelta(days=1))])
