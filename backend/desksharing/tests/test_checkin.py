# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from desksharing import booking, checkin, hours
from desksharing.booking import BookingError
from desksharing.models import Reservation
from desksharing.tests.test_booking import API, setup_department

DAY = date(2027, 3, 2)  # a Tuesday


def at(hour, minute=0):
    return datetime(2027, 3, 2, hour, minute, tzinfo=hours.TZ)


class CheckinTests(TestCase):
    def setUp(self):
        setup_department(self)
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

    def test_checkin_window(self):
        [res] = self.book(self.d1, 9, 11)
        for now in (at(8, 44), at(11)):
            with self.assertRaises(BookingError) as cm:
                checkin.check_in(res, user=self.member, now=now)
            self.assertEqual(cm.exception.code, "outside_window")
        with self.assertRaises(BookingError):
            checkin.check_in(res, user=self.other, now=at(9))
        checkin.check_in(res, user=self.member, now=at(8, 45))
        res.refresh_from_db()
        self.assertEqual(res.checked_in_at, at(8, 45))

    def test_group_checkin_same_day_only(self):
        a, b = self.book(self.d1, 9, 11)[0], None
        group_rows = booking.book(
            actor=self.member, holder=self.member, places=[self.d2, self.d3],
            day=DAY, start_hour=9, end_hour=11,
        )
        # A reservation of the same group on another day (e.g. a range).
        other_day = Reservation.objects.create(
            place=self.d2, holder=self.member, booked_by=self.member,
            group=group_rows[0].group,
            period=hours.local_range(DAY + timedelta(days=1), 9, 11),
        )
        checkin.check_in(group_rows[0], user=self.member, now=at(9))
        for row in group_rows:
            row.refresh_from_db()
            self.assertIsNotNone(row.checked_in_at)
        other_day.refresh_from_db()
        self.assertIsNone(other_day.checked_in_at)
        a.refresh_from_db()
        self.assertIsNone(a.checked_in_at)

    def test_scan_free_place_books_and_checks_in(self):
        self.book(self.d1, 11, 12, holder=self.other)
        self.now = at(9, 20)
        result = checkin.scan(self.d1.qr_token, user=self.member)
        self.assertEqual(result.action, "booked")
        self.assertEqual(result.reservation.period, hours.local_range(DAY, 9, 11))
        self.assertEqual(result.next_free_until, at(11))
        self.assertEqual(result.reservation.checked_in_at, at(9, 20))
        # Free until the business end otherwise.
        result = checkin.scan(self.d2.qr_token, user=self.member)
        self.assertEqual(result.reservation.period, hours.local_range(DAY, 9, 20))

    def test_scan_booked_place_checks_in(self):
        [res] = self.book(self.d1, 10, 12)
        self.now = at(9, 50)
        result = checkin.scan(self.d1.qr_token, user=self.member)
        self.assertEqual(result.action, "checked_in")
        self.assertEqual(result.reservation.pk, res.pk)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_scan_other_holders_place_is_taken(self):
        self.book(self.d1, 9, 12, holder=self.other)
        self.now = at(10, 10)
        result = checkin.scan(self.d1.qr_token, user=self.member)
        self.assertEqual(result.action, "taken")
        self.assertIsNone(result.reservation)
        self.assertEqual(result.next_free_until, at(12))

    def test_scan_without_rights(self):
        stranger = self.lender.__class__.objects.create_user("stranger", password="x")
        self.now = at(9, 5)
        self.assertEqual(checkin.scan(self.d1.qr_token, user=stranger).action, "not_allowed")
        self.assertEqual(checkin.scan("nope", user=self.member).action, "not_allowed")
        self.d1.is_active = False
        self.d1.save()
        self.assertEqual(checkin.scan(self.d1.qr_token, user=self.member).action, "not_allowed")
        # Outside business hours.
        self.now = at(21)
        self.assertEqual(checkin.scan(self.d2.qr_token, user=self.member).action, "not_allowed")
        self.assertEqual(Reservation.objects.count(), 0)

    def test_later_until_bounded_by_end(self):
        [res] = self.book(self.d1, 9, 11)
        self.now = at(9, 5)
        for until in (at(11, 1), at(9, 5), at(8)):
            with self.assertRaises(BookingError):
                checkin.come_later(res, user=self.member, until=until)
        with self.assertRaises(BookingError):
            checkin.come_later(res, user=self.other, until=at(10))
        checkin.come_later(res, user=self.member, until=at(10, 30))
        res.refresh_from_db()
        self.assertEqual(res.late_until, at(10, 30))

    def test_fixed_place_checkin_optional(self):
        self.d1.fixed_owner = self.member
        self.d1.save()
        self.now = at(8, 30)
        result = checkin.scan(self.d1.qr_token, user=self.member)
        self.assertEqual(result.action, "booked")
        self.assertEqual(result.reservation.holder, self.member)
        self.assertEqual(result.reservation.period, hours.local_range(DAY, 8, 20))
        self.assertIsNotNone(result.reservation.checked_in_at)
        # Others get "taken" on it.
        self.d2.fixed_owner = self.member
        self.d2.save()
        self.assertEqual(checkin.scan(self.d2.qr_token, user=self.other).action, "taken")

    def test_not_allowed_reasons(self):
        stranger = self.lender.__class__.objects.create_user("stranger", password="x")
        self.now = at(9, 5)
        self.assertEqual(checkin.scan("nope", user=self.member).reason, "unknown_token")
        self.assertEqual(checkin.scan(self.d1.qr_token, user=stranger).reason, "no_rights")
        self.now = at(21)
        self.assertEqual(checkin.scan(self.d1.qr_token, user=self.member).reason, "outside_hours")
        self.d1.is_active = False
        self.d1.save()
        self.assertEqual(checkin.scan(self.d1.qr_token, user=self.member).reason, "inactive")
        self.now = at(9) + timedelta(days=5)  # a Sunday, closed
        self.assertEqual(checkin.scan(self.d2.qr_token, user=self.member).reason, "closed")

    def test_scan_meeting_room_books_current_hour_only(self):
        self.now = at(9, 20)
        result = checkin.scan(self.m1.qr_token, user=self.member)
        self.assertEqual(result.action, "booked")
        self.assertEqual(result.reservation.period, hours.local_range(DAY, 9, 10))

    def test_scan_is_atomic(self):
        self.now = at(9, 5)
        with mock.patch(
            "desksharing.checkin.check_in", side_effect=BookingError("not_allowed")
        ):
            self.assertEqual(checkin.scan(self.d1.qr_token, user=self.member).action, "not_allowed")
        self.assertEqual(Reservation.objects.count(), 0)

    def test_api_rights(self):
        [res] = self.book(self.d1, 9, 11)
        self.now = at(9)
        stranger = self.lender.__class__.objects.create_user("stranger", password="x")
        client = APIClient()
        client.force_authenticate(stranger)
        self.assertEqual(client.post(f"{API}/reservations/{res.pk}/check-in/").status_code, 404)
        r = client.post(f"{API}/reservations/{res.pk}/later/", {"until": at(10).isoformat()})
        self.assertEqual(r.status_code, 404)
        r = client.post(f"{API}/scan/", {"token": self.d2.qr_token}, format="json")
        self.assertEqual((r.data["action"], r.data["reason"]), ("not_allowed", "no_rights"))
        # Place check-in: taken by someone else, and not allowed.
        client.force_authenticate(self.other)
        r = client.post(f"{API}/places/{self.d1.pk}/check-in/")
        self.assertEqual(r.data["action"], "taken")
        self.assertEqual(r.data["next_free_until"], at(11))
        client.force_authenticate(stranger)
        r = client.post(f"{API}/places/{self.d3.pk}/check-in/")
        self.assertEqual(r.data["action"], "not_allowed")

    def test_api(self):
        client = APIClient()
        client.force_authenticate(self.member)
        [res] = self.book(self.d1, 9, 11)
        self.now = at(9)
        r = client.post(f"{API}/reservations/{res.pk}/later/", {"until": at(10).isoformat()})
        self.assertEqual(r.status_code, 200)
        r = client.post(f"{API}/reservations/{res.pk}/later/", {"until": at(12).isoformat()})
        self.assertEqual(r.status_code, 409)
        r = client.post(f"{API}/reservations/{res.pk}/check-in/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["checked_in_at"], at(9).isoformat())
        self.assertEqual(r.data["late_until"], at(10).isoformat())
        self.assertIsNone(r.data["potentially_free_at"])
        r = client.post(f"{API}/scan/", {"token": self.d2.qr_token}, format="json")
        self.assertEqual(r.data["action"], "booked")
        r = client.post(f"{API}/places/{self.d3.pk}/check-in/")
        self.assertEqual(r.data["action"], "booked")
        self.assertEqual(client.post(f"{API}/scan/", {}, format="json").status_code, 400)
