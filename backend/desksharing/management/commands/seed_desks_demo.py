# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Idempotent demo data for local development and browser checks.

Creates the enabled department "Desksharing Demo" (pool, access group with the
local demo user ``demo`` — added whenever that user exists, department admin),
2 floors, 4 rooms (one meeting room), 10 desks with features (2 special), one
fixed desk, a simple plan for floor 1 and a few reservations today and
tomorrow by a second demo user (``demo2``).

Usage: python manage.py seed_desks_demo
Never run automatically (not part of any migration).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts import roles
from accounts.models import AccessGroup
from catalog.models import ResourcePool
from desksharing import hours
from desksharing.models import DeskSettings, Feature, Floor, Place, Reservation, Room

POOL_NAME = "Desksharing Demo"


class Command(BaseCommand):
    help = "Create (or complete) the Desksharing demo department."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        pool, _ = ResourcePool.objects.get_or_create(
            pool_id="desksharing-demo", defaults={"name": POOL_NAME}
        )
        group, _ = AccessGroup.objects.get_or_create(name="Desksharing Demo")
        group.pools.add(pool)
        demo = User.objects.filter(username="demo").first()
        if demo:
            group.members.add(demo)
        other, created = User.objects.get_or_create(
            username="demo2",
            defaults={"first_name": "Dana", "last_name": "Demo", "email": "demo2@example.org"},
        )
        if created:
            other.set_unusable_password()
            other.save()
        group.members.add(other)
        settings_ = DeskSettings.for_pool(pool)
        settings_.enabled = True
        settings_.save()
        lenders = roles.ensure_pool_lender_group(pool)
        if demo:
            lenders.members.add(demo)

        docking, _ = Feature.objects.get_or_create(pool=pool, name="Docking station")
        monitor, _ = Feature.objects.get_or_create(pool=pool, name="Second monitor")
        height, _ = Feature.objects.get_or_create(pool=pool, name="Height-adjustable")

        floor1, _ = Floor.objects.get_or_create(
            pool=pool, building="Haus A", name="Floor 1", defaults={"position": 1}
        )
        floor2, _ = Floor.objects.get_or_create(
            pool=pool, building="Haus A", name="Floor 2", defaults={"position": 2}
        )
        rooms = {}
        for floor, name, kind in [
            (floor1, "Room 101", Room.Kind.OFFICE),
            (floor1, "Room 102", Room.Kind.OFFICE),
            (floor2, "Room 201", Room.Kind.OFFICE),
            (floor2, "Conference room", Room.Kind.MEETING),
        ]:
            rooms[name], _ = Room.objects.get_or_create(
                floor=floor, name=name, defaults={"kind": kind}
            )

        desks = [
            ("Desk 101-1", "Room 101", [docking], False),
            ("Desk 101-2", "Room 101", [docking, monitor], False),
            ("Desk 101-3", "Room 101", [], False),
            ("Desk 101-4", "Room 101", [height], True),
            ("Desk 102-1", "Room 102", [monitor], False),
            ("Desk 102-2", "Room 102", [], False),
            ("Desk 102-3", "Room 102", [docking], False),
            ("Desk 201-1", "Room 201", [], False),
            ("Desk 201-2", "Room 201", [height, monitor], True),
            ("Desk 201-3", "Room 201", [], False),
        ]
        places = {}
        for i, (name, room, features, special) in enumerate(desks):
            place, _ = Place.objects.get_or_create(
                room=rooms[room], name=name,
                defaults={"kind": Place.Kind.DESK, "is_special": special},
            )
            place.features.set(features)
            if place.room.floor_id == floor1.pk and place.plan_symbol is None:
                place.plan_symbol = {"x": 40 + (i % 4) * 60, "y": 40 + (i // 4) * 70, "rotation": 0}
                place.save(update_fields=["plan_symbol"])
            places[name] = place
        fixed = places["Desk 102-3"]
        if fixed.fixed_owner_id is None:
            fixed.fixed_owner = other
            fixed.save()
        meeting, _ = Place.objects.get_or_create(
            room=rooms["Conference room"], name="Conference room",
            defaults={"kind": Place.Kind.MEETING_ROOM, "capacity": 8},
        )

        if not floor1.plan or not floor1.plan.get("shapes"):
            floor1.plan = {
                "shapes": [
                    {"id": "r101", "type": "room", "points": [[10, 10], [260, 10], [260, 150], [10, 150]],
                     "text": "Room 101", "room_id": rooms["Room 101"].pk},
                    {"id": "r102", "type": "room", "points": [[270, 10], [420, 10], [420, 150], [270, 150]],
                     "text": "Room 102", "room_id": rooms["Room 102"].pk},
                    {"id": "d1", "type": "door", "points": [[260, 60], [260, 90]]},
                ]
            }
            floor1.save(update_fields=["plan"])

        today = timezone.localtime(timezone.now(), hours.TZ).date()
        for day, name, start, end in [
            (today, "Desk 101-1", 8, 12),
            (today, "Desk 101-2", 9, 17),
            (today + timedelta(days=1), "Desk 101-1", 8, 16),
        ]:
            place = places[name]
            period = hours.local_range(day, start, end)
            exists = Reservation.objects.filter(
                place=place, status=Reservation.Status.ACTIVE, period__overlap=period
            ).exists()
            if not exists:
                Reservation.objects.create(
                    place=place, holder=other, booked_by=other, period=period
                )
        self.stdout.write(self.style.SUCCESS(
            f"Desksharing demo ready (pool id {pool.pk}); user demo: "
            + ("member and department admin" if demo else "not found yet - re-run after first login")
        ))
