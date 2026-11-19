# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from unittest import mock

from django.contrib.auth import get_user_model

from desksharing.models import Building, Floor, Place, Room
from desksharing.tests.test_places import PlaceTestBase

User = get_user_model()
URL = "/api/desks/manage/buildings/"


class BuildingApiTests(PlaceTestBase):
    """The campus-wide list: department admins read and add, app admins
    change and delete; codes are unique regardless of case."""

    def test_department_admin_lists_and_adds_but_cannot_change(self):
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        rows = res.json()["results"] if isinstance(res.json(), dict) else res.json()
        self.assertEqual([r["code"] for r in rows], ["B1"])
        self.assertFalse(rows[0]["editable"])

        res = self.client.post(URL, {"code": " 15 ", "description": "EW-Gebäude",
                                     "address": "Seminarstraße 20"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["code"], "15")

        pk = res.json()["id"]
        self.assertEqual(
            self.client.patch(f"{URL}{pk}/", {"description": "x"}, format="json").status_code, 403
        )
        self.assertEqual(self.client.delete(f"{URL}{pk}/").status_code, 403)

    def test_app_admin_without_any_department_may_manage(self):
        root = User.objects.create_superuser("root", password="x")
        self.client.force_authenticate(root)
        # No department managed or enabled yet.
        with mock.patch("desksharing.rights.admin_pool_ids", return_value=set()):
            res = self.client.post(URL, {"code": "AX"}, format="json")
            self.assertEqual(res.status_code, 201)
            self.assertEqual(
                self.client.patch(f"{URL}{res.json()['id']}/", {"address": "Weg 1"},
                                  format="json").status_code,
                200,
            )

    def test_member_without_admin_rights_is_forbidden(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_code_is_unique_ignoring_case(self):
        Building.objects.create(code="AX")
        res = self.client.post(URL, {"code": "ax"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("code", res.json())

    def test_app_admin_edits_and_deletes_only_unused(self):
        root = User.objects.create_superuser("root", password="x")
        self.client.force_authenticate(root)
        used = self.floor.building
        res = self.client.patch(f"{URL}{used.pk}/", {"description": "EW"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["editable"])
        self.assertEqual(self.client.delete(f"{URL}{used.pk}/").status_code, 409)
        spare = Building.objects.create(code="99")
        self.assertEqual(self.client.delete(f"{URL}{spare.pk}/").status_code, 204)

    def test_last_floor_is_offered_as_default(self):
        # The rule itself is tested with the overview (test_overview).
        self.client.force_authenticate(self.member)
        with mock.patch("desksharing.overview.last_floor_id", return_value=self.floor.pk) as last:
            res = self.client.get(f"/api/desks/floors/?pool={self.pool.pk}")
        self.assertEqual(res.json()["last_floor_id"], self.floor.pk)
        last.assert_called_once_with(self.pool, self.member)

    def test_floor_takes_building_and_reports_code(self):
        b = Building.objects.create(code="32", description="Bohnenkamp-Haus")
        res = self.client.patch(
            f"/api/desks/manage/floors/{self.floor.pk}/", {"building": b.pk}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["building_code"], "32")
        self.assertEqual(res.json()["building_description"], "Bohnenkamp-Haus")
        res = self.client.patch(
            f"/api/desks/manage/floors/{self.floor.pk}/", {"building": None}, format="json"
        )
        self.assertEqual(res.json()["building_code"], "")


class PoolFloorsTests(PlaceTestBase):
    def test_members_get_active_floors_with_building(self):
        self.desk()
        old = Floor.objects.create(name="Alt", is_active=False)
        Place.objects.create(room=Room.objects.create(floor=old, pool=self.pool, name="R"), name="X")
        self.client.force_authenticate(self.member)
        res = self.client.get(f"/api/desks/floors/?pool={self.pool.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {
            "floors": [{
                "id": self.floor.pk, "name": "EG", "position": 0,
                "building_id": self.floor.building_id, "building": "B1",
                "building_description": "",
            }],
            "last_floor_id": None,
        })

    def test_outsider_gets_404(self):
        outsider = User.objects.create_user("out", password="x")
        self.client.force_authenticate(outsider)
        res = self.client.get(f"/api/desks/floors/?pool={self.pool.pk}")
        self.assertEqual(res.status_code, 404)
