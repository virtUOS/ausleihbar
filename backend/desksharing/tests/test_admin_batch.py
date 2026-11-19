# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from accounts.models import AccessGroup
from catalog.models import ResourcePool
from desksharing import naming
from desksharing.models import DeskAdminSetting, DeskSettings, Floor, Place, Room
from desksharing.tests.test_admin_rights import AdminRightsBase


class NamingTests(AdminRightsBase):
    def test_room_range_padding_and_limits(self):
        self.assertEqual(naming.room_range("15/", "01", "03"), ["15/01", "15/02", "15/03"])
        self.assertEqual(naming.room_range("R", "8", "10"), ["R8", "R9", "R10"])
        self.assertEqual(len(naming.room_range("R", "1", "200")), 200)
        with self.assertRaises(ValueError):
            naming.room_range("R", "1", "201")
        with self.assertRaises(ValueError):
            naming.room_range("R", "5", "4")
        with self.assertRaises(ValueError):
            naming.room_range("R", "a", "c")

    def test_place_suggestions_letter_and_number(self):
        # room_a holds "15/101 A"; letters continue after it
        self.assertEqual(
            naming.next_place_names(self.room_a, 2, "letter"), ["15/101 B", "15/101 C"]
        )
        Place.objects.create(room=self.room_a, name="15/101 3")
        self.assertEqual(naming.next_place_names(self.room_a, 2, "number"), ["15/101 4", "15/101 5"])
        self.assertEqual(naming.next_place_names(self.room_b, 1, "number"), ["15/102 1"])
        letters = naming.next_place_names(self.room_b, 30, "letter")
        self.assertEqual(letters[:2], ["15/102 B", "15/102 C"])
        self.assertEqual(letters[24:26], ["15/102 Z", "15/102 AA"])

    def test_suggestions_endpoint(self):
        self.as_(self.admin_a)
        url = f"/api/desks/manage/places/name-suggestions/?room={self.room_a.pk}&count=2"
        self.assertEqual(self.client.get(url).json(), {"names": ["15/101 B", "15/101 C"]})
        foreign = f"/api/desks/manage/places/name-suggestions/?room={self.room_b.pk}&count=1"
        self.assertEqual(self.client.get(foreign).status_code, 403)


