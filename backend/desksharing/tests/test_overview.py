# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import hours, overview
from desksharing import privacy
from desksharing.models import Absence, Place, Reservation
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday
from desksharing.tests.test_rights import make_pool

User = get_user_model()


class OverviewBase(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)
        patcher = mock.patch("desksharing.notify.notify")
        patcher.start()
        self.addCleanup(patcher.stop)

    def at(self, hour, minute=0, day=None):
        d = day or self.day
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=hours.TZ)

    def reserve(self, place, holder, start=9, end=12, **kw):
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(self.day, start, end), **kw,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class OverviewTests(OverviewBase):
    def test_overview_members_only(self):
        outsider = User.objects.create_user("outsider", password="x")
        other_dept = AccessGroup.objects.create(name="Dept B")
        make_pool("PoolB", other_dept)
        other_dept.members.add(outsider)
        q = {"pool": self.pool.pk, "day": self.day.isoformat()}
        self.assertEqual(self.client_for(outsider).get(f"{API}/overview/", q).status_code, 404)
        self.assertEqual(APIClient().get(f"{API}/overview/", q).status_code, 403)
        self.assertEqual(self.client_for(self.member).get(f"{API}/overview/", q).status_code, 200)
        # Department admins are members, too.
        self.assertEqual(self.client_for(self.lender).get(f"{API}/overview/", q).status_code, 200)
        self.assertEqual(
            self.client_for(self.member).get(f"{API}/overview/", {"pool": "x"}).status_code, 400
        )
        # Free-now and neighbours: nothing for outsiders either.
        r = self.client_for(outsider).get(f"{API}/free-now/", {"pool": self.pool.pk})
        self.assertEqual(r.json(), [])
        res = self.reserve(self.d1, self.member)
        r = self.client_for(outsider).get(f"{API}/reservations/{res.pk}/neighbours/")
        self.assertEqual(r.status_code, 404)

    def test_department_day_states(self):
        self.reserve(self.d1, self.member, 9, 11, checked_in_at=self.at(9, 5))
        self.reserve(self.d2, self.other, 10, 12, potentially_free_at=self.at(11))
        self.reserve(self.m1, self.other, 14, 16, comment="Retro")
        data = overview.department_day(self.pool, self.day, viewer=self.member)
        self.assertEqual(data["open_hours"], [6, 20])
        [floor] = data["floors"]
        self.assertIn("plan", floor)
        places = {p["id"]: p for p in floor["places"]}
        d1 = {h["hour"]: h for h in places[self.d1.pk]["hours"]}
        self.assertEqual(d1[9]["state"], "checked_in")
        self.assertEqual(d1[9]["holder"], "Max")
        self.assertTrue(d1[9]["mine"])
        self.assertEqual(d1[11]["state"], "free")
        d2 = {h["hour"]: h for h in places[self.d2.pk]["hours"]}
        self.assertEqual(d2[10]["state"], "potentially_free")
        self.assertEqual(d2[10]["holder"], "Ola")
        self.assertFalse(d2[10]["mine"])
        [timeline] = data["meeting_rooms"]
        self.assertEqual(timeline["id"], self.m1.pk)
        [entry] = timeline["reservations"]
        self.assertEqual(
            (entry["start_hour"], entry["end_hour"], entry["holder"], entry["comment"]),
            (14, 16, "Ola", "Retro"),
        )
        # Desk comments are not part of the overview.
        self.assertNotIn("comment", d1[9])

    def test_overview_closed_hours_and_fixed_places(self):
        self.d3.fixed_owner = self.other
        self.d3.save()
        data = overview.department_day(self.pool, self.day, viewer=self.member)
        d3 = next(p for p in data["floors"][0]["places"] if p["id"] == self.d3.pk)
        self.assertTrue(d3["fixed"])
        self.assertTrue(all(h["state"] == "booked" and h["holder"] == "Ola" for h in d3["hours"]))
        Absence.objects.create(user=self.other, start_date=self.day, end_date=self.day,
                               kind="vacation")
        data = overview.department_day(self.pool, self.day, viewer=self.member)
        d3 = next(p for p in data["floors"][0]["places"] if p["id"] == self.d3.pk)
        self.assertTrue(all(h["state"] == "free" for h in d3["hours"]))
        # A weekend day is closed.
        sunday = next_weekday(6)
        data = overview.department_day(self.pool, sunday, viewer=self.member)
        self.assertIsNone(data["open_hours"])
        self.assertEqual(data["floors"][0]["places"][0]["hours"], [])

    def test_room_neighbours(self):
        mine = self.reserve(self.d1, self.member, 9, 12)
        self.reserve(self.d2, self.other, 11, 13)
        self.reserve(self.d3, self.lender, 12, 14)  # no overlap
        self.reserve(self.m1, self.lender, 9, 12)  # other room
        self.assertEqual(overview.room_neighbours(mine, viewer=self.member), ["Ola"])
        r = self.client_for(self.member).get(f"{API}/reservations/{mine.pk}/neighbours/")
        self.assertEqual(r.json(), ["Ola"])
        # Colleagues cannot look up someone else's reservation.
        r = self.client_for(self.other).get(f"{API}/reservations/{mine.pk}/neighbours/")
        self.assertEqual(r.status_code, 404)

    def test_free_now(self):
        now = self.at(10, 30)
        self.reserve(self.d1, self.other, 10, 11)
        self.reserve(self.d2, self.other, 13, 15)
        rows = overview.free_now(self.pool, viewer=self.member, now=now)
        by_id = {r["id"]: r for r in rows}
        self.assertNotIn(self.d1.pk, by_id)
        self.assertEqual(by_id[self.d2.pk]["free_until"], self.at(13).isoformat())
        self.assertEqual(by_id[self.d3.pk]["free_until"], self.at(20).isoformat())
        self.assertIn(self.m1.pk, by_id)
        rows = overview.free_now(self.pool, viewer=self.member, kind="desk", now=now)
        self.assertNotIn(self.m1.pk, {r["id"] for r in rows})
        # Outside the business hours nothing is free.
        self.assertEqual(overview.free_now(self.pool, viewer=self.member, now=self.at(21)), [])

    def test_free_now_api(self):
        r = self.client_for(self.member).get(
            f"{API}/free-now/", {"pool": self.pool.pk, "kind": "desk"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        r = self.client_for(self.member).get(f"{API}/free-now/", {"pool": self.pool.pk,
                                                                  "kind": "x"})
        self.assertEqual(r.status_code, 400)


class HoursEndpointTests(OverviewBase):
    def test_hours_open_closed_and_members_only(self):
        q = {"pool": self.pool.pk, "day": self.day.isoformat()}
        r = self.client_for(self.member).get(f"{API}/hours/", q)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body["open"], body["closed"]), ([6, 20], []))
        self.assertIsNone(body["min_hour"])
        self.assertIsInstance(body["closed_weekdays"], list)
        self.assertEqual(body["max_day"] is None, not self.pool.max_booking_months)
        self.assertEqual(
            self.client_for(self.member).get(f"{API}/hours/", {"pool": self.pool.pk}).status_code,
            400,
        )
        outsider = User.objects.create_user("hours_out", password="x")
        self.assertEqual(self.client_for(outsider).get(f"{API}/hours/", q).status_code, 404)
        self.assertEqual(APIClient().get(f"{API}/hours/", q).status_code, 403)
        # Closed weekday: no open interval.
        from desksharing.models import DeskSettings

        s = DeskSettings.objects.get(pool=self.pool)
        s.business_hours = {**(s.business_hours or {}), str(self.day.weekday()): None}
        s.save()
        r = self.client_for(self.member).get(f"{API}/hours/", q)
        body = r.json()
        self.assertEqual((body["open"], body["closed"]), (None, []))
        self.assertIn(self.day.weekday(), body["closed_weekdays"])
        # Today: the current Berlin hour is the first bookable one.
        today = timezone.localtime(timezone.now(), hours.TZ)
        r = self.client_for(self.member).get(
            f"{API}/hours/", {"pool": self.pool.pk, "day": today.date().isoformat()}
        )
        self.assertEqual(r.json()["min_hour"], today.hour)


