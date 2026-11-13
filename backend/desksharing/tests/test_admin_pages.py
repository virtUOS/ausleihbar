# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing.models import DeskSettings
from desksharing.tests.test_places import BASE, PlaceTestBase

User = get_user_model()


class PeopleSearchTests(PlaceTestBase):
    def setUp(self):
        super().setUp()
        self.max = User.objects.create_user("mm", password="x", first_name="Max", last_name="Muster")
        self.group.members.add(self.max)
        self.outsider = User.objects.create_user("oo", password="x", first_name="Maxine", last_name="Fremd")
        self.assistant = User.objects.create_user("asst", password="x", first_name="Ann", last_name="Assist")
        agroup = AccessGroup.objects.create(name="Assistants")
        agroup.members.add(self.assistant)
        self.group.members.add(self.assistant)
        s = DeskSettings.for_pool(self.pool)
        s.assistant_group = agroup
        s.save()

    def search(self, q, pool=None):
        return self.client.get(f"{BASE}/people/", {"pool": pool or self.pool.pk, "q": q})

    def test_finds_department_members_by_name_only(self):
        r = self.search("max")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["name"] for p in r.json()], ["Max Muster"])
        self.assertEqual(set(r.json()[0]), {"id", "name"})
        # Not found by username or by e-mail.
        self.assertEqual(self.search("asst").json(), [])

    def test_min_length(self):
        self.assertEqual(self.search("ma").status_code, 400)

    def test_assistant_allowed_member_and_other_pool_not(self):
        self.client.force_authenticate(self.assistant)
        self.assertEqual(self.search("max").status_code, 200)
        self.client.force_authenticate(self.max)
        self.assertEqual(self.search("max").status_code, 403)
        self.client.force_authenticate(self.lender)
        self.assertEqual(self.search("max", pool=self.other_pool.pk).status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.search("max").status_code, (401, 403))

    def test_whoami_assistant_pools(self):
        self.client.force_login(self.assistant)
        data = self.client.get("/api/whoami/").json()
        self.assertEqual(data["desk_assistant_pool_ids"], [self.pool.pk])
        self.assertEqual(data["desk_admin_pool_ids"], [])


class AccessGroupListTests(PlaceTestBase):
    def test_lists_pool_and_ordinary_groups_not_system(self):
        AccessGroup.objects.create(name="Ordinary")
        AccessGroup.objects.create(name="Admins2", is_admin=True)
        r = self.client.get(f"{BASE}/access-groups/", {"pool": self.pool.pk})
        self.assertEqual(r.status_code, 200)
        names = {g["name"]: g["in_pool"] for g in r.json()}
        self.assertTrue(names["Dept A"])
        self.assertFalse(names["Ordinary"])
        self.assertNotIn("Admins2", names)
        self.assertFalse(any(n.startswith("Verleiher") for n in names))

    def test_permissions(self):
        self.assertEqual(
            self.client.get(f"{BASE}/access-groups/", {"pool": self.other_pool.pk}).status_code, 404
        )
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.get(f"{BASE}/access-groups/", {"pool": self.pool.pk}).status_code, 403
        )


class PlaceQrAndOwnerNameTests(PlaceTestBase):
    def test_qr_png_and_owner_name(self):
        place = self.desk(fixed_owner=self.member)
        r = self.client.get(f"{BASE}/places/{place.pk}/qr/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertTrue(r.content.startswith(b"\x89PNG"))
        data = self.client.get(f"{BASE}/places/{place.pk}/").json()
        self.assertEqual(data["fixed_owner_name"], "member")
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(f"{BASE}/places/{place.pk}/qr/").status_code, 403)



