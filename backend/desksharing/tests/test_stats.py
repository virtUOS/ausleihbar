# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import time
from datetime import datetime, timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from django.contrib.auth import get_user_model
from desksharing import hours, stats
from desksharing.models import Absence, DeskSettings, Place, Reservation
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday

User = get_user_model()


class StatsBase(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)  # Tuesday

    def at(self, hour, minute=0, day=None):
        d = day or self.day
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=hours.TZ)

    def reserve(self, place, holder, start=9, end=12, day=None, **kw):
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(day or self.day, start, end), **kw,
        )

    def stats(self, start=None, end=None):
        return stats.department_stats(self.pool, start or self.day, end or self.day)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class StatsTests(StatsBase):
    def test_standard_places_only_as_quota(self):
        self.reserve(self.d1, self.member, 9, 12)
        self.reserve(self.d2, self.other, 10, 11)
        self.reserve(self.m1, self.member, 9, 11)
        data = self.stats()
        self.assertEqual(data["quota"]["desk"]["booked_h"], 4)
        self.assertEqual(data["quota"]["meeting_room"]["booked_h"], 2)
        self.assertEqual(data["special"], [])
        # Cancelled reservations are not counted.
        self.reserve(self.d3, self.other, 9, 10, status=Reservation.Status.CANCELLED)
        self.assertEqual(self.stats()["quota"]["desk"]["booked_h"], 4)
        # Heatmap: weekday 1, hour 10 -> d1 and d2 of three desks.
        self.assertEqual(data["quota"]["desk"]["heatmap"][1][10], 66.7)
        self.assertEqual(data["quota"]["desk"]["heatmap"][1][9], 33.3)
        self.assertNotIn(5, data["quota"]["desk"]["heatmap"])  # Saturday closed

    def test_special_place_individual(self):
        Place.objects.filter(pk=self.d3.pk).update(is_special=True)
        self.reserve(self.d3, self.member, 9, 11)
        self.reserve(self.d1, self.member, 9, 10)
        data = self.stats()
        self.assertEqual(data["quota"]["desk"]["booked_h"], 1)
        [entry] = data["special"]
        self.assertEqual(entry["place"]["id"], self.d3.pk)
        self.assertEqual(entry["place"]["name"], "D3")
        self.assertEqual(entry["booked_h"], 2)
        self.assertEqual(entry["heatmap"][1][9], 100.0)

    def test_fixed_desk_in_quota_assigned_hours(self):
        Place.objects.filter(pk=self.d1.pk).update(fixed_owner=self.member)
        self.assertEqual(self.stats()["quota"]["desk"]["assigned_h"], 14)
        # Tuesday heatmap: the fixed desk is occupied all day (1 of 3).
        self.assertEqual(self.stats()["quota"]["desk"]["heatmap"][1][8], 33.3)
        # A week (Mon-Sun): 5 open days.
        monday = self.day - timedelta(days=self.day.weekday())
        week = self.stats(monday, monday + timedelta(days=6))
        self.assertEqual(week["quota"]["desk"]["assigned_h"], 70)
        # An absence covering the Tuesday removes that day.
        Absence.objects.create(
            user=self.member, start_date=self.day, end_date=self.day, kind="vacation"
        )
        week = self.stats(monday, monday + timedelta(days=6))
        self.assertEqual(week["quota"]["desk"]["assigned_h"], 56)
        self.assertEqual(week["quota"]["desk"]["heatmap"][1][8], 0.0)
        # The owner's own reservation counts like any other.
        self.d1.refresh_from_db()
        res = self.reserve(self.d1, self.member, 9, 12, checked_in_at=self.at(9, 5))
        self.assertTrue(res.owner_use)
        data = self.stats()["quota"]["desk"]
        self.assertEqual((data["booked_h"], data["checked_in_h"]), (3, 3))

    def test_no_show_and_rebooked_hours(self):
        released = self.reserve(
            self.d1, self.member, 9, 13, status=Reservation.Status.RELEASED,
            released_at=self.at(11), release_reason="no_show", no_show=True,
        )
        self.reserve(self.d1, self.other, 11, 12)  # fully inside the released part
        self.reserve(self.d1, self.other, 12, 14)  # clipped: 12-13 counts
        self.reserve(self.d2, self.other, 9, 11, checked_in_at=self.at(8, 50))
        # Released after check-in: checked in 9-10 (until release at 10:00).
        self.reserve(
            self.d3, self.member, 9, 12, status=Reservation.Status.RELEASED,
            released_at=self.at(10), release_reason="holder", checked_in_at=self.at(9),
        )
        desk = self.stats()["quota"]["desk"]
        self.assertEqual(desk["no_show_count"], 1)
        self.assertEqual(desk["no_show_h"], 4)
        self.assertEqual(desk["released_h"], 2 + 2)  # 11-13 and 10-12
        self.assertEqual(desk["rebooked_after_release_h"], 2)
        self.assertEqual(desk["booked_h"], 4 + 1 + 2 + 2 + 3)
        self.assertEqual(desk["checked_in_h"], 2 + 1)
        self.assertEqual(released.no_show, True)

    def test_stats_admin_only(self):
        assistant = User.objects.create_user("assi2", password="x")
        helpers = AccessGroup.objects.create(name="Helpers2")
        helpers.members.add(assistant)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.assistant_group = helpers
        settings_.save()
        q = {"pool": self.pool.pk, "start": self.day.isoformat(), "end": self.day.isoformat()}
        for url in ("stats/", "stats.csv"):
            self.assertEqual(self.client_for(self.lender).get(f"{API}/manage/{url}", q).status_code, 200)
            for user in (assistant, self.member):
                self.assertEqual(self.client_for(user).get(f"{API}/manage/{url}", q).status_code, 403)
            self.assertEqual(APIClient().get(f"{API}/manage/{url}", q).status_code, 403)
        # Max period: 5 years.
        q["end"] = (self.day + timedelta(days=5 * 366 + 5)).isoformat()
        self.assertEqual(self.client_for(self.lender).get(f"{API}/manage/stats/", q).status_code, 400)
        q["end"] = (self.day - timedelta(days=1)).isoformat()
        self.assertEqual(self.client_for(self.lender).get(f"{API}/manage/stats/", q).status_code, 400)

    def test_csv_rows(self):
        self.reserve(self.d1, self.member, 9, 12)
        text = stats.stats_csv(self.pool, self.day, self.day)
        lines = text.strip().splitlines()
        self.assertTrue(lines[0].startswith("group,place,booked_h"))
        self.assertTrue(any(l.startswith("desk,,3.0") or l.startswith("desk,,3,") for l in lines))
        self.assertTrue(any(l.startswith("meeting_room,") for l in lines))

    def test_performance_guard(self):
        places = Place.objects.bulk_create(
            [Place(room=self.room, name=f"P{i}") for i in range(100)]
        )
        days = [self.day + timedelta(days=d) for d in range(0, 240) if (self.day + timedelta(days=d)).weekday() < 5]
        Reservation.objects.bulk_create([
            Reservation(place=p, holder=self.member, period=hours.local_range(d, 9, 13))
            for p in places for d in days[:120]
        ])
        started = time.monotonic()
        data = stats.department_stats(self.pool, self.day, self.day + timedelta(days=365))
        elapsed = time.monotonic() - started
        self.assertEqual(data["quota"]["desk"]["booked_h"], 100 * 120 * 4)
        self.assertLess(elapsed, 3.0)
