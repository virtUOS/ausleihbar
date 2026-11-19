# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Admin CRUD rights: campus-wide floors and equipment (app admins change,
department admins read/add), rooms and places by department."""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import translation
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import rights
from desksharing.models import Building, Feature, FeatureImage, Floor, Place, Room
from desksharing.tests.test_rights import make_pool

User = get_user_model()
BASE = "/api/desks/manage"


def png(name="p.png"):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class AdminRightsBase(TestCase):
    """One shared floor holding rooms/places of departments A and B."""

    def setUp(self):
        self.pool_a = make_pool("PoolA", AccessGroup.objects.create(name="Dept A"))
        self.pool_b = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        self.admin_a = User.objects.create_user("admin_a", password="x")
        self.pool_a.lender_group.members.add(self.admin_a)
        self.admin_b = User.objects.create_user("admin_b", password="x")
        self.pool_b.lender_group.members.add(self.admin_b)
        self.member = User.objects.create_user("member", password="x")
        AccessGroup.objects.get(name="Dept A").members.add(self.member)
        self.root = User.objects.create_superuser("root", password="x")
        self.building = Building.objects.create(code="15")
        self.floor = Floor.objects.create(building=self.building, name="EG")
        self.room_a = Room.objects.create(floor=self.floor, pool=self.pool_a, name="15/101")
        self.room_b = Room.objects.create(floor=self.floor, pool=self.pool_b, name="15/102")
        self.place_a = Place.objects.create(room=self.room_a, name="15/101 A")
        self.place_b = Place.objects.create(room=self.room_b, name="15/102 A")
        self.client = APIClient()

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def ids(self, url):
        body = self.client.get(url).json()
        rows = body["results"] if isinstance(body, dict) else body
        return {row["id"] for row in rows}


class RightsHelperTests(AdminRightsBase):
    def test_can_admin_room_and_place(self):
        self.assertTrue(rights.can_admin_room(self.admin_a, self.room_a))
        self.assertFalse(rights.can_admin_room(self.admin_a, self.room_b))
        self.assertTrue(rights.can_admin_place(self.admin_a, self.place_a))
        self.assertFalse(rights.can_admin_place(self.admin_a, self.place_b))
        self.assertFalse(rights.can_admin_place(self.member, self.place_a))
        unassigned = Room.objects.create(floor=self.floor, name="15/103")
        self.assertFalse(rights.can_admin_room(self.admin_a, unassigned))
        self.assertTrue(rights.can_admin_room(self.root, unassigned))


class FloorRightsTests(AdminRightsBase):
    def test_list_scoped_to_floors_with_own_places_or_rooms(self):
        other = Floor.objects.create(building=self.building, name="1. OG")
        Room.objects.create(floor=other, pool=self.pool_a, name="15/201")  # assigned empty room: reachable
        only_b = Floor.objects.create(building=self.building, name="2. OG")
        Place.objects.create(
            room=Room.objects.create(floor=only_b, pool=self.pool_b, name="15/301"), name="15/301 A"
        )
        self.as_(self.admin_a)
        self.assertEqual(self.ids(f"{BASE}/floors/"), {self.floor.pk, other.pk})
        self.assertEqual(self.client.get(f"{BASE}/floors/{only_b.pk}/").status_code, 404)
        self.as_(self.root)
        self.assertEqual(self.ids(f"{BASE}/floors/"), {self.floor.pk, other.pk, only_b.pk})
        elsewhere = Floor.objects.create(building=Building.objects.create(code="32"), name="EG")
        self.assertEqual(self.ids(f"{BASE}/floors/?building={self.building.pk}"),
                         {self.floor.pk, other.pk, only_b.pk})
        self.assertEqual(self.ids(f"{BASE}/floors/?building=32x"), set())  # bad id: nothing
        self.assertIn(elsewhere.pk, self.ids(f"{BASE}/floors/"))

    def test_member_forbidden(self):
        self.as_(self.member)
        for url in (f"{BASE}/floors/", f"{BASE}/rooms/", f"{BASE}/places/", f"{BASE}/features/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        r = self.client.patch(f"{BASE}/floors/{self.floor.pk}/", {"name": "X"}, format="json")
        self.assertEqual(r.json()["detail"], "Only department admins may access this.")
        r = self.client.put(f"{BASE}/floors/{self.floor.pk}/plan/", {"symbols": {}}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_department_admin_cannot_create_or_change_floors(self):
        self.as_(self.admin_a)
        url = f"{BASE}/floors/{self.floor.pk}/"
        r = self.client.post(f"{BASE}/floors/", {"building": self.building.pk, "name": "3. OG"},
                             format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.patch(url, {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(url, {"scale_px_per_m": 3}, format="json").status_code, 403)
        self.floor.refresh_from_db()
        self.assertEqual(self.floor.name, "EG")
        self.assertIsNone(self.floor.scale_px_per_m)

    def test_admin_a_cannot_deactivate_or_delete_floor_holding_b_places(self):
        self.as_(self.admin_a)
        url = f"{BASE}/floors/{self.floor.pk}/"
        self.assertEqual(self.client.patch(url, {"is_active": False}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.floor.refresh_from_db()
        self.place_b.refresh_from_db()
        self.assertTrue(self.floor.is_active)
        self.assertTrue(self.place_b.is_active)

    def test_admin_a_cannot_save_plan_shapes_or_template(self):
        self.as_(self.admin_a)
        plan = {"plan": {"shapes": [{"id": "w", "type": "wall", "points": [[0, 0], [1, 1]]}]}}
        r = self.client.put(f"{BASE}/floors/{self.floor.pk}/plan/", plan, format="json")
        self.assertEqual(r.status_code, 403)
        self.floor.refresh_from_db()
        self.assertEqual(self.floor.plan, {"shapes": []})
        r = self.client.post(f"{BASE}/floors/{self.floor.pk}/template/", {"file": png()},
                             format="multipart")
        self.assertEqual(r.status_code, 403)

    def test_app_admin_creates_updates_deletes_floor(self):
        self.as_(self.root)
        r = self.client.post(f"{BASE}/floors/", {"building": self.building.pk, "name": "3. OG"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        new = r.json()["id"]
        self.assertEqual(
            self.client.patch(f"{BASE}/floors/{new}/", {"scale_px_per_m": 2.5}, format="json").status_code,
            200,
        )
        self.assertEqual(self.client.delete(f"{BASE}/floors/{new}/").status_code, 204)
        self.assertFalse(Floor.objects.filter(pk=new).exists())

    def test_delete_floor_with_rooms_is_409(self):
        self.as_(self.root)
        r = self.client.delete(f"{BASE}/floors/{self.floor.pk}/")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"], "This floor still has rooms.")
        self.assertTrue(Floor.objects.filter(pk=self.floor.pk).exists())

    def test_app_admin_deactivation_retires_places(self):
        self.as_(self.root)
        r = self.client.patch(f"{BASE}/floors/{self.floor.pk}/", {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.place_a.refresh_from_db()
        self.place_b.refresh_from_db()
        self.assertFalse(self.place_a.is_active)
        self.assertFalse(self.place_b.is_active)

    def test_floor_name_unique_per_building_case_insensitive(self):
        self.as_(self.root)
        r = self.client.post(f"{BASE}/floors/", {"building": self.building.pk, "name": "eg"},
                             format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("A floor with this name exists in this building.", str(r.json()))
        other = Floor.objects.create(building=self.building, name="1. OG")
        r = self.client.patch(f"{BASE}/floors/{other.pk}/", {"name": "Eg"}, format="json")
        self.assertEqual(r.status_code, 400)
        # Another building may reuse the name.
        b2 = Building.objects.create(code="32")
        r = self.client.post(f"{BASE}/floors/", {"building": b2.pk, "name": "EG"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_floor_name_clash_written_under_other_language(self):
        # A row named under English has its German column empty; the check
        # must still catch the raw (constrained) column.
        with translation.override("en"):
            other = Floor.objects.create(building=self.building, name="Basement")
        self.assertTrue(other.pk)
        self.as_(self.root)
        r = self.client.post(f"{BASE}/floors/", {"building": self.building.pk, "name_de": "basement"},
                             format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.json(), {"name": ["A floor with this name exists in this building."]})


class PlanSymbolTests(AdminRightsBase):
    def url(self):
        return f"{BASE}/floors/{self.floor.pk}/plan/"

    def test_department_admin_sets_own_symbols(self):
        self.as_(self.admin_a)
        sym = {"x": 1, "y": 2, "rotation": 90}
        r = self.client.put(self.url(), {"symbols": {str(self.place_a.pk): sym}}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.place_a.refresh_from_db()
        self.assertEqual(self.place_a.plan_symbol, sym)
        r = self.client.put(self.url(), {"symbols": {str(self.place_a.pk): None}}, format="json")
        self.assertEqual(r.status_code, 200)
        self.place_a.refresh_from_db()
        self.assertIsNone(self.place_a.plan_symbol)

    def test_admin_a_cannot_move_b_place_symbol(self):
        self.as_(self.admin_a)
        sym = {"x": 1, "y": 2, "rotation": 0}
        r = self.client.put(
            self.url(),
            {"symbols": {str(self.place_a.pk): sym, str(self.place_b.pk): sym}},
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.place_a.refresh_from_db()
        self.place_b.refresh_from_db()
        self.assertIsNone(self.place_a.plan_symbol)  # nothing written
        self.assertIsNone(self.place_b.plan_symbol)
        # Nor through the place endpoint.
        r = self.client.patch(f"{BASE}/places/{self.place_b.pk}/", {"plan_symbol": sym}, format="json")
        self.assertEqual(r.status_code, 403)
        self.place_b.refresh_from_db()
        self.assertIsNone(self.place_b.plan_symbol)

    def test_symbols_must_be_on_this_floor_and_valid(self):
        self.as_(self.root)
        elsewhere = Floor.objects.create(building=self.building, name="1. OG")
        far = Place.objects.create(
            room=Room.objects.create(floor=elsewhere, pool=self.pool_a, name="15/201"), name="15/201 A"
        )
        sym = {"x": 1, "y": 2, "rotation": 0}
        r = self.client.put(self.url(), {"symbols": {str(far.pk): sym}}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.put(self.url(), {"symbols": {str(self.place_b.pk): {"x": "a"}}}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_app_admin_saves_plan_and_symbols(self):
        self.as_(self.root)
        sym = {"x": 3, "y": 4, "rotation": 0}
        plan = {"shapes": [{"id": "r", "type": "room", "points": [[0, 0], [1, 0], [1, 1]],
                            "room_id": self.room_b.pk}]}
        r = self.client.put(self.url(), {"plan": plan, "symbols": {str(self.place_b.pk): sym}},
                            format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.floor.refresh_from_db()
        self.place_b.refresh_from_db()
        self.assertEqual(self.floor.plan["shapes"][0]["id"], "r")
        self.assertEqual(self.place_b.plan_symbol, sym)


class RoomRightsTests(AdminRightsBase):
    def test_room_create_app_admin_only_pool_optional(self):
        self.as_(self.admin_a)
        data = {"floor": self.floor.pk, "pool": self.pool_a.pk, "name": "15/110"}
        self.assertEqual(self.client.post(f"{BASE}/rooms/", data, format="json").status_code, 403)
        self.as_(self.root)
        r = self.client.post(f"{BASE}/rooms/", {"floor": self.floor.pk, "name": "15/110"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(Room.objects.get(pk=r.json()["id"]).pool_id)
        r = self.client.post(f"{BASE}/rooms/", data | {"name": "15/111"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Room.objects.get(pk=r.json()["id"]).pool_id, self.pool_a.pk)
        # App admins see unassigned rooms.
        self.assertIn(Room.objects.get(name="15/110").pk, self.ids(f"{BASE}/rooms/"))

    def test_room_delete_app_admin_only(self):
        self.as_(self.admin_a)
        self.assertEqual(self.client.delete(f"{BASE}/rooms/{self.room_a.pk}/").status_code, 403)
        self.as_(self.root)
        self.assertEqual(self.client.delete(f"{BASE}/rooms/{self.room_a.pk}/").status_code, 204)

    def test_room_update_by_its_department_admin(self):
        self.as_(self.admin_a)
        r = self.client.patch(f"{BASE}/rooms/{self.room_a.pk}/", {"name": "15/101a"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.patch(f"{BASE}/rooms/{self.room_b.pk}/", {"name": "X"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}/rooms/{self.room_b.pk}/").status_code, 404)
        self.room_b.refresh_from_db()
        self.assertEqual(self.room_b.name, "15/102")

    def test_department_admin_reads_foreign_rooms_holding_own_places(self):
        # A's own (overridden) places in B's room and in an unassigned room:
        # A reads those rooms (to reach the places), never edits them.
        Place.objects.create(room=self.room_b, name="15/102 K", pool=self.pool_a, pool_overridden=True)
        unassigned = Room.objects.create(floor=self.floor, name="15/103")
        Place.objects.create(room=unassigned, name="15/103 K", pool=self.pool_a, pool_overridden=True,
                             is_active=False)  # retired places stay reachable too
        empty_b = Room.objects.create(floor=self.floor, pool=self.pool_b, name="15/105")
        self.as_(self.admin_a)
        ids = self.ids(f"{BASE}/rooms/?include_inactive=1")
        self.assertEqual(ids, {self.room_a.pk, self.room_b.pk, unassigned.pk})
        self.assertNotIn(empty_b.pk, ids)
        self.assertEqual(self.client.get(f"{BASE}/rooms/{self.room_b.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/rooms/{empty_b.pk}/").status_code, 404)
        r = self.client.patch(f"{BASE}/rooms/{self.room_b.pk}/", {"name": "X"}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.client.patch(f"{BASE}/rooms/{unassigned.pk}/", {"name": "X"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.delete(f"{BASE}/rooms/{self.room_b.pk}/").status_code, 403)
        # B still doesn't see A's room.
        self.as_(self.admin_b)
        self.assertNotIn(self.room_a.pk, self.ids(f"{BASE}/rooms/?include_inactive=1"))

    def test_room_pool_is_read_only_on_update(self):
        for user in (self.admin_a, self.root):
            self.as_(user)
            r = self.client.patch(f"{BASE}/rooms/{self.room_a.pk}/", {"pool": self.pool_b.pk},
                                  format="json")
            self.assertEqual(r.status_code, 200, r.content)
            self.room_a.refresh_from_db()
            self.assertEqual(self.room_a.pool_id, self.pool_a.pk)

    def test_department_admin_cannot_move_room_to_other_floor(self):
        other = Floor.objects.create(building=self.building, name="1. OG")
        self.as_(self.admin_a)
        r = self.client.patch(f"{BASE}/rooms/{self.room_a.pk}/", {"floor": other.pk}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_department_admin_cannot_deactivate_room_with_other_departments_places(self):
        foreign = Place.objects.create(room=self.room_a, name="15/101 B", pool=self.pool_b,
                                       pool_overridden=True)
        self.as_(self.admin_a)
        r = self.client.patch(f"{BASE}/rooms/{self.room_a.pk}/", {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 403)
        foreign.refresh_from_db()
        self.assertTrue(foreign.is_active)
        foreign.delete()
        r = self.client.patch(f"{BASE}/rooms/{self.room_a.pk}/", {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.place_a.refresh_from_db()
        self.assertFalse(self.place_a.is_active)

    def test_room_name_unique_per_floor(self):
        self.as_(self.root)
        r = self.client.post(f"{BASE}/rooms/", {"floor": self.floor.pk, "name": "15/101"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("A room with this name exists on this floor.", str(r.json()))
        self.as_(self.admin_a)
        r = self.client.patch(f"{BASE}/rooms/{self.room_a.pk}/", {"name": "15/102"}, format="json")
        self.assertEqual(r.json(), {"name": ["A room with this name exists on this floor."]})


class PlaceRightsTests(AdminRightsBase):
    def test_list_scoped(self):
        self.as_(self.admin_a)
        self.assertEqual(self.ids(f"{BASE}/places/"), {self.place_a.pk})
        self.as_(self.root)
        loose = Place.objects.create(room=Room.objects.create(floor=self.floor, name="15/109"), name="L")
        self.assertEqual(self.ids(f"{BASE}/places/"), {self.place_a.pk, self.place_b.pk, loose.pk})

    def test_create_in_own_room_only(self):
        self.as_(self.admin_a)
        r = self.client.post(f"{BASE}/places/", {"room": self.room_a.pk, "name": "15/101 B"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Place.objects.get(pk=r.json()["id"]).pool_id, self.pool_a.pk)
        r = self.client.post(f"{BASE}/places/", {"room": self.room_b.pk, "name": "15/102 B"},
                             format="json")
        self.assertEqual(r.status_code, 403)
        unassigned = Room.objects.create(floor=self.floor, name="15/103")
        r = self.client.post(f"{BASE}/places/", {"room": unassigned.pk, "name": "15/103 A"},
                             format="json")
        self.assertEqual(r.status_code, 403)
        self.as_(self.root)
        r = self.client.post(f"{BASE}/places/", {"room": unassigned.pk, "name": "15/103 A"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(Place.objects.get(pk=r.json()["id"]).pool_id)

    def test_update_delete_by_place_department(self):
        self.as_(self.admin_a)
        url_b = f"{BASE}/places/{self.place_b.pk}/"
        self.assertEqual(self.client.patch(url_b, {"capacity": 2}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url_b).status_code, 403)
        self.assertEqual(self.client.post(f"{url_b}regenerate-qr/").status_code, 403)
        self.assertEqual(self.client.get(url_b).status_code, 404)
        self.assertTrue(Place.objects.filter(pk=self.place_b.pk).exists())
        # An overridden place of A in B's room is A's to edit.
        mine = Place.objects.create(room=self.room_b, name="15/102 B", pool=self.pool_a,
                                    pool_overridden=True)
        r = self.client.patch(f"{BASE}/places/{mine.pk}/", {"name": "15/102 C"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.as_(self.admin_b)
        self.assertEqual(
            self.client.patch(f"{BASE}/places/{mine.pk}/", {"name": "X"}, format="json").status_code, 403
        )

    def test_pool_fields_read_only(self):
        for user in (self.admin_a, self.root):
            self.as_(user)
            r = self.client.patch(
                f"{BASE}/places/{self.place_a.pk}/",
                {"pool": self.pool_b.pk, "pool_overridden": True},
                format="json",
            )
            self.assertEqual(r.status_code, 200, r.content)
            self.place_a.refresh_from_db()
            self.assertEqual(self.place_a.pool_id, self.pool_a.pk)
            self.assertFalse(self.place_a.pool_overridden)

    def test_move_rederives_pool_unless_overridden(self):
        self.as_(self.root)
        r = self.client.patch(f"{BASE}/places/{self.place_a.pk}/", {"room": self.room_b.pk},
                              format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.place_a.refresh_from_db()
        self.assertEqual(self.place_a.pool_id, self.pool_b.pk)
        kept = Place.objects.create(room=self.room_a, name="15/101 K", pool=self.pool_a,
                                    pool_overridden=True)
        r = self.client.patch(f"{BASE}/places/{kept.pk}/", {"room": self.room_b.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        kept.refresh_from_db()
        self.assertEqual(kept.pool_id, self.pool_a.pk)

    def test_department_admin_moves_only_between_own_rooms(self):
        own2 = Room.objects.create(floor=self.floor, pool=self.pool_a, name="15/104")
        self.as_(self.admin_a)
        url = f"{BASE}/places/{self.place_a.pk}/"
        self.assertEqual(self.client.patch(url, {"room": self.room_b.pk}, format="json").status_code, 403)
        self.place_a.refresh_from_db()
        self.assertEqual(self.place_a.room_id, self.room_a.pk)
        self.assertEqual(self.client.patch(url, {"room": own2.pk}, format="json").status_code, 200)
        self.place_a.refresh_from_db()
        self.assertEqual((self.place_a.room_id, self.place_a.pool_id), (own2.pk, self.pool_a.pk))

    def test_place_name_unique_per_building(self):
        other_floor = Floor.objects.create(building=self.building, name="1. OG")
        room = Room.objects.create(floor=other_floor, pool=self.pool_a, name="15/201")
        self.as_(self.admin_a)
        r = self.client.post(f"{BASE}/places/", {"room": room.pk, "name": "15/102 a"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("A place with this name exists in this building.", str(r.json()))
        r = self.client.patch(f"{BASE}/places/{self.place_a.pk}/", {"name": "15/102 A"}, format="json")
        self.assertEqual(r.status_code, 400)
        # Another building may reuse it.
        far = Room.objects.create(
            floor=Floor.objects.create(building=Building.objects.create(code="32"), name="EG"),
            pool=self.pool_a, name="32/1",
        )
        r = self.client.post(f"{BASE}/places/", {"room": far.pk, "name": "15/102 A"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        # Moving into a building with that name taken is refused too.
        r = self.client.patch(f"{BASE}/places/{r.json()['id']}/", {"room": self.room_a.pk},
                              format="json")
        self.assertEqual(r.status_code, 400)


class UniqueRaceTests(AdminRightsBase):
    def test_integrity_error_maps_to_static_message(self):
        # A clash the serializer could not see (concurrent insert) still
        # answers with the static message, not the generic integrity one.
        from unittest import mock

        from desksharing.serializers import UniqueNameMixin

        self.as_(self.root)
        with mock.patch.object(UniqueNameMixin, "check_unique_name", lambda self, attrs: None):
            r = self.client.post(f"{BASE}/rooms/", {"floor": self.floor.pk, "name": "15/101"},
                                 format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json(), {"name": ["A room with this name exists on this floor."]})


class FeatureRightsTests(AdminRightsBase):
    def test_department_admin_reads_and_creates(self):
        self.as_(self.admin_a)
        r = self.client.post(f"{BASE}/features/", {"name": "Dock", "description": "USB-C"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["description"], "USB-C")
        self.assertEqual(r.json()["images"], [])
        self.assertIn(r.json()["id"], self.ids(f"{BASE}/features/"))

    def test_department_admin_cannot_edit_delete_or_upload(self):
        f = Feature.objects.create(name="Dock")
        self.as_(self.admin_a)
        url = f"{BASE}/features/{f.pk}/"
        self.assertEqual(self.client.patch(url, {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        r = self.client.post(f"{url}images/", {"image": png()}, format="multipart")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Feature.objects.filter(pk=f.pk, name="Dock").exists())

    def test_app_admin_edits_and_deletes_only_unused(self):
        used = Feature.objects.create(name="Dock")
        self.place_a.features.add(used)
        spare = Feature.objects.create(name="Lamp")
        self.as_(self.root)
        r = self.client.patch(f"{BASE}/features/{used.pk}/", {"description": "x"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.delete(f"{BASE}/features/{used.pk}/")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"], "This equipment is still used by places.")
        self.assertTrue(Feature.objects.filter(pk=used.pk).exists())
        self.assertEqual(self.client.delete(f"{BASE}/features/{spare.pk}/").status_code, 204)

    def test_app_admin_gallery(self):
        f = Feature.objects.create(name="Dock")
        self.as_(self.root)
        r = self.client.post(f"{BASE}/features/{f.pk}/images/", {"image": png()}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        second = self.client.post(f"{BASE}/features/{f.pk}/images/", {"image": png("b.png")},
                                  format="multipart").json()
        self.assertEqual(FeatureImage.objects.filter(feature=f).count(), 2)
        r = self.client.post(f"{BASE}/features/{f.pk}/images/reorder/",
                             {"order": [second["id"], r.json()["id"]]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        row = self.client.get(f"{BASE}/features/{f.pk}/").json()
        self.assertEqual([img["id"] for img in row["images"]][0], second["id"])
        r = self.client.delete(f"{BASE}/features/{f.pk}/images/{second['id']}/")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(FeatureImage.objects.filter(feature=f).count(), 1)

    def test_feature_name_unique_case_insensitive(self):
        Feature.objects.create(name="Dock")
        self.as_(self.admin_a)
        r = self.client.post(f"{BASE}/features/", {"name": "dock"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Equipment with this name exists.", str(r.json()))
        with translation.override("en"):
            Feature.objects.create(name="Monitor")
        r = self.client.post(f"{BASE}/features/", {"name_de": "MONITOR"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.json(), {"name": ["Equipment with this name exists."]})
