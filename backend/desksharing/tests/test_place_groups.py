# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Rooms carry default access groups for their places (followers vs
overridden places)."""
import importlib
from unittest import mock

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.models import AccessGroup
from desksharing import place_groups, signals
from desksharing.models import Place, Room
from desksharing.tests.test_admin_rights import BASE, AdminRightsBase


def gids(obj):
    return {g.pk for g in obj.access_groups.all()}


class PlaceGroupsTests(AdminRightsBase):
    def setUp(self):
        super().setUp()
        self.g1 = AccessGroup.objects.create(name="G1")
        self.g2 = AccessGroup.objects.create(name="G2")
        self.g3 = AccessGroup.objects.create(name="G3")
        self.place_a2 = Place.objects.create(room=self.room_a, name="15/101 B")

    def test_new_place_takes_room_groups(self):
        self.room_a.access_groups.set([self.g1])
        self.as_(self.admin_a)
        resp = self.client.post(
            f"{BASE}/places/", {"room": self.room_a.pk, "name": "15/101 C"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["groups_overridden"], False)
        self.assertEqual(resp.json()["access_groups"], [self.g1.pk])
        # posting its own set on create overrides
        resp = self.client.post(
            f"{BASE}/places/",
            {"room": self.room_a.pk, "name": "15/101 D", "access_groups": [self.g2.pk]},
            format="json",
        )
        self.assertEqual(resp.json()["groups_overridden"], True)
        self.assertEqual(resp.json()["access_groups"], [self.g2.pk])

    def test_room_groups_hand_down_to_followers_only(self):
        self.place_a2.access_groups.set([self.g3])
        Place.objects.filter(pk=self.place_a2.pk).update(groups_overridden=True)
        self.as_(self.admin_a)
        resp = self.client.patch(
            f"{BASE}/rooms/{self.room_a.pk}/", {"access_groups": [self.g1.pk]}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["access_groups"], [self.g1.pk])
        self.assertEqual(gids(self.place_a), {self.g1.pk})
        self.assertEqual(gids(self.place_a2), {self.g3.pk})

    def test_bulk_places_add_remove_marks_overridden(self):
        self.room_a.access_groups.set([self.g1])
        place_groups.hand_down(self.room_a)
        n = place_groups.apply(
            actor=self.admin_a, places=[self.place_a], add_ids=[self.g2.pk], remove_ids=[self.g1.pk]
        )
        self.place_a.refresh_from_db()
        self.assertEqual(n, 1)
        self.assertTrue(self.place_a.groups_overridden)
        self.assertEqual(gids(self.place_a), {self.g2.pk})
        self.assertEqual(gids(self.place_a2), {self.g1.pk})

    def test_mixed_selection_explicit_place_overrides(self):
        place_groups.apply(
            actor=self.admin_a, rooms=[self.room_a], places=[self.place_a], add_ids=[self.g1.pk]
        )
        self.place_a.refresh_from_db(); self.place_a2.refresh_from_db()
        self.assertTrue(self.place_a.groups_overridden)
        self.assertFalse(self.place_a2.groups_overridden)
        self.assertEqual(gids(self.room_a), {self.g1.pk})
        self.assertEqual(gids(self.place_a2), {self.g1.pk})

    def test_follow_room_resets(self):
        self.room_a.access_groups.set([self.g1])
        place_groups.apply(actor=self.admin_a, places=[self.place_a], add_ids=[self.g2.pk])
        n = place_groups.apply(actor=self.admin_a, places=[self.place_a], follow_room=True)
        self.place_a.refresh_from_db()
        self.assertEqual(n, 1)
        self.assertFalse(self.place_a.groups_overridden)
        self.assertEqual(gids(self.place_a), {self.g1.pk})
        # already following: nothing changes
        self.assertEqual(
            place_groups.apply(actor=self.admin_a, places=[self.place_a], follow_room=True), 0
        )

    def test_moved_follower_takes_new_room_groups(self):
        room2 = Room.objects.create(floor=self.floor, pool=self.pool_a, name="15/110")
        room2.access_groups.set([self.g2])
        self.as_(self.admin_a)
        resp = self.client.patch(f"{BASE}/places/{self.place_a.pk}/", {"room": room2.pk}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(gids(self.place_a), {self.g2.pk})

    def test_overridden_keeps_on_move(self):
        room2 = Room.objects.create(floor=self.floor, pool=self.pool_a, name="15/110")
        room2.access_groups.set([self.g2])
        place_groups.apply(actor=self.admin_a, places=[self.place_a], add_ids=[self.g1.pk])
        self.as_(self.admin_a)
        resp = self.client.patch(f"{BASE}/places/{self.place_a.pk}/", {"room": room2.pk}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(gids(self.place_a), {self.g1.pk})

    def test_place_serializer_flag_rules(self):
        self.room_a.access_groups.set([self.g1])
        place_groups.hand_down(self.room_a)
        self.as_(self.admin_a)
        url = f"{BASE}/places/{self.place_a.pk}/"
        # posting the room's own set keeps following; a different set overrides
        r = self.client.patch(url, {"access_groups": [self.g1.pk]}, format="json").json()
        self.assertFalse(r["groups_overridden"])
        r = self.client.patch(url, {"access_groups": [self.g2.pk]}, format="json").json()
        self.assertTrue(r["groups_overridden"])
        self.assertEqual(r["access_groups"], [self.g2.pk])
        # groups_overridden=false resets and ignores posted groups
        r = self.client.patch(
            url, {"groups_overridden": False, "access_groups": [self.g3.pk]}, format="json"
        ).json()
        self.assertFalse(r["groups_overridden"])
        self.assertEqual(r["access_groups"], [self.g1.pk])

    def test_department_admin_foreign_selection_403_nothing_changed(self):
        self.as_(self.admin_a)
        resp = self.client.post(
            f"{BASE}/place-groups/",
            {"place_ids": [self.place_a.pk, self.place_b.pk], "add_ids": [self.g1.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(gids(self.place_a), set())
        self.place_a.refresh_from_db()
        self.assertFalse(self.place_a.groups_overridden)
        resp = self.client.post(
            f"{BASE}/place-groups/",
            {"room_ids": [self.room_a.pk, self.room_b.pk], "add_ids": [self.g1.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(gids(self.room_a), set())
        with self.assertRaises(PermissionDenied):
            place_groups.apply(actor=self.admin_a, rooms=[self.room_b], add_ids=[self.g1.pk])

    def test_system_group_rejected(self):
        system = self.pool_a.lender_group
        with self.assertRaises(ValidationError):
            place_groups.apply(actor=self.root, rooms=[self.room_a], add_ids=[system.pk])
        self.as_(self.root)
        for url in (f"{BASE}/rooms/{self.room_a.pk}/", f"{BASE}/places/{self.place_a.pk}/"):
            resp = self.client.patch(url, {"access_groups": [system.pk]}, format="json")
            self.assertEqual(resp.status_code, 400, resp.content)
        resp = self.client.post(
            f"{BASE}/place-groups/",
            {"room_ids": [self.room_a.pk], "add_ids": [system.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(gids(self.room_a), set())

    def test_migration_marks_grouped_places_overridden(self):
        migration = importlib.import_module("desksharing.migrations.0024_room_access_groups")
        self.place_a.access_groups.set([self.g1])
        migration.mark_grouped_places_overridden(apps, None)
        self.place_a.refresh_from_db(); self.place_a2.refresh_from_db()
        self.assertTrue(self.place_a.groups_overridden)
        self.assertFalse(self.place_a2.groups_overridden)

    def test_endpoint_roundtrip(self):
        self.as_(self.admin_a)
        url = f"{BASE}/place-groups/"
        resp = self.client.post(
            url, {"room_ids": [self.room_a.pk], "add_ids": [self.g1.pk, self.g2.pk]}, format="json"
        )
        self.assertEqual((resp.status_code, resp.json()), (200, {"places_changed": 2}))
        self.assertEqual(gids(self.place_a), {self.g1.pk, self.g2.pk})
        resp = self.client.post(
            url, {"place_ids": [self.place_a.pk], "remove_ids": [self.g2.pk]}, format="json"
        )
        self.assertEqual(resp.json(), {"places_changed": 1})
        self.assertEqual(gids(self.place_a), {self.g1.pk})
        resp = self.client.post(url, {"place_ids": [self.place_a.pk], "follow_room": True}, format="json")
        self.assertEqual(resp.json(), {"places_changed": 1})
        self.assertEqual(gids(self.place_a), {self.g1.pk, self.g2.pk})
        # errors
        self.assertEqual(self.client.post(url, {"add_ids": [self.g1.pk]}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(url, {"room_ids": [self.room_a.pk]}, format="json").status_code, 400
        )
        self.assertEqual(
            self.client.post(url, {"room_ids": [999999], "add_ids": [self.g1.pk]}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.post(url, {"room_ids": [self.room_a.pk], "add_ids": [999999]}, format="json").status_code,
            400,
        )

    def test_removing_group_revokes_lost_rights_once(self):
        self.room_a.access_groups.set([self.g1, self.g2])
        place_groups.hand_down(self.room_a)
        signals._local.coll = None  # setUp's uncommitted requests are stale
        with mock.patch("desksharing.absences.revoke_lost_rights") as revoke:
            with self.captureOnCommitCallbacks(execute=True):
                place_groups.apply(
                    actor=self.admin_a, rooms=[self.room_a], remove_ids=[self.g1.pk, self.g2.pk]
                )
        calls = [c.kwargs.get("place") for c in revoke.call_args_list]
        self.assertEqual(sorted(calls), sorted([self.place_a.pk, self.place_a2.pk]))