class BatchTests(AdminRightsBase):
    def test_batch_rooms_skips_existing(self):
        self.as_(self.root)
        resp = self.client.post(
            "/api/desks/manage/rooms/batch/",
            {"floor": self.floor.pk, "prefix": "15/10", "start": "1", "end": "3",
             "pool": self.pool_a.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"created": ["15/103"], "skipped": ["15/101", "15/102"]})
        self.assertEqual(Room.objects.get(name="15/103").pool, self.pool_a)

    def test_batch_rooms_dry_run_creates_nothing(self):
        self.as_(self.root)
        before = Room.objects.count()
        resp = self.client.post(
            "/api/desks/manage/rooms/batch/",
            {"floor": self.floor.pk, "prefix": "X", "start": "1", "end": "3", "dry_run": True},
            format="json",
        )
        self.assertEqual(resp.json(), {"created": ["X1", "X2", "X3"], "skipped": []})
        self.assertEqual(Room.objects.count(), before)

    def test_batch_rooms_validation_and_rights(self):
        self.as_(self.admin_a)
        body = {"floor": self.floor.pk, "prefix": "X", "start": "1", "end": "2"}
        self.assertEqual(self.client.post("/api/desks/manage/rooms/batch/", body, format="json").status_code, 403)
        self.as_(self.root)
        bad = self.client.post(
            "/api/desks/manage/rooms/batch/", {**body, "floor": 99999}, format="json"
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("floor", bad.json())

    def test_place_names_unique_per_building(self):
        other_floor = Floor.objects.create(building=self.building, name="1.OG")
        room_c = Room.objects.create(floor=other_floor, pool=self.pool_a, name="15/101 ")
        Place.objects.create(room=room_c, name="15/101 B")  # taken elsewhere in the building
        self.as_(self.admin_a)
        resp = self.client.post(
            "/api/desks/manage/places/batch/",
            {"room_ids": [self.room_a.pk], "count": 2, "kind": "desk"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["created"], ["15/101 C", "15/101 D"])
        self.assertEqual(Place.objects.get(name="15/101 C").pool, self.pool_a)

    def test_place_batch_order_dry_run_and_rights(self):
        self.as_(self.root)
        body = {"room_ids": [self.room_b.pk, self.room_a.pk], "count": 1, "kind": "desk"}
        dry = self.client.post(
            "/api/desks/manage/places/batch/", {**body, "dry_run": True}, format="json"
        )
        self.assertEqual(dry.json()["created"], ["15/102 B", "15/101 B"])
        self.assertEqual(Place.objects.count(), 2)
        self.as_(self.admin_a)
        self.assertEqual(
            self.client.post("/api/desks/manage/places/batch/", body, format="json").status_code, 403
        )
        self.assertEqual(Place.objects.count(), 2)


class AssignEndpointTests(AdminRightsBase):
    def setUp(self):
        super().setUp()
        self.free = Room.objects.create(floor=self.floor, name="Free")
        self.fp = Place.objects.create(room=self.free, name="Free A")
        self.pool_c = ResourcePool.objects.create(name="PoolC")
        self.group = AccessGroup.objects.create(name="Dept C")

    def post(self, body):
        return self.client.post("/api/desks/manage/assign/", body, format="json")

    def test_assign_endpoint_all_or_nothing(self):
        self.as_(self.root)
        # unknown admin group id: nothing happens (no group added, no enable, no assign)
        bad = self.post({"room_ids": [self.free.pk], "pool": self.pool_c.pk,
                         "access_group_ids": [self.group.pk], "admin_group_ids": [999999]})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("admin_group_ids", bad.json())
        self.assertFalse(self.group.pools.exists())
        self.free.refresh_from_db()
        self.assertIsNone(self.free.pool)
        # no access group on the pool: enabling fails, assignment rolled back
        fail = self.post({"room_ids": [self.free.pk], "pool": self.pool_c.pk})
        self.assertEqual(fail.status_code, 400)
        self.free.refresh_from_db()
        self.assertIsNone(self.free.pool)
        # success: groups, enabled, assigned
        ok = self.post({"room_ids": [self.free.pk], "pool": self.pool_c.pk,
                        "access_group_ids": [self.group.pk]})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json(), {"places_changed": 1})
        self.free.refresh_from_db()
        self.assertEqual(self.free.pool, self.pool_c)
        self.assertTrue(DeskSettings.for_pool(self.pool_c).enabled)
        self.assertTrue(self.group.pools.filter(pk=self.pool_c.pk).exists())

    def test_assign_places_and_unknown_ids(self):
        self.as_(self.root)
        resp = self.post({"place_ids": [self.fp.pk], "pool": self.pool_a.pk})
        self.assertEqual(resp.json(), {"places_changed": 1})
        self.fp.refresh_from_db()
        self.assertTrue(self.fp.pool_overridden)
        self.assertEqual(self.post({"place_ids": [999999], "pool": None}).status_code, 400)

    def test_assign_endpoint_department_admin_forbidden(self):
        self.as_(self.admin_a)
        resp = self.post({"room_ids": [self.free.pk], "pool": self.pool_a.pk})
        self.assertEqual(resp.status_code, 403)
        self.free.refresh_from_db()
        self.assertIsNone(self.free.pool)


class AdminSettingAndFloorTests(AdminRightsBase):
    def test_admin_setting_get_put(self):
        self.as_(self.admin_a)
        url = "/api/desks/manage/admin-setting/"
        self.assertEqual(self.client.get(url).json(), {"place_name_pattern": "letter"})
        self.assertEqual(self.client.put(url, {"place_name_pattern": "number"}, format="json").status_code, 403)
        self.as_(self.root)
        self.assertEqual(self.client.put(url, {"place_name_pattern": "number"}, format="json").status_code, 200)
        self.assertEqual(DeskAdminSetting.load().place_name_pattern, "number")
        self.assertEqual(self.client.put(url, {"place_name_pattern": "x"}, format="json").status_code, 400)
        self.as_(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_floor_visible_through_assigned_empty_room(self):
        other = Floor.objects.create(building=self.building, name="2.OG")
        Room.objects.create(floor=other, pool=self.pool_a, name="15/201")
        Floor.objects.create(building=self.building, name="3.OG")  # nothing of A's
        self.as_(self.admin_a)
        ids = self.ids("/api/desks/manage/floors/")
        self.assertIn(other.pk, ids)
        self.assertEqual(self.client.get(f"/api/desks/manage/floors/{other.pk}/").status_code, 200)
        self.assertEqual(len(ids), 2)
