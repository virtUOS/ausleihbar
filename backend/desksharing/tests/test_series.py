# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from desksharing import booking, cycles, hours, notify, series as series_svc
from accounts import roles
from accounts.models import AccessGroup
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, ReleaseRequest, Reservation, Series
from desksharing.tests.test_booking import API, setup_department

User = get_user_model()

# A Monday, 08:00 local; every date below is relative to it.
NOW = datetime(2027, 3, 1, 8, 0, tzinfo=hours.TZ)
TUESDAYS = [date(2027, 3, 2) + timedelta(weeks=i) for i in range(8)]


class SeriesTests(TestCase):
    def setUp(self):
        setup_department(self)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        DeskSettings.objects.filter(pool=self.pool).update(cycle_months=6)  # window end 2027-06-30

    def create(self, **kw):
        args = dict(
            actor=self.member, holder=self.member, place=self.d1, weekdays=[1],
            start_hour=9, end_hour=11, valid_from=TUESDAYS[0], valid_until=TUESDAYS[-1],
        )
        args.update(kw)
        return series_svc.create_series(**args)

    def test_creates_occurrences_up_front(self):
        result = self.create()
        self.assertEqual(result.conflicts, [])
        self.assertEqual(len(result.created), 8)
        self.assertTrue(all(r.series == result.series for r in result.created))
        self.assertEqual(
            sorted(hours.local_day_hours(r.period)[0] for r in result.created), TUESDAYS
        )

    def test_series_may_run_longer_than_three_months(self):
        result = self.create(valid_from=date(2027, 3, 2), valid_until=date(2027, 6, 29))
        self.assertEqual(result.conflicts, [])
        self.assertEqual(len(result.created), 18)

    def test_series_beyond_window_refused(self):
        window = cycles.booking_window(self.pool)
        with self.assertRaises(BookingError) as cm:
            self.create(valid_until=window.open_until + timedelta(days=1))
        self.assertEqual(cm.exception.code, "series_window")
        self.assertEqual(cm.exception.extra["open_until"], window.open_until.isoformat())
        self.assertEqual(Series.objects.count(), 0)

    def test_series_beyond_window_warns_for_assistant(self):
        assistant = User.objects.create_user("assi", password="x")
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.assistant_group = AccessGroup.objects.create(name="Assist")
        settings_.save()
        settings_.assistant_group.members.add(assistant)
        roles.invalidate_cache()
        window = cycles.booking_window(self.pool)
        warnings = []
        result = self.create(
            actor=assistant, valid_until=window.open_until + timedelta(days=14),
            warnings=warnings,
        )
        self.assertIn("series_window", warnings)
        self.assertTrue(result.created)

    def test_series_rejects_bad_input(self):
        for kw in (
            dict(weekdays=[]), dict(weekdays=[7]),
            dict(valid_from=TUESDAYS[3], valid_until=TUESDAYS[0]),
        ):
            with self.assertRaises(ValueError):
                self.create(**kw)

    def test_series_conflicts_return_alternatives(self):
        booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[2],
            start_hour=10, end_hour=12,
        )
        result = self.create()
        self.assertEqual(len(result.created), 7)
        self.assertEqual([c.day for c in result.conflicts], [TUESDAYS[2]])
        self.assertEqual(set(result.conflicts[0].alternatives), {self.d2, self.d3})

    def test_closed_days_are_skipped_silently(self):
        # Saturday is closed by default.
        result = self.create(weekdays=[5], valid_from=date(2027, 3, 1), valid_until=date(2027, 3, 31))
        self.assertEqual(result.created, [])
        self.assertEqual(result.conflicts, [])

    def test_resolve_conflict_books_alternative(self):
        booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[2],
            start_hour=9, end_hour=11,
        )
        result = self.create()
        res = series_svc.resolve_conflict(result.series, TUESDAYS[2], self.d2)
        self.assertEqual(res.place, self.d2)
        self.assertEqual(res.series, result.series)
        self.assertEqual(res.holder, self.member)

    def test_extend_to_window_end(self):
        result = self.create(valid_until=date(2027, 4, 20))
        later = datetime(2027, 6, 4, 8, 0, tzinfo=hours.TZ)  # transition from 06-03
        with mock.patch("django.utils.timezone.now", return_value=later):
            window = cycles.booking_window(self.pool)
            self.assertEqual(window.open_until, date(2027, 12, 31))
            ext = series_svc.extend_series(result.series, actor=self.member)
        result.series.refresh_from_db()
        self.assertEqual(result.series.valid_until, date(2027, 12, 31))
        days = [hours.local_day_hours(r.period)[0] for r in ext.created]
        self.assertEqual(min(days), date(2027, 6, 8))
        self.assertEqual(max(days), date(2027, 12, 28))

    def test_extend_not_open_before_window_moves(self):
        result = self.create(valid_until=date(2027, 6, 30))  # the window end
        with self.assertRaises(BookingError) as cm:
            series_svc.extend_series(result.series, actor=self.member)
        self.assertEqual(cm.exception.code, "not_allowed")
        self.assertEqual(str(cm.exception.detail), "The extension is not open yet.")

    def test_late_extension_allowed(self):
        result = self.create()
        late = datetime(2027, 5, 10, 8, 0, tzinfo=hours.TZ)  # after the end
        with mock.patch("django.utils.timezone.now", return_value=late):
            ext = series_svc.extend_series(result.series, actor=self.member)
        result.series.refresh_from_db()
        self.assertEqual(result.series.valid_until, date(2027, 6, 30))
        days = [hours.local_day_hours(r.period)[0] for r in ext.created]
        self.assertGreaterEqual(min(days), date(2027, 5, 10))

    def test_on_taken_request_creates_batch(self):
        for day in TUESDAYS[:2]:
            booking.book(
                actor=self.other, holder=self.other, places=[self.d1], day=day,
                start_hour=9, end_hour=10,
            )
        # A third date is blocked twice: never requestable.
        for hour in (9, 10):
            booking.book(
                actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[2],
                start_hour=hour, end_hour=hour + 1,
            )
        result = self.create(on_taken="request")
        self.assertEqual(len(result.created), 5)
        self.assertEqual(len(result.requests), 2)
        self.assertEqual([c.day for c in result.conflicts], [TUESDAYS[2]])
        self.assertEqual(
            {r.requester_id for r in result.requests} | {r.status for r in result.requests},
            {self.member.pk, ReleaseRequest.Status.OPEN},
        )
        self.assertEqual(len({r.batch for r in result.requests}), 1)

    def test_request_mode_keeps_already_requested_date_a_conflict(self):
        [blocker] = booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[0],
            start_hour=9, end_hour=10,
        )
        ReleaseRequest.objects.create(
            reservation=blocker, requester=self.member,
            wanted_period=hours.local_range(TUESDAYS[0], 9, 11),
        )
        result = self.create(on_taken="request")
        self.assertEqual(result.requests, [])
        self.assertEqual([c.day for c in result.conflicts], [TUESDAYS[0]])
        self.assertEqual(len(result.created), 7)

    def test_default_keeps_taken_dates_as_conflicts(self):
        booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[0],
            start_hour=9, end_hour=10,
        )
        result = self.create()
        self.assertEqual(result.requests, [])
        self.assertEqual(len(result.conflicts), 1)

    def test_reminder_text(self):
        result = self.create(valid_until=date(2027, 3, 16))
        _subject, body = notify._render_series_extension_due(
            self.member, {"series": result.series, "days": 7}
        )
        self.assertIn("You can extend it in the app:", body)
        self.assertNotIn("three months", body)

    def test_extend_forbidden_for_strangers_and_cancelled(self):
        result = self.create(valid_until=date(2027, 3, 16))
        with self.assertRaises(BookingError):
            series_svc.extend_series(result.series, actor=self.other)
        series_svc.delete_series(result.series, actor=self.member)
        with self.assertRaises(BookingError):
            series_svc.extend_series(result.series, actor=self.member)

    def test_cancel_occurrence_keeps_series(self):
        result = self.create()
        res = result.created[1]
        series_svc.cancel_occurrence(res, actor=self.member)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.CANCELLED)
        self.assertEqual(res.series, result.series)
        self.assertEqual(
            Reservation.objects.filter(series=result.series, status="active").count(), 7
        )

    def test_move_occurrence_other_room(self):
        result = self.create()
        res = result.created[0]
        series_svc.move_occurrence(res, actor=self.member, to_place=self.d3)
        res.refresh_from_db()
        self.assertEqual(res.place, self.d3)
        self.assertEqual(res.series, result.series)

    def test_move_in_progress_reservation_allowed(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=TUESDAYS[0],
            start_hour=9, end_hour=11,
        )
        running = datetime(2027, 3, 2, 10, 30, tzinfo=hours.TZ)
        with mock.patch("django.utils.timezone.now", return_value=running):
            booking.move(res, actor=self.member, to_place=self.d2)
        res.refresh_from_db()
        self.assertEqual(res.place, self.d2)

    def test_move_checks_booking_horizon(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=TUESDAYS[-1],
            start_hour=9, end_hour=11,
        )
        self.pool.max_booking_months = 1  # shrunk after the booking was made
        self.pool.save()
        with self.assertRaises(BookingError) as cm:
            booking.move(res, actor=self.member, to_place=self.d2)
        self.assertEqual(cm.exception.code, "horizon")

    def test_multiple_weekdays(self):
        result = self.create(weekdays=[0, 2, 4], valid_from=date(2027, 3, 1), valid_until=date(2027, 3, 14))
        days = sorted(hours.local_day_hours(r.period)[0] for r in result.created)
        self.assertEqual(len(days), 6)
        self.assertEqual(days[0], date(2027, 3, 1))
        self.assertEqual(days[-1], date(2027, 3, 12))

    def test_hours_outside_business_hours_fail_creation(self):
        settings_ = self.pool.desk_settings
        settings_.business_hours = {str(d): ([8, 16] if d < 5 else None) for d in range(7)}
        settings_.save()
        with self.assertRaises(BookingError) as cm:
            self.create(start_hour=17, end_hour=19)
        self.assertEqual(cm.exception.code, "outside_hours")
        self.assertEqual(Series.objects.count(), 0)
        with self.assertRaises(BookingError):
            self.create(start_hour=4, end_hour=8)

    def test_second_extend_sees_new_end(self):
        result = self.create()
        stale = Series.objects.get(pk=result.series.pk)
        with mock.patch(
            "django.utils.timezone.now",
            return_value=datetime(2027, 6, 4, 8, 0, tzinfo=hours.TZ),
        ):
            series_svc.extend_series(result.series, actor=self.member)
            with self.assertRaises(BookingError):  # window end reached
                series_svc.extend_series(stale, actor=self.member)
        stale.refresh_from_db()
        self.assertEqual(stale.valid_until, date(2027, 12, 31))

    def test_admin_delete_needs_reason(self):
        result = self.create(valid_until=date(2027, 3, 16))
        with self.assertRaises(BookingError) as cm:
            series_svc.delete_series(result.series, actor=self.lender)
        self.assertEqual(cm.exception.code, "reason_required")
        series_svc.delete_series(result.series, actor=self.lender, reason="Room closed")
        self.assertEqual(
            Reservation.objects.filter(series=result.series, status="active").count(), 0
        )

    def test_assistant_cannot_manage_series(self):
        result = self.create()
        settings_ = self.pool.desk_settings
        settings_.assistant_group = self.group
        settings_.enabled = True
        settings_.save()
        with self.assertRaises(BookingError):
            series_svc.delete_series(result.series, actor=self.other)

    def test_delete_series_keeps_past(self):
        result = self.create()
        after_two = datetime(2027, 3, 10, 8, 0, tzinfo=hours.TZ)  # Tue 9 Mar passed
        with mock.patch("django.utils.timezone.now", return_value=after_two):
            series_svc.delete_series(result.series, actor=self.member)
        active = Reservation.objects.filter(series=result.series, status="active")
        self.assertEqual(
            sorted(hours.local_day_hours(r.period)[0] for r in active), TUESDAYS[:2]
        )
        result.series.refresh_from_db()
        self.assertIsNotNone(result.series.cancelled_at)


