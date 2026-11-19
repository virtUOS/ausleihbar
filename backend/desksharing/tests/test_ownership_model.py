# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Departments on rooms and places, campus-wide floors and equipment."""
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from desksharing.models import Building, DeskAdminSetting, Feature, Floor, Place, Reservation, Room
from desksharing import booking
from desksharing.tests.test_booking import setup_department
from desksharing.tests.test_hours import next_weekday


class OwnershipModelTests(TestCase):
    def setUp(self):
        setup_department(self)

    def test_room_and_place_pool_fields(self):
        self.assertEqual(self.room.pool_id, self.pool.pk)
        self.assertEqual(self.d1.pool_id, self.pool.pk)
        self.assertFalse(self.d1.pool_overridden)
        # Floors belong to no department any more.
        self.assertFalse(hasattr(self.floor, "pool_id"))
        unassigned = Room.objects.create(floor=self.floor, name="Free")
        self.assertIsNone(unassigned.pool_id)
        self.assertIsNone(Place.objects.create(room=unassigned, name="Free A").pool_id)

    def test_reservation_pool_set_on_create(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=next_weekday(1),
            start_hour=9, end_hour=12,
        )
        self.assertEqual(res.pool_id, self.d1.pool_id)

    def test_unique_names(self):
        building = self.floor.building
        with self.assertRaises(IntegrityError), transaction.atomic():
            Floor.objects.create(building=building, name="eg")
        other = Building.objects.create(code="B2")
        Floor.objects.create(building=other, name="EG")  # another building is fine
        with self.assertRaises(IntegrityError), transaction.atomic():
            Room.objects.create(floor=self.floor, name="r1")
        Feature.objects.create(name="Dock")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Feature.objects.create(name="DOCK")

    def test_admin_setting_default_letter(self):
        setting = DeskAdminSetting.load()
        self.assertEqual(setting.place_name_pattern, "letter")
        self.assertEqual(DeskAdminSetting.load().pk, setting.pk)


class SeedDemoTests(TestCase):
    def test_seed_creates_campus_floors_and_department_rooms(self):
        for _ in range(2):  # idempotent
            call_command("seed_desks_demo", stdout=StringIO())
        rooms = Room.objects.all()
        self.assertEqual(rooms.count(), 4)
        pool_id = rooms.first().pool_id
        self.assertIsNotNone(pool_id)
        self.assertFalse(rooms.exclude(pool_id=pool_id).exists())
        self.assertEqual(Place.objects.filter(pool_id=pool_id).count(), 11)
        self.assertEqual(Floor.objects.count(), 2)
        self.assertEqual(Feature.objects.count(), 3)
        self.assertFalse(Reservation.objects.exclude(pool_id=pool_id).exists())
        self.assertTrue(Reservation.objects.exists())
