# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts import roles
from accounts.models import AccessGroup
from desksharing import booking, cycles, hours, privacy
from desksharing import series as series_svc
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, ReleaseRequest, Reservation, Series
from desksharing.serializers import DeskSettingsSerializer
from desksharing.tests.test_booking import setup_department
from desksharing.tests.test_rights import make_pool

User = get_user_model()


class WindowTests(TestCase):
    def setUp(self):
        self.pool = make_pool("Cycles", enabled=False)

    def window(self, today, **settings):
        DeskSettings.objects.filter(pool=self.pool).update(**settings)
        return cycles.booking_window(self.pool, today=today)

    def test_quarter_before_transition(self):
        w = self.window(date(2026, 11, 17))
        self.assertEqual((w.cycle_end, w.transition_from, w.open_until),
                         (date(2026, 12, 31), date(2026, 12, 4), date(2026, 12, 31)))
        self.assertEqual(w.next_cycle_end, date(2027, 3, 31))

    def test_transition_starts_on_its_first_day_and_crosses_the_year(self):
        self.assertEqual(self.window(date(2026, 12, 3)).open_until, date(2026, 12, 31))
        self.assertEqual(self.window(date(2026, 12, 4)).open_until, date(2027, 3, 31))
        self.assertEqual(self.window(date(2026, 12, 31)).open_until, date(2027, 3, 31))

    def test_yearly_cycle(self):
        w = self.window(date(2026, 12, 10), cycle_months=12)
        self.assertEqual((w.cycle_end, w.open_until), (date(2026, 12, 31), date(2027, 12, 31)))

    def test_monthly_cycle_without_transition(self):
        w = self.window(date(2026, 2, 28), cycle_months=1, transition_weeks=0)
        self.assertEqual(w.open_until, date(2026, 2, 28))

    def test_advance_until_respects_pool_horizon(self):
        self.assertEqual(self.window(date(2026, 11, 17)).advance_until, date(2027, 11, 17))
        self.pool.max_booking_months = 6
        self.pool.save()
        self.assertEqual(self.window(date(2026, 11, 17)).advance_until, date(2027, 5, 17))

    def test_no_pool_horizon_uses_advance_months_only(self):
        self.pool.max_booking_months = 0
        self.pool.save()
        self.assertEqual(self.window(date(2026, 11, 17)).advance_until, date(2027, 11, 17))

    def test_settings_validation(self):
        # serializer: transition must be shorter than a cycle; advance >= cycle
        for bad, field in (({"cycle_months": 1, "transition_weeks": 4}, "transition_weeks"),
                           ({"cycle_months": 6, "advance_months": 3}, "advance_months"),
                           ({"cycle_months": 5}, "cycle_months")):
            ser = DeskSettingsSerializer(DeskSettings.for_pool(self.pool), data=bad, partial=True)
            self.assertFalse(ser.is_valid(), bad)
            self.assertIn(field, ser.errors, bad)

    def test_settings_valid(self):
        ser = DeskSettingsSerializer(
            DeskSettings.for_pool(self.pool), data={"cycle_months": 6}, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)