class SeriesApiTests(TestCase):
    def setUp(self):
        setup_department(self)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        DeskSettings.objects.filter(pool=self.pool).update(cycle_months=6)  # window end 2027-06-30
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def payload(self, **kw):
        data = dict(
            place_id=self.d1.pk, weekdays=[1], start_hour=9, end_hour=11,
            valid_from="2027-03-02", valid_until="2027-04-27",
        )
        data.update(kw)
        return data

    def test_create_mine_resolve_delete(self):
        booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[1],
            start_hour=9, end_hour=10,
        )
        resp = self.client.post(f"{API}/series/", self.payload(), format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.data["created"]), 8)  # 9 Tuesdays, one taken
        self.assertEqual(len(resp.data["conflicts"]), 1)
        conflict = resp.data["conflicts"][0]
        self.assertEqual(conflict["day"], TUESDAYS[1].isoformat())
        alt = conflict["alternatives"][0]["id"]
        sid = resp.data["series"]["id"]

        mine = self.client.get(f"{API}/series/mine/")
        self.assertEqual([s["id"] for s in mine.data], [sid])

        resp = self.client.post(
            f"{API}/series/{sid}/resolve/",
            {"day": TUESDAYS[1].isoformat(), "place_id": alt}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        resp = self.client.delete(f"{API}/series/{sid}/")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(
            Reservation.objects.filter(series_id=sid, status="active").count(), 0
        )
        self.assertEqual(self.client.get(f"{API}/series/mine/").data, [])

    def test_beyond_window_is_409_and_extend_early_is_409(self):
        resp = self.client.post(
            f"{API}/series/", self.payload(valid_until="2027-07-01"), format="json"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "series_window")
        sid = self.client.post(
            f"{API}/series/", self.payload(valid_until="2027-06-30"), format="json"
        ).data["series"]["id"]
        resp = self.client.post(f"{API}/series/{sid}/extend/")
        self.assertEqual(resp.status_code, 409)

    def test_create_with_on_taken_request_returns_requests(self):
        booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=TUESDAYS[1],
            start_hour=9, end_hour=10,
        )
        resp = self.client.post(
            f"{API}/series/", self.payload(on_taken="request"), format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["conflicts"], [])
        self.assertEqual(len(resp.data["requests"]), 1)

    def test_other_user_cannot_touch(self):
        sid = self.client.post(f"{API}/series/", self.payload(), format="json").data["series"]["id"]
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(other.delete(f"{API}/series/{sid}/").status_code, 404)

    def test_admin_delete_over_api_and_bad_hours(self):
        sid = self.client.post(f"{API}/series/", self.payload(), format="json").data["series"]["id"]
        admin = APIClient()
        admin.force_authenticate(self.lender)
        resp = admin.delete(f"{API}/series/{sid}/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "reason_required")
        resp = admin.delete(f"{API}/series/{sid}/?reason=Closed")
        self.assertEqual(resp.status_code, 204)
        for kw in (dict(start_hour=4), dict(end_hour=22), dict(start_hour=11, end_hour=9)):
            resp = self.client.post(f"{API}/series/", self.payload(**kw), format="json")
            self.assertEqual(resp.status_code, 400, kw)
        resp = self.client.post(
            f"{API}/series/", self.payload(start_hour=19, end_hour=20, weekdays=[5]), format="json"
        )  # Saturday: closed, nothing to book
        self.assertEqual(resp.status_code, 201)


class SeriesOpenConflictsTests(TestCase):
    def setUp(self):
        setup_department(self)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        DeskSettings.objects.filter(pool=self.pool).update(cycle_months=6)  # window end 2027-06-30
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def make(self, **kw):
        args = dict(
            actor=self.member, holder=self.member, place=self.d1, weekdays=[1],
            start_hour=9, end_hour=11, valid_from=TUESDAYS[0], valid_until=TUESDAYS[-1],
        )
        args.update(kw)
        return series_svc.create_series(**args).series

    def block_d1(self, day):
        booking.book(
            actor=self.other, holder=self.other, places=[self.d1], day=day,
            start_hour=9, end_hour=10,
        )

    def days(self, series):
        resp = self.client.get(f"{API}/series/{series.pk}/conflicts/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.data

    def test_missing_date_listed_with_alternatives_and_resolved_not(self):
        self.block_d1(TUESDAYS[2])
        series = self.make()
        rows = self.days(series)
        self.assertEqual([r["day"] for r in rows], [TUESDAYS[2].isoformat()])
        self.assertTrue(rows[0]["alternatives"])
        series_svc.resolve_conflict(series, TUESDAYS[2], self.d2, actor=self.member)
        self.assertEqual(self.days(series), [])

    def test_cancelled_occurrence_is_not_a_conflict(self):
        series = self.make()
        res = series.reservations.first()
        booking.cancel(res, actor=self.member)
        self.assertEqual(self.days(series), [])

    def test_closed_day_not_listed(self):
        from lending.models import Block

        self.block_d1(TUESDAYS[3])
        series = self.make()
        self.assertEqual(len(self.days(series)), 1)
        Block.objects.create(
            period=hours.local_range(TUESDAYS[3], 6, 20), reason="Closed",
        )
        self.assertEqual(self.days(series), [])

    def test_past_dates_not_listed(self):
        series = self.make(valid_from=TUESDAYS[0], valid_until=TUESDAYS[3])
        # Nothing is missing; a past, never-booked date must not appear either.
        Reservation.objects.filter(series=series).delete()
        with mock.patch(
            "django.utils.timezone.now",
            return_value=datetime(2027, 3, 17, 8, 0, tzinfo=hours.TZ),
        ):
            rows = self.days(series)
        self.assertEqual([r["day"] for r in rows], [TUESDAYS[3].isoformat()])

    def test_other_user_gets_404(self):
        series = self.make()
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(other.get(f"{API}/series/{series.pk}/conflicts/").status_code, 404)
