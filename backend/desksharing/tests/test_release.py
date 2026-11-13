# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from desksharing import hours, release
from desksharing.models import DeskSettings, Place, Reservation
from desksharing.tests.test_booking import setup_department

DAY = date(2027, 3, 2)  # a Tuesday


def at(hour, minute=0):
    return datetime(2027, 3, 2, hour, minute, tzinfo=hours.TZ)


class ReleaseTests(TestCase):
    def setUp(self):
        setup_department(self)
        patcher = mock.patch("desksharing.notify.notify")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def reserve(self, place, start=9, end=12, holder=None, **kw):
        holder = holder or self.member
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(DAY, start, end), **kw,
        )

    def events(self, event):
        return [c for c in self.notify.call_args_list if c.args[1] == event]

    # free_count / is_scarce

    def test_free_count(self):
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9, 30)), 3)
        self.reserve(self.d1)
        self.reserve(self.d2, start=10, end=11)
        self.reserve(self.d3, status=Reservation.Status.RELEASED)
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9, 30)), 2)
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(10, 30)), 1)
        # Inactive places do not count.
        self.d3.is_active = False
        self.d3.save()
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9, 30)), 1)

    def test_fixed_place_counts_taken_unless_owner_absent(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9)), 2)
        with mock.patch("desksharing.absences.fixed_place_available", return_value=True) as m:
            self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9, 30)), 3)
        self.assertEqual(m.call_args.args[1], hours.local_range(DAY, 9, 10))

    def test_rooms_and_desks_counted_separately(self):
        res = self.reserve(self.m1)
        self.assertEqual(release.free_count(self.pool, Place.Kind.MEETING_ROOM, at(9)), 0)
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9)), 3)
        self.assertTrue(release.is_scarce(self.pool, Place.Kind.MEETING_ROOM, at(9)))
        self.assertFalse(release.is_scarce(self.pool, Place.Kind.DESK, at(9)))
        # The meeting room uses the room_* settings.
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.room_grace_short_min = 30
        settings_.save()
        self.assertEqual(release.tick(at(9, 20)).released, 0)
        self.assertEqual(release.tick(at(9, 30)).released, 1)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)

    # tick

    def test_plenty_marks_potentially_free_only(self):
        res = self.reserve(self.d1)
        self.assertEqual(release.tick(at(9, 30)), release.TickResult(released=0, marked=0))
        result = release.tick(at(10))
        self.assertEqual(result, release.TickResult(released=0, marked=1))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertEqual(res.potentially_free_at, at(10))
        self.assertTrue(res.no_show)
        [nudge] = self.events("grace_nudge")
        self.assertEqual(nudge.args[0], self.member)
        self.assertEqual(nudge.args[2]["reservation"].pk, res.pk)

    def test_scarce_releases_after_short_grace(self):
        res = self.reserve(self.d1)
        self.reserve(self.d2, holder=self.other, checked_in_at=at(9))
        self.assertEqual(release.tick(at(9, 14)).released, 0)
        self.assertEqual(release.tick(at(9, 15)), release.TickResult(released=1, marked=0))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.released_at, at(9, 15))
        self.assertEqual(res.release_reason, Reservation.ReleaseReason.NO_SHOW)
        self.assertTrue(res.no_show)
        self.assertEqual(res.period, hours.local_range(DAY, 9, 12))
        [mail] = self.events("released_no_show")
        self.assertEqual(mail.args[0], self.member)
        self.assertEqual(mail.args[2]["reservation"].pk, res.pk)
        # Free for the rest of the reservation, the released place excluded.
        self.assertEqual([p.pk for p in mail.args[2]["alternatives"]], [self.d3.pk])
        # The place is bookable again.
        self.assertEqual(release.free_count(self.pool, Place.Kind.DESK, at(9, 30)), 2)

    def test_come_later_postpones(self):
        res = self.reserve(self.d1, late_until=at(10, 30))
        self.reserve(self.d2, holder=self.other, checked_in_at=at(9))
        self.assertEqual(release.tick(at(9, 15)).released, 0)
        # Not marked while the announced arrival lies ahead.
        self.assertEqual(release.tick(at(10, 10)), release.TickResult(0, 0))
        # Marked at the arrival time, but the short grace still applies.
        self.assertEqual(release.tick(at(10, 30)), release.TickResult(0, 1))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertEqual(release.tick(at(10, 45)), release.TickResult(1, 0))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)

    def test_come_later_before_start_measures_from_start(self):
        res = self.reserve(self.d1, late_until=at(8, 30))
        self.reserve(self.d2, holder=self.other, checked_in_at=at(9))
        self.assertEqual(release.tick(at(9, 10)).released, 0)
        self.assertEqual(release.tick(at(9, 15)).released, 1)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)

    def test_potentially_free_released_when_scarce_later(self):
        res = self.reserve(self.d1)
        self.assertEqual(release.tick(at(10)).marked, 1)
        # Places become scarce later that day.
        self.reserve(self.d2, start=11, end=12, holder=self.other)
        self.assertEqual(release.tick(at(10, 30)).released, 0)
        self.assertEqual(release.tick(at(11, 5)), release.TickResult(released=1, marked=0))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.released_at, at(11, 5))
        self.assertEqual(len(self.events("grace_nudge")), 1)
        self.assertEqual(len(self.events("released_no_show")), 1)

    def test_no_show_counted_once(self):
        self.reserve(self.d1)
        release.tick(at(10))
        self.reserve(self.d2, start=11, end=12, holder=self.other)
        release.tick(at(11, 5))
        self.assertEqual(Reservation.objects.filter(no_show=True).count(), 1)
        self.assertEqual(
            Reservation.objects.filter(
                no_show=True, status=Reservation.Status.RELEASED
            ).count(),
            1,
        )

    def test_tick_idempotent(self):
        self.reserve(self.d1)
        self.reserve(self.d2, start=9, end=10)
        self.reserve(self.d3, holder=self.other, checked_in_at=at(9))
        self.assertEqual(release.tick(at(9, 20)), release.TickResult(2, 0))
        self.assertEqual(release.tick(at(9, 20)), release.TickResult(0, 0))
        self.assertEqual(release.tick(at(9, 25)), release.TickResult(0, 0))
        self.assertEqual(len(self.events("released_no_show")), 2)

    def test_release_lifts_scarcity_for_the_next(self):
        # Threshold 2: two no-shows, one checked in. Releasing the first
        # leaves one free place (still scarce), so the second goes too.
        self.reserve(self.d1)
        self.reserve(self.d2)
        self.reserve(self.d3, holder=self.other, checked_in_at=at(9))
        self.assertEqual(release.tick(at(9, 15)).released, 2)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.desk_scarcity_free_below = 1
        settings_.save()
        Reservation.objects.all().delete()
        self.reserve(self.d1)
        self.reserve(self.d2)
        self.reserve(self.d3, holder=self.other, checked_in_at=at(9))
        # Free below 1: releasing the first frees a place, the second stays.
        self.assertEqual(release.tick(at(9, 15)).released, 1)

    def test_checked_in_and_fixed_owner_untouched(self):
        checked = self.reserve(self.d1, checked_in_at=at(8, 50))
        self.d2.fixed_owner = self.other
        self.d2.save()
        own = self.reserve(self.d2, holder=self.other)
        self.reserve(self.d3, holder=self.lender, checked_in_at=at(9))
        self.assertEqual(release.tick(at(11)), release.TickResult(0, 0))
        for res in (checked, own):
            res.refresh_from_db()
            self.assertEqual(res.status, Reservation.Status.ACTIVE)
            self.assertIsNone(res.potentially_free_at)
            self.assertFalse(res.no_show)

    def test_future_and_past_reservations_untouched(self):
        future = self.reserve(self.d1, start=13, end=14)
        past = self.reserve(self.d2, start=7, end=8)
        self.reserve(self.d3, holder=self.other, checked_in_at=at(9))
        self.assertEqual(release.tick(at(9, 30)), release.TickResult(0, 0))
        for res in (future, past):
            res.refresh_from_db()
            self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertFalse(future.no_show)
        # Ended without check-in: only recorded as a no-show, nothing else.
        self.assertTrue(past.no_show)
        self.assertIsNone(past.potentially_free_at)

    def test_command(self):
        self.reserve(self.d1, start=7, end=20)
        out = StringIO()
        with mock.patch("django.utils.timezone.now", return_value=at(9)):
            call_command("desks_tick", stdout=out)
        self.assertIn("Released 0", out.getvalue())
        self.assertIn("marked 1", out.getvalue())


