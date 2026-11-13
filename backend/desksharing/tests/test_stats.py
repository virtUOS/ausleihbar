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
from lending.models import Block

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
        owner_places = Place.objects.bulk_create(
            [Place(room=self.room, name=f"F{i}", fixed_owner=self.member) for i in range(10)]
        )
        specials = Place.objects.bulk_create(
            [Place(room=self.room, name=f"S{i}", is_special=True) for i in range(5)]
        )
        places = Place.objects.bulk_create(
            [Place(room=self.room, name=f"P{i}") for i in range(100)]
        )
        days = [self.day + timedelta(days=d) for d in range(0, 240) if (self.day + timedelta(days=d)).weekday() < 5]
        Reservation.objects.bulk_create([
            Reservation(place=p, holder=self.member, period=hours.local_range(d, 9, 13))
            for p in places for d in days[:120]
        ])
        Reservation.objects.bulk_create([
            Reservation(
                place=p, holder=self.other, period=hours.local_range(d, 14, 18),
                status=Reservation.Status.RELEASED, released_at=hours.local_dt(d, 16),
                release_reason="holder",
            )
            for p in places[:50] + specials for d in days[:60]
        ])
        Reservation.objects.bulk_create([
            Reservation(place=p, holder=self.member, period=hours.local_range(d, 6, 7))
            for p in owner_places + specials for d in days[:100]
        ])
        started = time.monotonic()
        data = stats.department_stats(self.pool, self.day, self.day + timedelta(days=365))
        elapsed = time.monotonic() - started
        self.assertEqual(
            data["quota"]["desk"]["booked_h"], 100 * 120 * 4 + 50 * 60 * 4 + 10 * 100
        )
        self.assertEqual(len(data["special"]), 5)
        self.assertLess(elapsed, 1.5)


class StatsEdgeCaseTests(StatsBase):
    def block(self, day, start=0, end=24):
        return Block.objects.create(period=hours.local_range(day, start, end))

    def test_released_before_start(self):
        self.reserve(
            self.d1, self.member, 9, 12, status=Reservation.Status.RELEASED,
            released_at=self.at(7), release_reason="holder",
        )
        desk = self.stats()["quota"]["desk"]
        self.assertEqual((desk["released_h"], desk["booked_h"], desk["checked_in_h"]), (3, 3, 0))

    def test_block_on_day_with_reservations(self):
        self.reserve(self.d1, self.member, 9, 12)
        self.reserve(self.d2, self.member, 9, 10)
        self.block(self.day)  # holiday set after the bookings were made
        desk = self.stats()["quota"]["desk"]
        self.assertEqual(desk["booked_h"], 4)
        heat = desk["heatmap"][1]
        self.assertEqual(heat[9], 66.7)  # 2 of 3, still available (occupied)
        self.assertEqual(heat[10], 33.3)
        self.assertNotIn(14, heat)  # blocked and empty: not available
        for pct in heat.values():
            self.assertLessEqual(pct, 100.0)
        # A second, empty Tuesday with the same block: the denominator excludes it.
        week2 = self.day + timedelta(days=7)
        both = self.stats(self.day, week2)["quota"]["desk"]["heatmap"][1]
        self.assertEqual(both[9], 33.3)  # 2 occupied of 3 + 3 (day 2 open)
        self.assertEqual(both[14], 0.0)  # open second Tuesday only

    def test_block_effect_on_assigned_hours(self):
        Place.objects.filter(pk=self.d1.pk).update(fixed_owner=self.member)
        self.block(self.day, 6, 12)
        desk = self.stats()["quota"]["desk"]
        self.assertEqual(desk["assigned_h"], 8)
        self.assertNotIn(8, desk["heatmap"][1])
        self.assertEqual(desk["heatmap"][1][13], 33.3)

    def test_business_hours_change(self):
        self.reserve(self.d1, self.member, 7, 9)
        settings_ = DeskSettings.for_pool(self.pool)
        hrs = dict(settings_.business_hours)
        hrs["1"] = [10, 18]
        settings_.business_hours = hrs
        settings_.save()
        heat = self.stats()["quota"]["desk"]["heatmap"][1]
        self.assertEqual(heat[7], 33.3)
        self.assertEqual(heat[10], 0.0)
        self.assertNotIn(9, heat)  # closed and empty
        self.assertTrue(all(v <= 100 for v in heat.values()))

    def test_dst_change_day_same_as_normal_day(self):
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.business_hours = {str(d): [6, 20] for d in range(7)}
        settings_.save()
        from datetime import date
        dst, normal = date(2027, 3, 28), date(2027, 3, 30)
        figures = []
        for day in (dst, normal):
            self.reserve(self.d1, self.member, 9, 17, day=day, checked_in_at=self.at(9, day=day))
            figures.append(self.stats(day, day)["quota"]["desk"])
        for key in stats.FIGURE_KEYS:
            self.assertEqual(figures[0][key], figures[1][key], key)
        self.assertEqual(figures[0]["booked_h"], 8)
        self.assertEqual(figures[0]["checked_in_h"], 8)
        self.assertEqual(
            list(figures[0]["heatmap"][6].values()), list(figures[1]["heatmap"][1].values())
        )

    def test_pool_param_cannot_bypass_permission(self):
        for url in ("stats/", "stats.csv"):
            q = {"pool": f"{self.pool.pk}.0", "start": self.day.isoformat(), "end": self.day.isoformat()}
            self.assertEqual(self.client_for(self.member).get(f"{API}/manage/{url}", q).status_code, 403)
            q["pool"] = self.pool.pk
            self.assertEqual(self.client_for(self.member).get(f"{API}/manage/{url}", q).status_code, 403)
            q["pool"] = f"{self.pool.pk}.0"
            self.assertEqual(self.client_for(self.lender).get(f"{API}/manage/{url}", q).status_code, 200)

    def test_csv_neutralizes_tab_and_cr(self):
        self.assertEqual(stats._safe("\tx"), "'\tx")
        self.assertEqual(stats._safe("\rx"), "'\rx")
