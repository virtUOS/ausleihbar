# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts import roles
from accounts.models import AccessGroup
from desksharing import booking, cycles, hours
from desksharing import series as series_svc
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, Reservation, Series
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