class TickHardeningTests(TestCase):
    def setUp(self):
        setup_department(self)
        patcher = mock.patch("desksharing.notify.notify")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def reserve(self, place, start=9, end=12, holder=None, **kw):
        holder = holder or self.member
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(DAY, start, end), **kw,
        )

    def test_ended_unused_reservation_becomes_no_show_once(self):
        res = self.reserve(self.d1)
        owned = self.reserve(self.d2, holder=self.other)
        self.d2.fixed_owner = self.other
        self.d2.save()
        used = self.reserve(self.d3, checked_in_at=at(9))
        self.assertEqual(release.tick(at(12, 1)), release.TickResult(0, 0))
        for r in (res, owned, used):
            r.refresh_from_db()
        self.assertTrue(res.no_show)
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertIsNone(res.potentially_free_at)
        self.assertFalse(owned.no_show)
        self.assertFalse(used.no_show)
        self.notify.assert_not_called()
        # Once: the ended row is not re-processed (pre-filtered in SQL).
        with self.assertNumQueries(2):
            release.tick(at(13))

    def test_disabled_department_is_skipped(self):
        res = self.reserve(self.d1)
        past = self.reserve(self.d2, start=7, end=8)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.enabled = False
        settings_.save()
        self.assertEqual(release.tick(at(10)), release.TickResult(0, 0))
        res.refresh_from_db()
        past.refresh_from_db()
        self.assertIsNone(res.potentially_free_at)
        self.assertFalse(res.no_show)
        self.assertFalse(past.no_show)

    def test_failing_notify_does_not_abort_tick(self):
        a = self.reserve(self.d1)
        b = self.reserve(self.d2, holder=self.other)
        self.notify.side_effect = RuntimeError("smtp down")
        with self.assertLogs("desksharing.release", level="ERROR"):
            result = release.tick(at(10))
        # Both were processed although the first notification raised.
        self.assertEqual(result.released + result.marked, 2)
        for r in (a, b):
            r.refresh_from_db()
            self.assertTrue(r.no_show)
            self.assertNotEqual(
                (r.status, r.potentially_free_at), (Reservation.Status.ACTIVE, None)
            )