class PoolFeaturesEndpointTests(OverviewBase):
    def test_features_members_only(self):
        from desksharing.models import Feature

        Feature.objects.create(pool=self.pool, name="Monitor")
        r = self.client_for(self.member).get(f"{API}/features/", {"pool": self.pool.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([f["name"] for f in r.json()], ["Monitor"])
        outsider = User.objects.create_user("feat_out", password="x")
        self.assertEqual(
            self.client_for(outsider).get(f"{API}/features/", {"pool": self.pool.pk}).status_code,
            404,
        )


class PlaceStatusTests(OverviewBase):
    def test_place_status_states(self):
        res = self.reserve(self.d1, self.member, 9, 11)
        self.reserve(self.d1, self.other, 14, 15)
        st = overview.place_status(self.d1, at=self.at(8), anonymous=False)
        self.assertEqual(st["state"], "free")
        self.assertEqual(st["until"], self.at(9).isoformat())
        self.assertEqual(st["next"], {"start": self.at(9).isoformat(),
                                      "end": self.at(11).isoformat()})
        st = overview.place_status(self.d1, at=self.at(10), anonymous=False)
        self.assertEqual((st["state"], st["holder"]), ("booked", "Max"))
        self.assertEqual(st["until"], self.at(11).isoformat())
        self.assertEqual(st["next"]["start"], self.at(14).isoformat())
        Reservation.objects.filter(pk=res.pk).update(potentially_free_at=self.at(10))
        self.assertEqual(
            overview.place_status(self.d1, at=self.at(10), anonymous=False)["state"],
            "potentially_free",
        )
        Reservation.objects.filter(pk=res.pk).update(checked_in_at=self.at(9))
        self.assertEqual(
            overview.place_status(self.d1, at=self.at(10), anonymous=False)["state"],
            "checked_in",
        )
        st = overview.place_status(self.d1, at=self.at(21), anonymous=False)
        self.assertEqual((st["state"], st["holder"]), ("closed", None))
        self.d2.is_active = False
        self.d2.save()
        self.assertEqual(
            overview.place_status(self.d2, at=self.at(10), anonymous=False)["state"], "closed"
        )

    def test_place_status_anonymous_for_lending_style_call(self):
        self.reserve(self.d1, self.member, 9, 11)
        self.reserve(self.m1, self.member, 9, 11, comment="Planning")
        for place in (self.d1, self.m1):
            st = overview.place_status(place, at=self.at(10), anonymous=True)
            self.assertEqual(st["state"], "booked")
            self.assertIsNone(st["holder"])
            self.assertNotIn("Max", str(st))
        self.d3.fixed_owner = self.member
        self.d3.save()
        st = overview.place_status(self.d3, at=self.at(10), anonymous=True)
        self.assertEqual((st["state"], st["holder"]), ("booked", None))
        self.assertEqual(
            overview.place_status(self.d3, at=self.at(10), anonymous=False)["holder"], "Max"
        )

    def test_overview_now_for_today(self):
        data = overview.department_day(
            self.pool, self.day, viewer=self.member, now=self.at(10)
        )
        place = data["floors"][0]["places"][0]
        self.assertEqual(place["now"]["state"], "free")
        data = overview.department_day(
            self.pool, self.day, viewer=self.member, now=self.at(10) - timedelta(days=1)
        )
        self.assertIsNone(data["floors"][0]["places"][0]["now"])


class OverviewPastDayTests(OverviewBase):
    def test_past_days_only_for_department_admins(self):
        past = timezone.localdate() - timedelta(days=1)
        q = {"pool": self.pool.pk, "day": past.isoformat()}
        r = self.client_for(self.member).get(f"{API}/overview/", q)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client_for(self.lender).get(f"{API}/overview/", q).status_code, 200)
        today = {"pool": self.pool.pk, "day": timezone.localdate().isoformat()}
        self.assertEqual(self.client_for(self.member).get(f"{API}/overview/", today).status_code, 200)


class QueryCountTests(OverviewBase):
    """The number of queries must not grow with the number of places."""

    def add_places(self, n):
        owners = [User.objects.create_user(f"owner{i}_{n}", password="x") for i in range(n)]
        self.group.members.add(*owners)
        for i, owner in enumerate(owners):
            hidden = Place.objects.create(room=self.room, name=f"F{n}-{i}", fixed_owner=owner)
            privacy.set_hide_name(owner, i % 2 == 0)
            Absence.objects.create(user=owner, start_date=self.day, end_date=self.day,
                                   kind="vacation") if i % 3 == 0 else None
            free = Place.objects.create(room=self.room, name=f"P{n}-{i}")
            Reservation.objects.create(
                place=free, holder=owner, booked_by=owner,
                period=hours.local_range(self.day, 9, 11),
            )
            del hidden

    def count(self, fn):
        with CaptureQueriesContext(connection) as ctx:
            fn()
        return len(ctx.captured_queries)

    def measure(self):
        member = User.objects.get(pk=self.member.pk)  # fresh rights cache
        return (
            self.count(lambda: overview.department_day(
                self.pool, self.day, viewer=member, now=self.at(10))),
            self.count(lambda: overview.free_now(self.pool, viewer=member, now=self.at(10))),
        )

    def test_queries_do_not_grow_with_places(self):
        self.add_places(3)
        small = self.measure()
        self.add_places(10)
        large = self.measure()
        self.assertEqual(small, large)