class PlaceValidationTests(PlaceTestBase):
    def url(self, place):
        return f"{BASE}/places/{place.pk}/"

    def test_fixed_owner_must_be_active_department_member(self):
        place = self.desk()
        stranger = User.objects.create_user("stranger", password="x", first_name="Sam")
        r = self.client.patch(self.url(place), {"fixed_owner": stranger.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("Sam", r.content.decode())
        self.member.is_active = False
        self.member.save()
        r = self.client.patch(self.url(place), {"fixed_owner": self.member.pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.member.is_active = True
        self.member.save()
        r = self.client.patch(self.url(place), {"fixed_owner": self.member.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["fixed_owner_name"], "member")

    def test_meeting_room_has_no_owner(self):
        r = self.client.post(f"{BASE}/places/", {
            "room": self.room.pk, "kind": "meeting_room", "name": "M", "capacity": 4,
            "fixed_owner": self.member.pk,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_access_groups_exclude_system_and_admin_groups(self):
        place = self.desk()
        ok = AccessGroup.objects.create(name="Ordinary")
        admin = AccessGroup.objects.create(name="Adm", is_admin=True)
        r = self.client.patch(self.url(place), {"access_groups": [ok.pk]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        for bad in (admin, self.pool.lender_group):
            r = self.client.patch(self.url(place), {"access_groups": [bad.pk]}, format="json")
            self.assertEqual(r.status_code, 400)

    def test_names_per_language(self):
        r = self.client.post(f"{BASE}/features/", {
            "pool": self.pool.pk, "name_de": "Monitor", "name_en": "Screen",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["name_de"], r.json()["name_en"]), ("Monitor", "Screen"))

    def test_inactive_rows_listed_on_request(self):
        place = self.desk(is_active=False)
        self.room.is_active = False
        self.room.save()
        self.assertNotIn(place.pk, [p["id"] for p in self.client.get(f"{BASE}/places/").json()["results"]])
        listed = self.client.get(f"{BASE}/places/", {"include_inactive": 1}).json()["results"]
        self.assertIn(place.pk, [p["id"] for p in listed])
        rooms = self.client.get(f"{BASE}/rooms/", {"include_inactive": 1}).json()["results"]
        self.assertFalse(rooms[0]["is_active"])


class PeopleScaleTests(PlaceTestBase):
    def test_member_found_among_many_non_members_with_bounded_queries(self):
        User.objects.bulk_create(
            [User(username=f"nm{i}", first_name="Zoe", last_name=f"N{i}") for i in range(120)]
        )
        target = User.objects.create_user("zz", password="x", first_name="Zoe", last_name="Zzz")
        self.group.members.add(target)
        with self.assertNumQueries(9):
            r = self.client.get(f"{BASE}/people/", {"pool": self.pool.pk, "q": "zoe"})
        self.assertEqual([p["name"] for p in r.json()], ["Zoe Zzz"])


class FreeHolderTests(PlaceTestBase):
    def test_free_list_uses_holders_rights(self):
        from desksharing.models import Place as P
        restricted = AccessGroup.objects.create(name="Only")
        place = self.desk(name="R")
        place.access_groups.add(restricted)
        asst = User.objects.create_user("asst2", password="x")
        self.group.members.add(asst)
        ag = AccessGroup.objects.create(name="A2")
        ag.members.add(asst)
        s = DeskSettings.for_pool(self.pool)
        s.assistant_group = ag
        s.save()
        from desksharing.tests.test_booking import next_weekday
        q = {"pool": self.pool.pk, "kind": "desk", "day": next_weekday(1).isoformat(),
             "start_hour": 9, "end_hour": 11}
        self.client.force_authenticate(asst)
        ids = lambda r: [p["id"] for p in r.json()]
        self.assertNotIn(place.pk, ids(self.client.get(f"{BASE.replace('/manage','')}/free/", q)))
        restricted.members.add(self.member)
        r = self.client.get(f"{BASE.replace('/manage','')}/free/", {**q, "holder": self.member.pk})
        self.assertIn(place.pk, ids(r))
        self.client.force_authenticate(self.member)
        r = self.client.get(f"{BASE.replace('/manage','')}/free/", {**q, "holder": asst.pk})
        self.assertEqual(r.status_code, 403)


class AbsencePoolFilterTests(PlaceTestBase):
    def test_pool_param(self):
        from datetime import date
        from desksharing.models import Absence
        self.group.members.add(self.member)
        Absence.objects.create(user=self.member, start_date=date(2099, 1, 1), end_date=date(2099, 1, 2), kind="vacation")
        other = User.objects.create_user("o2", password="x")
        Absence.objects.create(user=other, start_date=date(2099, 1, 1), end_date=date(2099, 1, 2), kind="vacation")
        r = self.client.get(f"{BASE}/absences/", {"pool": self.pool.pk})
        self.assertEqual([a["user"] for a in r.json()], [self.member.pk])
        self.assertEqual(self.client.get(f"{BASE}/absences/", {"pool": self.other_pool.pk}).status_code, 404)


class DeactivateViaPatchTests(PlaceTestBase):
    def reserve(self, place):
        from datetime import timedelta
        from django.utils import timezone
        from desksharing import hours
        from desksharing.models import Reservation
        day = timezone.localtime(timezone.now(), hours.TZ).date() + timedelta(days=3)
        return Reservation.objects.create(
            place=place, holder=self.member, booked_by=self.member,
            period=hours.local_range(day, 9, 11),
        )

    def check(self, url, place):
        from unittest import mock
        res = self.reserve(place)
        with mock.patch("desksharing.notify.notify") as notify, self.captureOnCommitCallbacks(execute=True):
            r = self.client.patch(url, {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        res.refresh_from_db()
        self.assertEqual(res.status, "cancelled")
        notify.assert_called_once()
        place.refresh_from_db()
        self.assertFalse(place.is_active)

    def test_place_patch_retires(self):
        place = self.desk()
        self.check(f"{BASE}/places/{place.pk}/", place)

    def test_room_patch_retires_its_places(self):
        place = self.desk()
        self.check(f"{BASE}/rooms/{self.room.pk}/", place)
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_active)

    def test_reactivating_does_not_touch_reservations(self):
        place = self.desk(is_active=False)
        r = self.client.patch(f"{BASE}/places/{place.pk}/", {"is_active": True}, format="json")
        self.assertEqual(r.status_code, 200)
        place.refresh_from_db()
        self.assertTrue(place.is_active)


class AccessGroupPickerExclusionTests(PlaceTestBase):
    def test_pool_lender_and_admin_groups_not_offered(self):
        AccessGroup.objects.create(name="Adm3", is_admin=True)
        names = [g["name"] for g in self.client.get(f"{BASE}/access-groups/", {"pool": self.pool.pk}).json()]
        self.assertNotIn("Adm3", names)
        self.assertFalse(any(n.startswith("Verleiher") for n in names))
