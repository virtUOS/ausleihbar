# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime
from unittest import mock

from django.core import mail
from django.test import TestCase

from accounts.models import AccessGroup
from desksharing import booking, door_actions, hours
from desksharing.booking import BookingError
from desksharing.models import Display, DisplayEvent, Reservation
from desksharing.tests.test_booking import setup_department

DAY = date(2027, 3, 2)  # a Tuesday


def at(hour, minute=0):
    return datetime(2027, 3, 2, hour, minute, tzinfo=hours.TZ)


class DoorActionTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.display = Display.objects.create(panel="5.79", secret_hash="x" * 64, room=self.room)
        self.now = at(7)
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def book(self, place, start, end, holder=None):
        holder = holder or self.member
        return booking.book(
            actor=holder, holder=holder, places=[place], day=DAY,
            start_hour=start, end_hour=end,
        )

    def test_display_check_in_any_holder(self):
        [res] = self.book(self.d1, 9, 11)
        door_actions.check_in(res, display=self.display, now=at(9))
        res.refresh_from_db()
        self.assertEqual(res.checked_in_at, at(9))
        event = DisplayEvent.objects.get()
        self.assertEqual(event.action, "check_in")
        self.assertEqual(event.place, self.d1)
        self.assertEqual(event.reservation, res)
        self.assertEqual(event.display, self.display)
        self.assertEqual(event.display_label, str(self.display))
        self.assertEqual(event.pool, self.pool)
        self.assertEqual(event.room, self.d1.room)

    def test_display_check_in_outside_window(self):
        [res] = self.book(self.d1, 9, 11)
        with self.assertRaises(BookingError) as cm:
            door_actions.check_in(res, display=self.display, now=at(8, 44))
        self.assertEqual(cm.exception.code, "outside_window")
        self.assertFalse(DisplayEvent.objects.exists())

    def test_display_check_out_releases_rest_without_mail(self):
        [res] = self.book(self.d1, 9, 12)
        door_actions.check_in(res, display=self.display, now=at(9))
        mail.outbox.clear()
        door_actions.check_out(res, display=self.display, now=at(10, 40))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.released_at, at(10))
        self.assertEqual(res.release_reason, "display")
        self.assertEqual(mail.outbox, [])
        self.assertEqual(DisplayEvent.objects.filter(action="check_out").count(), 1)

    def test_display_check_out_requires_checked_in(self):
        [res] = self.book(self.d1, 9, 11)
        with self.assertRaises(BookingError) as cm:
            door_actions.check_out(res, display=self.display, now=at(10))
        self.assertEqual(cm.exception.code, "not_allowed")

    def test_display_check_out_requires_started(self):
        [res] = self.book(self.d1, 9, 11)
        door_actions.check_in(res, display=self.display, now=at(8, 50))
        with self.assertRaises(BookingError) as cm:
            door_actions.check_out(res, display=self.display, now=at(8, 55))
        self.assertEqual(cm.exception.code, "not_allowed")

    def test_display_check_out_refused_after_end(self):
        [res] = self.book(self.d1, 9, 11)
        door_actions.check_in(res, display=self.display, now=at(9))
        with self.assertRaises(BookingError) as cm:
            door_actions.check_out(res, display=self.display, now=at(11, 5))
        self.assertEqual(cm.exception.code, "not_allowed")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertFalse(DisplayEvent.objects.filter(action="check_out").exists())

    def test_max_anonymous_hours_until_next_booking(self):
        self.book(self.m1, 12, 13)
        self.assertEqual(door_actions.max_anonymous_hours(self.m1, at(9, 20)), 3)
        end = hours.business_hours(self.pool, DAY)[1]
        self.assertEqual(door_actions.max_anonymous_hours(self.m1, at(end)), 0)

    def test_book_anonymous(self):
        res = door_actions.book_anonymous(self.m1, display=self.display, hours_=2, now=at(9, 20))
        self.assertEqual(res.period, hours.local_range(DAY, 9, 11))
        self.assertIsNone(res.holder)
        self.assertIsNone(res.booked_by)
        self.assertEqual(res.display, self.display)
        self.assertEqual(res.pool, self.pool)
        self.assertEqual(res.checked_in_at, at(9, 20))
        self.assertEqual(DisplayEvent.objects.get(action="book").reservation, res)
        self.assertEqual(mail.outbox, [])

    def test_door_booking_flag_in_overview_and_manage_list(self):
        from desksharing import overview
        from desksharing.serializers import ManageReservationSerializer

        anon = door_actions.book_anonymous(self.m1, display=self.display, hours_=1, now=at(9, 20))
        [own] = self.book(self.m1, 12, 13)
        day = overview.department_day(self.pool, DAY, viewer=self.lender, now=at(9, 20))
        [room] = [m for m in day["meeting_rooms"] if m["id"] == self.m1.pk]
        flags = {r["id"]: r["door_booking"] for r in room["reservations"]}
        self.assertEqual(flags, {anon.pk: True, own.pk: False})
        [place] = [p for f in day["floors"] for p in f["places"] if p["id"] == self.m1.pk]
        by_hour = {h["hour"]: h["door_booking"] for h in place["hours"]}
        self.assertEqual((by_hour[9], by_hour[12], by_hour[14]), (True, False, False))
        rows = ManageReservationSerializer(
            [anon, own], many=True, context={"viewer": self.lender}
        ).data
        self.assertEqual([r["door_booking"] for r in rows], [True, False])
        self.assertIsNone(rows[0]["holder_name"])

    def test_book_anonymous_clamped(self):
        self.book(self.m1, 12, 13)
        res = door_actions.book_anonymous(self.m1, display=self.display, hours_=9, now=at(9, 20))
        self.assertEqual(res.period, hours.local_range(DAY, 9, 12))
        res2 = door_actions.book_anonymous(self.m1, display=self.display, hours_=0, now=at(13, 30))
        self.assertEqual(res2.period, hours.local_range(DAY, 13, 14))

    def test_book_anonymous_not_bookable_now(self):
        end = hours.business_hours(self.pool, DAY)[1]
        with self.assertRaises(BookingError) as cm:
            door_actions.book_anonymous(self.m1, display=self.display, hours_=1, now=at(end))
        self.assertEqual(cm.exception.code, "taken")

    def test_book_anonymous_taken_now(self):
        self.book(self.m1, 9, 10)
        with self.assertRaises(BookingError) as cm:
            door_actions.book_anonymous(self.m1, display=self.display, hours_=1, now=at(9, 10))
        self.assertEqual(cm.exception.code, "taken")

    def test_book_anonymous_ignores_access_groups(self):
        self.m1.access_groups.set([AccessGroup.objects.create(name="Elsewhere")])
        res = door_actions.book_anonymous(self.m1, display=self.display, hours_=1, now=at(9))
        self.assertIsNone(res.holder)

    def test_book_anonymous_desk_refused(self):
        with self.assertRaises(BookingError) as cm:
            door_actions.book_anonymous(self.d1, display=self.display, hours_=1, now=at(9))
        self.assertEqual(cm.exception.code, "not_allowed")