class LimitTests(TestCase):
    def setUp(self):
        setup_department(self)
        # "Today" is frozen to the real Berlin day, so the engine's own
        # past/horizon checks (real clock) stay consistent.
        self.today = cycles.today()
        patcher = mock.patch("desksharing.cycles.today", return_value=self.today)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.advance_days = 2
        settings_.advance_places = 2
        settings_.assistant_group = AccessGroup.objects.create(name="Assist")
        settings_.save()
        self.assistant = User.objects.create_user("assist", password="x")
        settings_.assistant_group.members.add(self.assistant)
        roles.invalidate_cache()
        self.window = cycles.booking_window(self.pool)
        # Open weekdays (Tuesdays) after / before the window's end.
        self.inside = self.tuesday_after(self.today)
        self.beyond = [self.tuesday_after(self.window.open_until) + timedelta(weeks=i) for i in range(4)]

    @staticmethod
    def tuesday_after(day):
        day += timedelta(days=1)
        return day + timedelta(days=(1 - day.weekday()) % 7)

    def book(self, places, day, holder=None, actor=None, **kw):
        holder = holder or self.member
        return booking.book(
            actor=actor or holder, holder=holder, places=places, day=day,
            start_hour=9, end_hour=10, **kw,
        )

    def test_patching_today_takes_effect(self):
        with mock.patch("desksharing.cycles.today", return_value=date(2026, 3, 1)):
            self.assertEqual(cycles.booking_window(self.pool).today, date(2026, 3, 1))

    def test_inside_window_unlimited(self):
        self.assertLessEqual(self.inside, self.window.open_until)
        res = self.book([self.d1, self.d2, self.d3], self.inside)
        self.assertEqual(len(res), 3)

    def test_days_beyond_window_limited(self):
        self.book([self.d1], self.beyond[0])
        self.book([self.d1], self.beyond[1])
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1], self.beyond[2])
        self.assertEqual(cm.exception.code, "advance_days")
        self.assertEqual(cm.exception.extra["limit"], 2)
        self.assertEqual(cm.exception.extra["open_until"], self.window.open_until.isoformat())

    def test_second_place_same_day_counts_places_not_days(self):
        self.book([self.d1], self.beyond[0])
        self.book([self.d2], self.beyond[0])
        self.book([self.d1], self.beyond[1])  # still within the 2 quota days
        with self.assertRaises(BookingError) as cm:
            self.book([self.d3], self.beyond[0])
        self.assertEqual(cm.exception.code, "advance_places")
        self.assertEqual(cm.exception.extra["limit"], 2)
        self.assertEqual(cm.exception.extra["day"], self.beyond[0].isoformat())

    def test_cancelled_frees_quota(self):
        [first] = self.book([self.d1], self.beyond[0])
        self.book([self.d1], self.beyond[1])
        booking.cancel(first, actor=self.member)
        self.book([self.d1], self.beyond[2])

    def test_existing_beyond_window_count(self):
        for day in self.beyond[:2]:
            Reservation.objects.create(
                place=self.d1, holder=self.member, booked_by=self.member,
                period=hours.local_range(day, 9, 10),
            )
        with self.assertRaises(BookingError) as cm:
            self.book([self.d2], self.beyond[2])
        self.assertEqual(cm.exception.code, "advance_days")

    def test_other_pools_and_holders_do_not_count(self):
        self.book([self.d1], self.beyond[0], holder=self.other)
        self.book([self.d1], self.beyond[1], holder=self.other)
        self.book([self.d2], self.beyond[2])

    def post(self, user, **extra):
        client = APIClient()
        client.force_authenticate(user)
        body = {
            "place_ids": [self.d1.pk], "day": self.beyond[2].isoformat(),
            "start_hour": 9, "end_hour": 10, **extra,
        }
        return client.post("/api/desks/reservations/", body, format="json")

    def fill_quota(self, holder, actor):
        for day in self.beyond[:2]:
            self.book([self.d2], day, holder=holder, actor=actor)

    def test_assistant_for_other_gets_warning(self):
        self.fill_quota(self.other, self.assistant)
        resp = self.post(self.assistant, holder_id=self.other.pk)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn("advance_days", resp.json()["warnings"])

    def test_assistant_requests_for_member_from_requester_perspective(self):
        self.fill_quota(self.other, self.assistant)
        self.book([self.d1], self.beyond[2], holder=self.member)
        client = APIClient()
        client.force_authenticate(self.assistant)
        resp = client.post(
            "/api/desks/reservations/days/",
            {"place_ids": [self.d1.pk], "days": [self.beyond[2].isoformat()],
             "start_hour": 9, "end_hour": 10, "holder_id": self.other.pk,
             "on_taken": "request"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("advance_days", body["warnings"])
        [req] = body["requests"]
        self.assertIn("other", req)
        self.assertIn("other_holder_name", req)
        self.assertNotIn("own", req)
        self.assertEqual(ReleaseRequest.objects.get(pk=req["id"]).requester, self.other)

    def test_assistant_for_self_refused(self):
        self.group.members.add(self.assistant)
        self.fill_quota(self.assistant, self.assistant)
        resp = self.post(self.assistant)
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "advance_days")
        self.assertEqual(body["limit"], 2)

    def test_horizon_never_waived(self):
        far = self.window.advance_until + timedelta(days=7)
        far += timedelta(days=(1 - far.weekday()) % 7)
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1], far, holder=self.other, actor=self.assistant)
        self.assertEqual(cm.exception.code, "horizon")

    def test_series_occurrence_limit_not_turned_into_conflict(self):
        self.fill_quota(self.member, self.member)
        series = Series.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member, weekdays=[1],
            start_hour=9, end_hour=10, valid_from=self.beyond[2], valid_until=self.beyond[3],
        )
        with self.assertRaises(BookingError) as cm:
            series_svc._book_days(series, self.beyond[2], self.beyond[3], self.member)
        self.assertEqual(cm.exception.code, "advance_days")

    def test_hours_max_day_is_advance_until(self):
        client = APIClient()
        client.force_authenticate(self.member)
        resp = client.get(f"/api/desks/hours/?pool={self.pool.pk}&day={self.inside.isoformat()}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["max_day"], self.window.advance_until.isoformat())


class WindowViewTests(TestCase):
    def setUp(self):
        setup_department(self)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.advance_days = 3
        settings_.assistant_group = AccessGroup.objects.create(name="Assist")
        settings_.save()
        self.assistant = User.objects.create_user("assist", password="x")
        settings_.assistant_group.members.add(self.assistant)
        self.group.members.add(self.assistant)
        self.outsider = User.objects.create_user("outsider", password="x")
        roles.invalidate_cache()
        self.window = cycles.booking_window(self.pool)
        day = self.window.open_until + timedelta(days=1)
        self.tuesday = day + timedelta(days=(1 - day.weekday()) % 7)
        self.client = APIClient()

    def get(self, url, user=None, **params):
        self.client.force_authenticate(user or self.member)
        resp = self.client.get(url, params)
        self.assertNotIn("holder", resp.content.decode(), url)
        return resp

    def reserve(self, place, holder, day, start=9, end=10):
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder, period=hours.local_range(day, start, end)
        )

    def test_window_shape_and_quota(self):
        self.reserve(self.d1, self.member, self.tuesday)
        self.reserve(self.d2, self.member, self.tuesday)
        resp = self.get("/api/desks/window/", pool=self.pool.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        w = self.window
        self.assertEqual(resp.json(), {
            "today": w.today.isoformat(), "open_until": w.open_until.isoformat(),
            "transition_from": w.transition_from.isoformat(),
            "next_open_until": w.next_cycle_end.isoformat(),
            "advance_until": w.advance_until.isoformat(), "advance_days": 3,
            "advance_places": w.advance_places, "advance_days_used": 1, "advance_days_left": 2,
        })

    def test_window_access(self):
        self.assertEqual(self.get("/api/desks/window/", self.outsider, pool=self.pool.pk).status_code, 404)
        self.assertEqual(APIClient().get("/api/desks/window/", {"pool": self.pool.pk}).status_code, 403)

    def test_holder_only_for_assistants(self):
        self.reserve(self.d1, self.other, self.tuesday)
        url = "/api/desks/window/"
        self.assertEqual(self.get(url, self.member, pool=self.pool.pk, holder=self.other.pk).status_code, 403)
        self.assertEqual(self.get(url, self.member, pool=self.pool.pk, holder=self.member.pk).status_code, 200)
        resp = self.get(url, self.assistant, pool=self.pool.pk, holder=self.other.pk)
        self.assertEqual(resp.json()["advance_days_used"], 1)
        self.assertEqual(self.get(url, self.assistant, pool=self.pool.pk, holder=99999).status_code, 404)

    def test_place_days(self):
        self.reserve(self.d1, self.other, self.tuesday, 9, 11)
        self.reserve(self.d1, self.member, self.tuesday, 13, 14)  # own: not "taken"
        sunday = self.tuesday + timedelta(days=5)
        resp = self.get(
            f"/api/desks/places/{self.d1.pk}/days/", **{"from": self.tuesday.isoformat(), "to": sunday.isoformat()}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = resp.json()
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], {"day": self.tuesday.isoformat(), "closed": False, "taken": [9, 10]})
        self.assertEqual(rows[1]["taken"], [])
        self.assertTrue(rows[-1]["closed"] or rows[-2]["closed"])  # weekend

    def test_place_days_fixed_for_someone_else_and_absence(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        url = f"/api/desks/places/{self.d1.pk}/days/"
        span = {"from": self.tuesday.isoformat(), "to": self.tuesday.isoformat()}
        row = self.get(url, **span).json()[0]
        self.assertEqual(row["taken"], list(range(6, 20)))
        from desksharing.models import Absence
        Absence.objects.create(user=self.other, start_date=self.tuesday, end_date=self.tuesday)
        self.assertEqual(self.get(url, **span).json()[0]["taken"], [])
        self.assertEqual(self.get(url, self.other, **span).json()[0]["taken"], [])

    def test_place_days_access_and_limits(self):
        url = f"/api/desks/places/{self.d1.pk}/days/"
        span = {"from": self.tuesday.isoformat(), "to": self.tuesday.isoformat()}
        self.assertEqual(self.get(url, self.outsider, **span).status_code, 404)
        self.assertEqual(APIClient().get(url, span).status_code, 403)
        far = {"from": self.tuesday.isoformat(), "to": (self.tuesday + timedelta(days=401)).isoformat()}
        self.assertEqual(self.get(url, **far).status_code, 400)
        self.assertEqual(self.get(url, from_="x").status_code, 400)

    def test_availability(self):
        day2 = self.tuesday + timedelta(days=7)
        day3 = self.tuesday + timedelta(days=14)
        self.reserve(self.d1, self.other, self.tuesday, 10, 11)     # taken (requestable)
        self.reserve(self.d2, self.other, self.tuesday, 9, 10)
        self.reserve(self.d2, self.assistant, self.tuesday, 10, 11)  # two overlaps: unavailable
        self.reserve(self.d3, self.member, day2, 10, 11)            # own: unavailable
        sat = self.tuesday + timedelta(days=4)                      # closed weekend
        days = ",".join(d.isoformat() for d in (self.tuesday, day2, day3, sat))
        resp = self.get("/api/desks/availability/", pool=self.pool.pk, kind="desk",
                        days=days, start_hour=9, end_hour=11)
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = {r["name"]: r for r in resp.json()}
        self.assertEqual(set(rows), {"D1", "D2", "D3"})
        self.assertEqual(rows["D1"]["taken_days"], [self.tuesday.isoformat()])
        self.assertEqual(rows["D1"]["unavailable_days"], [sat.isoformat()])
        self.assertEqual(rows["D2"]["taken_days"], [])
        self.assertEqual(rows["D2"]["unavailable_days"], sorted([self.tuesday.isoformat(), sat.isoformat()]))
        self.assertEqual(rows["D3"]["unavailable_days"], sorted([day2.isoformat(), sat.isoformat()]))
        self.assertEqual(set(rows["D1"]), {
            "id", "name", "floor_id", "room", "where", "features", "taken_days", "unavailable_days",
            "people_visible"})
        self.assertEqual(rows["D1"]["room"], "R1")

    def test_holder_param_does_not_tell_own_reservations_apart(self):
        # The holder's own reservation looks like anybody else's to an
        # assistant (it would reveal where an opted-out person sits).
        privacy.set_hide_name(self.other, True)
        self.reserve(self.d1, self.other, self.tuesday, 9, 10)
        self.reserve(self.d2, self.other, self.tuesday, 9, 10)
        self.reserve(self.d2, self.member, self.tuesday, 10, 11)
        days = self.tuesday.isoformat()
        rows = {r["name"]: r for r in self.get(
            "/api/desks/availability/", self.assistant, pool=self.pool.pk, kind="desk",
            days=days, start_hour=9, end_hour=11, holder=self.other.pk).json()}
        self.assertEqual(rows["D1"]["taken_days"], [days])
        self.assertEqual(rows["D1"]["unavailable_days"], [])
        self.assertEqual(rows["D2"]["unavailable_days"], [days])
        # The holder's own view still marks them as their own (unavailable).
        rows = {r["name"]: r for r in self.get(
            "/api/desks/availability/", self.other, pool=self.pool.pk, kind="desk",
            days=days, start_hour=9, end_hour=11).json()}
        self.assertEqual(rows["D1"]["unavailable_days"], [days])
        url = f"/api/desks/places/{self.d1.pk}/days/"
        span = {"from": days, "to": days}
        self.assertEqual(
            self.get(url, self.assistant, holder=self.other.pk, **span).json()[0]["taken"], [9]
        )
        self.assertEqual(self.get(url, self.other, **span).json()[0]["taken"], [])

    def test_holder_param_requires_a_member(self):
        days = self.tuesday.isoformat()
        for url, params in (
            ("/api/desks/window/", {"pool": self.pool.pk}),
            ("/api/desks/availability/", {"pool": self.pool.pk, "kind": "desk", "days": days,
                                          "start_hour": 9, "end_hour": 10}),
            (f"/api/desks/places/{self.d1.pk}/days/", {"from": days, "to": days}),
        ):
            resp = self.get(url, self.assistant, holder=self.outsider.pk, **params)
            self.assertEqual(resp.status_code, 404, url)

    def queries_for_availability(self, days):
        # Constant: independent of the number of days.
        self.get("/api/desks/availability/", pool=self.pool.pk, kind="desk",
                 days=days, start_hour=9, end_hour=10)  # warm per-process caches
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.get("/api/desks/availability/", pool=self.pool.pk, kind="desk",
                     days=days, start_hour=9, end_hour=10)
        return len(ctx)

    def test_availability_query_count_constant(self):
        def count(n):
            days = ",".join((self.tuesday + timedelta(days=i)).isoformat() for i in range(n))
            return self.queries_for_availability(days)
        self.assertEqual(count(2), count(60))

    def test_availability_fixed_and_rules(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        days = self.tuesday.isoformat()
        rows = {r["name"]: r for r in self.get(
            "/api/desks/availability/", pool=self.pool.pk, kind="desk", days=days,
            start_hour=9, end_hour=10).json()}
        self.assertEqual(rows["D1"]["unavailable_days"], [days])
        # On the holder's behalf their own fixed place still counts as assigned
        # (an assistant must not learn which one it is).
        rows = self.get("/api/desks/availability/", self.assistant, pool=self.pool.pk, kind="desk",
                        days=days, start_hour=9, end_hour=10, holder=self.other.pk).json()
        self.assertEqual({r["name"]: r["unavailable_days"] for r in rows}["D1"], [days])
        self.assertEqual(self.get("/api/desks/availability/", self.member, pool=self.pool.pk, kind="desk",
                                  days=days, start_hour=9, end_hour=10, holder=self.other.pk).status_code, 403)
        self.assertEqual(self.get("/api/desks/availability/", self.outsider, pool=self.pool.pk, kind="desk",
                                  days=days, start_hour=9, end_hour=10).status_code, 404)
        self.assertEqual(APIClient().get("/api/desks/availability/").status_code, 403)

    def test_availability_validation(self):
        base = {"pool": self.pool.pk, "kind": "desk", "days": self.tuesday.isoformat(),
                "start_hour": 9, "end_hour": 10}
        for change in ({"kind": "x"}, {"start_hour": 10, "end_hour": 9}, {"end_hour": 21},
                       {"days": ""}, {"days": "nope"}, {"start_hour": "a"}):
            resp = self.get("/api/desks/availability/", **{**base, **change})
            self.assertEqual(resp.status_code, 400, change)
        many = ",".join((self.tuesday + timedelta(days=i)).isoformat() for i in range(367))
        self.assertEqual(self.get("/api/desks/availability/", **{**base, "days": many}).status_code, 400)
