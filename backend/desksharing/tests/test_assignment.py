# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import AccessGroup
from catalog.models import ResourcePool
from desksharing import assignment
from desksharing.models import DeskSettings, Place, Room
from desksharing.tests.test_booking import setup_department

User = get_user_model()


class AssignmentTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.pool2 = ResourcePool.objects.create(name="PoolB")
        self.free_room = Room.objects.create(floor=self.floor, name="Free")
        self.p1 = Place.objects.create(room=self.free_room, name="P1")
        self.p2 = Place.objects.create(room=self.free_room, name="P2")

    def test_assign_room_hands_down_except_overridden(self):
        assignment.assign_places([self.p2], self.pool, actor=self.admin)
        changed = assignment.assign_rooms([self.free_room], self.pool2, actor=self.admin)
        self.free_room.refresh_from_db(); self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertEqual(self.free_room.pool, self.pool2)
        self.assertEqual(self.p1.pool, self.pool2)
        self.assertEqual(self.p2.pool, self.pool)

    def test_unassign_room_keeps_overridden(self):
        assignment.assign_rooms([self.free_room], self.pool2, actor=self.admin)
        assignment.assign_places([self.p2], self.pool, actor=self.admin)
        assignment.assign_rooms([self.free_room], None, actor=self.admin)
        self.free_room.refresh_from_db(); self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertIsNone(self.free_room.pool)
        self.assertIsNone(self.p1.pool)
        self.assertEqual(self.p2.pool, self.pool)

    def test_assign_place_override_and_follow_room(self):
        assignment.assign_rooms([self.free_room], self.pool2, actor=self.admin)
        self.assertEqual(assignment.assign_places([self.p1], self.pool, actor=self.admin), 1)
        self.p1.refresh_from_db()
        self.assertEqual((self.p1.pool, self.p1.pool_overridden), (self.pool, True))
        assignment.assign_places([self.p1], None, actor=self.admin, follow_room=True)
        self.p1.refresh_from_db()
        self.assertEqual((self.p1.pool, self.p1.pool_overridden), (self.pool2, False))

    def test_new_place_inherits_room_pool(self):
        assignment.assign_rooms([self.free_room], self.pool2, actor=self.admin)
        room = Room.objects.get(pk=self.free_room.pk)  # assign_rooms updates in bulk
        self.assertEqual(Place.objects.create(room=room, name="New").pool, self.pool2)

    def test_groups_add_only(self):
        other = AccessGroup.objects.create(name="Other")
        admins = AccessGroup.objects.create(name="Admins")
        assignment.add_department_groups(
            self.pool2, access_group_ids=[other.pk], admin_group_ids=[admins.pk], actor=self.admin
        )
        self.assertIn(self.pool2, other.pools.all())
        self.assertIn(self.pool2, admins.lender_pools.all())
        assignment.add_department_groups(
            self.pool, access_group_ids=[other.pk], admin_group_ids=[], actor=self.admin
        )
        self.assertEqual(set(other.pools.all()), {self.pool, self.pool2})
        self.assertIn(self.pool, self.group.pools.all())

    def test_system_group_refused_as_admin_group(self):
        with self.assertRaises(ValidationError):
            assignment.add_department_groups(
                self.pool2, access_group_ids=[],
                admin_group_ids=[self.pool.lender_group.pk], actor=self.admin,
            )

    def test_enable_requires_access_group(self):
        with self.assertRaises(ValidationError) as ctx:
            assignment.ensure_desksharing_enabled(self.pool2)
        self.assertIn("pool", ctx.exception.message_dict)
        self.assertFalse(DeskSettings.for_pool(self.pool2).enabled)

    def test_enable_with_group_added_same_call(self):
        group = AccessGroup.objects.create(name="Other")
        assignment.add_department_groups(
            self.pool2, access_group_ids=[group.pk], admin_group_ids=[], actor=self.admin
        )
        assignment.ensure_desksharing_enabled(self.pool2)
        self.assertTrue(DeskSettings.for_pool(self.pool2).enabled)

    def test_department_admin_refused(self):
        with self.assertRaises(PermissionDenied):
            assignment.assign_rooms([self.free_room], self.pool, actor=self.lender)
        with self.assertRaises(PermissionDenied):
            assignment.assign_places([self.p1], self.pool, actor=self.lender)
        with self.assertRaises(PermissionDenied):
            assignment.add_department_groups(
                self.pool, access_group_ids=[], admin_group_ids=[], actor=self.lender
            )
