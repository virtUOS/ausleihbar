# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""The system group "Alle Angemeldeten" in desksharing (ADR-0021): it never
counts at department level, opens rooms/places to everyone as guests, and
those guests see no person data (privacy (2))."""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from accounts.roles import all_users_group
from accounts.testing import open_pool
from desksharing import assignment, overview, privacy, rights
from desksharing.models import DeskSettings, Place, Reservation, Room, Series
from desksharing.serializers import ReservationSerializer
from desksharing.tests.test_booking import API
from desksharing.tests.test_overview import OverviewBase
from desksharing.tests.test_rights import make_pool, new_pool

User = get_user_model()
BASE = "/api/desks/manage"


class DepartmentLevelTests(TestCase):
    """The pool-level group means "lending open to all", never desks."""

    def setUp(self):
        self.all = all_users_group()
        self.lender = User.objects.create_user("lender", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.lender)

    def test_only_all_users_group_cannot_enable(self):
        pool = new_pool("Open")
        open_pool(pool)
        s = DeskSettings.for_pool(pool)
        s.enabled = True
        with self.assertRaises(ValidationError) as cm:
            s.full_clean()
        self.assertIn("enabled", cm.exception.message_dict)
        with self.assertRaises(ValidationError):
            assignment.ensure_desksharing_enabled(pool)
        self.assertFalse(DeskSettings.for_pool(pool).enabled)
        pool.lender_group.members.add(self.lender)
        r = self.client.put(f"{BASE}/settings/{pool.pk}/", {"enabled": True}, format="json")
        self.assertEqual(r.status_code, 400, r.content)

    def test_pool_group_does_not_make_everyone_member(self):
        group = AccessGroup.objects.create(name="Dept A")
        pool = make_pool("A", group)
        open_pool(pool)
        pool.lender_group.members.add(self.lender)
        member = User.objects.create_user("member", password="x", first_name="Mia")
        group.members.add(member)
        outsider = User.objects.create_user("zoe", password="x", first_name="Zoe")
        self.assertIn(pool.pk, rights.member_pool_ids(member))
        self.assertNotIn(pool.pk, rights.member_pool_ids(outsider))
        self.assertNotIn(pool.pk, rights.visible_pool_ids(outsider))
        ids = rights.member_user_ids(pool.pk)
        self.assertIn(member.pk, ids)
        self.assertNotIn(outsider.pk, ids)
        r = self.client.get(f"{BASE}/people/", {"pool": pool.pk, "q": "zoe"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), [])

    def test_course_group_member_is_no_department_member(self):
        from lti.models import LtiPlatform
        from lti.services import create_link

        group = AccessGroup.objects.create(name="Dept A")
        pool = make_pool("A", group)
        platform = LtiPlatform.objects.create(
            name="Moodle", issuer="https://moodle.example.org", client_id="c1",
            auth_login_url="https://lms.example.org/auth",
            auth_token_url="https://lms.example.org/token",
        )
        link, _ = create_link(
            platform=platform, context_id="c1", pool=pool, title="Kurs"
        )
        learner = User.objects.create_user("learner", password="x", first_name="Lea")
        link.access_group.members.add(learner)
        self.assertNotIn(learner.pk, rights.member_user_ids(pool.pk))
        pool.lender_group.members.add(self.lender)
        r = self.client.get(f"{BASE}/people/", {"pool": pool.pk, "q": "learner"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), [])

    def test_all_users_group_is_no_assistant_group(self):
        group = AccessGroup.objects.create(name="Dept A")
        pool = make_pool("A", group)
        pool.lender_group.members.add(self.lender)
        r = self.client.put(
            f"{BASE}/settings/{pool.pk}/", {"assistant_group": self.all.pk}, format="json"
        )
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("assistant_group", r.json())
        s = DeskSettings.for_pool(pool)
        s.assistant_group = self.all
        with self.assertRaises(ValidationError) as cm:
            s.full_clean()
        self.assertIn("assistant_group", cm.exception.message_dict)
        # Even if set through the ORM it grants nobody assistant rights.
        DeskSettings.objects.filter(pool=pool).update(assistant_group=self.all)
        outsider = User.objects.create_user("o", password="x")
        self.assertNotIn(pool.pk, rights.assistant_pool_ids(outsider))

    def test_access_group_picker_offers_group_never_in_pool(self):
        group = AccessGroup.objects.create(name="Dept A")
        pool = make_pool("A", group)
        open_pool(pool)
        pool.lender_group.members.add(self.lender)
        r = self.client.get(f"{BASE}/access-groups/", {"pool": pool.pk})
        self.assertEqual(r.status_code, 200, r.content)
        rows = {g["id"]: g for g in r.json()}
        self.assertIn(self.all.pk, rows)
        self.assertFalse(rows[self.all.pk]["in_pool"])
        self.assertTrue(rows[self.all.pk]["system_all"])
        self.assertFalse(rows[group.pk]["system_all"])
        self.assertTrue(rows[group.pk]["in_pool"])


class OpenPlaceTests(OverviewBase):
    """Room/place access groups: the group makes every user a guest of those
    places, without names."""

    def setUp(self):
        super().setUp()
        self.all = all_users_group()
        open_pool(self.pool)  # pool-level: lending only, never desks
        self.open_room = Room.objects.create(floor=self.floor, pool=self.pool, name="Open")
        self.open_room.access_groups.set([self.all])
        self.o1 = Place.objects.create(room=self.open_room, name="O1")
        self.o2 = Place.objects.create(room=self.open_room, name="O2")
        self.fixed = Place.objects.create(room=self.open_room, name="OF", fixed_owner=self.other)
        meet = Room.objects.create(
            floor=self.floor, pool=self.pool, name="OM", kind=Room.Kind.MEETING
        )
        self.om = Place.objects.create(
            room=meet, name="OM1", kind=Place.Kind.MEETING_ROOM, capacity=4
        )
        for place in (self.o1, self.o2, self.fixed, self.om):
            place.access_groups.set([self.all])
        self.outsider = User.objects.create_user("zoe", password="x", first_name="Zoe")
        self.res = self.reserve(self.o1, self.member, comment="Max sitzt hier")
        self.mres = self.reserve(self.om, self.member, comment="Team Max")

    def fresh(self, user):
        return User.objects.get(pk=user.pk)

    def test_everyone_is_guest_of_exactly_those_places(self):
        self.assertEqual(
            rights.guest_place_ids(self.outsider, self.pool.pk),
            {self.o1.pk, self.o2.pk, self.fixed.pk, self.om.pk},
        )
        self.assertNotIn(self.pool.pk, rights.member_pool_ids(self.outsider))

    def test_guest_books_free_hour(self):
        body = {
            "day": self.day.isoformat(), "start_hour": 13, "end_hour": 14,
            "place_ids": [self.o2.pk],
        }
        r = self.client_for(self.outsider).post(f"{API}/reservations/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["reservations"][0]["holder_id"], self.outsider.pk)

    def test_overview_has_no_person_data(self):
        data = overview.department_day(
            self.pool, self.day, viewer=self.outsider, now=self.at(10)
        )
        places = {p["id"]: p for f in data["floors"] for p in f["places"]}
        self.assertEqual(set(places), {self.o1.pk, self.o2.pk, self.fixed.pk, self.om.pk})
        for place in places.values():
            self.assertFalse(place["people_visible"])
            for entry in place["hours"]:
                self.assertIsNone(entry["holder"])
        o1_hours = {e["hour"]: e for e in places[self.o1.pk]["hours"]}
        self.assertEqual(o1_hours[10]["state"], "booked")
        self.assertIsNone(places[self.o1.pk]["now"]["holder"])
        self.assertEqual(places[self.fixed.pk]["now"]["state"], "booked")
        self.assertIsNone(places[self.fixed.pk]["now"]["holder"])
        [room] = data["meeting_rooms"]
        [entry] = room["reservations"]
        self.assertIsNone(entry["holder"])
        self.assertEqual(entry["comment"], "")

    def test_overview_api_has_no_names(self):
        r = self.client_for(self.outsider).get(
            f"{API}/overview/", {"pool": self.pool.pk, "day": self.day.isoformat()}
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.content.decode()
        for secret in ("Max", "Ola", "Team"):
            self.assertNotIn(secret, body)

    def test_reservation_payload_has_no_person_data(self):
        for res in (self.res, self.mres):
            data = ReservationSerializer(res, context={"viewer": self.outsider}).data
            self.assertIsNone(data["holder_id"])
            self.assertIsNone(data["booked_by_id"])
            self.assertEqual(data["comment"], "")
            self.assertIsNone(privacy.holder_label(res, viewer=self.outsider))
        self.assertIsNone(privacy.fixed_owner_label(self.fixed, viewer=self.outsider))

    def test_series_has_no_person_data(self):
        series = SimpleNamespace(
            place=self.o1, pool_id=self.pool.pk, holder=self.member, holder_id=self.member.pk
        )
        self.assertIsNone(privacy.series_user_id(series, self.member.pk, viewer=self.outsider))
        self.assertEqual(
            privacy.series_user_id(series, self.member.pk, viewer=self.member), self.member.pk
        )
        self.assertEqual(
            privacy.series_user_id(series, self.member.pk, viewer=self.lender), self.member.pk
        )

    def test_holder_sees_own_data(self):
        mine = self.reserve(self.o2, self.outsider, comment="mein Platz")
        data = ReservationSerializer(mine, context={"viewer": self.outsider}).data
        self.assertEqual(data["holder_id"], self.outsider.pk)
        self.assertEqual(data["comment"], "mein Platz")
        self.assertEqual(privacy.holder_label(mine, viewer=self.outsider), "Zoe")

    def test_member_and_real_guest_see_names(self):
        gg = AccessGroup.objects.create(name="Guests")
        guest = User.objects.create_user("guest", password="x")
        gg.members.add(guest)
        self.o1.access_groups.add(gg)
        for viewer in (self.fresh(self.member), self.fresh(guest), self.fresh(self.lender)):
            self.assertTrue(rights.sees_people(viewer, self.o1))
            self.assertEqual(privacy.holder_label(self.res, viewer=viewer), "Max")
            self.assertEqual(privacy.comment_for(self.res, viewer=viewer), "Max sitzt hier")
        # The real guest sees names on their place only; a place's real
        # group gives nothing to those who reach it via the all-users group.
        self.assertFalse(rights.sees_people(self.fresh(guest), self.o2))
        outsider = self.fresh(self.outsider)
        self.assertFalse(rights.sees_people(outsider, self.o1))
        self.assertIsNone(privacy.holder_label(self.res, viewer=outsider))
        member = self.fresh(self.other)
        data = overview.department_day(self.pool, self.day, viewer=member, now=self.at(10))
        places = {p["id"]: p for f in data["floors"] for p in f["places"]}
        self.assertTrue(places[self.o1.pk]["people_visible"])
        self.assertEqual(places[self.o1.pk]["now"]["holder"], "Max")
        self.assertEqual(data["meeting_rooms"][-1]["reservations"][0]["holder"], "Max")

    def test_displays_unchanged(self):
        self.assertEqual(privacy.holder_label(self.res, viewer=None), "Max")
        self.assertEqual(privacy.fixed_owner_label(self.fixed, viewer=None), "Ola")

    def assert_refused(self, r):
        self.assertEqual(r.status_code, 403, r.content)
        self.assertEqual(r.json()["code"], "no_people_access")
        self.assertTrue(r.json()["detail"])

    def test_release_request_refused(self):
        c = self.client_for(self.outsider)
        r = c.post(f"{API}/release-requests/", {"reservation_id": self.res.pk}, format="json")
        self.assert_refused(r)

    def test_swap_request_refused(self):
        mine = self.reserve(self.o2, self.outsider, start=9, end=12)
        c = self.client_for(self.outsider)
        r = c.post(
            f"{API}/swap-requests/", {"mine_id": mine.pk, "theirs_id": self.res.pk},
            format="json",
        )
        self.assert_refused(r)

    def test_take_over_request_refused(self):
        c = self.client_for(self.outsider)
        r = c.post(f"{API}/reservations/days/", {
            "place_ids": [self.o1.pk], "days": [self.day.isoformat()],
            "start_hour": 10, "end_hour": 11, "on_taken": "request",
        }, format="json")
        self.assert_refused(r)
        self.assertFalse(Reservation.objects.filter(holder=self.outsider).exists())

    def test_no_right_at_all_stays_not_allowed(self):
        # A place that does not carry the all-users group: the requester has
        # no booking right, so the answer is not_allowed (checked first), not
        # the people-access refusal.
        theirs = self.reserve(self.d1, self.other, start=9, end=12)
        c = self.client_for(self.outsider)
        r = c.post(f"{API}/release-requests/", {"reservation_id": theirs.pk}, format="json")
        self.assertEqual(r.json()["code"], "not_allowed", r.content)
        mine = self.reserve(self.o2, self.outsider, start=9, end=12)
        r = c.post(
            f"{API}/swap-requests/", {"mine_id": mine.pk, "theirs_id": theirs.pk},
            format="json",
        )
        self.assertEqual(r.json()["code"], "not_allowed", r.content)

    def test_real_guest_may_still_request(self):
        gg = AccessGroup.objects.create(name="Guests")
        guest = User.objects.create_user("guest", password="x")
        gg.members.add(guest)
        self.o1.access_groups.add(gg)
        r = self.client_for(guest).post(
            f"{API}/release-requests/", {"reservation_id": self.res.pk}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)

    def test_admin_of_booking_department_keeps_names(self):
        """``Reservation.pool`` keeps the booking's department: its admins
        keep seeing the holder after the place moved on."""
        other_pool = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        Place.objects.filter(pk=self.o1.pk).update(pool=other_pool, pool_overridden=True)
        res = Reservation.objects.select_related("place").get(pk=self.res.pk)
        self.assertEqual(res.pool_id, self.pool.pk)
        lender = self.fresh(self.lender)
        self.assertFalse(rights.sees_people(lender, res.place))
        self.assertEqual(privacy.holder_label(res, viewer=lender), "Max")
        series = SimpleNamespace(
            place=res.place, pool_id=self.pool.pk, holder=self.member, holder_id=self.member.pk
        )
        self.assertEqual(privacy.series_user_id(series, self.member.pk, viewer=lender), self.member.pk)
        # Not for the all-users guest.
        self.assertIsNone(privacy.holder_label(res, viewer=self.fresh(self.outsider)))

    def test_series_take_over_request_refused(self):
        r = self.client_for(self.outsider).post(f"{API}/series/", {
            "place_id": self.o1.pk, "weekdays": [self.day.weekday()],
            "start_hour": 10, "end_hour": 11,
            "valid_from": self.day.isoformat(), "valid_until": self.day.isoformat(),
            "on_taken": "request",
        }, format="json")
        self.assert_refused(r)
        self.assertFalse(Series.objects.filter(holder=self.outsider).exists())

    def test_availability_flags_people(self):
        q = {
            "pool": self.pool.pk, "kind": "desk", "start_hour": 10, "end_hour": 11,
            "days": self.day.isoformat(),
        }
        rows = self.client_for(self.outsider).get(f"{API}/availability/", q).json()
        self.assertTrue(rows)
        self.assertTrue(all(not r["people_visible"] for r in rows))
        o1 = next(r for r in rows if r["id"] == self.o1.pk)
        self.assertEqual(o1["taken_days"], [self.day.isoformat()])
        rows = self.client_for(self.other).get(f"{API}/availability/", q).json()
        self.assertTrue(all(r["people_visible"] for r in rows))
