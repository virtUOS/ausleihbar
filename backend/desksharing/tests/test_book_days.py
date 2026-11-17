# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from desksharing import booking, cycles, hours
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, Reservation
from desksharing.tests.test_booking import setup_department
from desksharing.tests.test_hours import next_weekday

User = get_user_model()
URL = "/api/desks/reservations/days/"


class BookDaysTests(TestCase):
    def setUp(self):
        setup_department(self)
        tue = next_weekday(1)
        self.days = [tue + timedelta(weeks=i) for i in range(3)]

    def book(self, places, days=None, holder=None, **kw):
        holder = holder or self.member
        return booking.book_days(
            actor=holder, holder=holder, places=places, days=days or self.days,
            start_hour=9, end_hour=12, **kw,
        )

    def other_books(self, place, day, holder=None):
        return booking.book(
            actor=holder or self.other, holder=holder or self.other, places=[place],
            day=day, start_hour=10, end_hour=11,
        )

    def test_books_all_free_days_in_one_group(self):
        rows, requests = self.book([self.d1, self.d2])
        self.assertEqual((len(rows), requests), (6, []))
        self.assertEqual(len({r.group for r in rows}), 1)

    def test_closed_day_refused_nothing_booked(self):
        from lending.models import Block

        Block.objects.create(period=hours.local_range(self.days[1], 6, 20), reason="Holiday")
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1])
        self.assertEqual(cm.exception.code, "closed")
        self.assertEqual(cm.exception.extra["day"], self.days[1].isoformat())
        self.assertEqual(Reservation.objects.count(), 0)

    def test_taken_with_fail_returns_taken_dates(self):
        self.other_books(self.d1, self.days[1])
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1, self.d2])
        self.assertEqual(cm.exception.code, "taken")
        self.assertEqual(
            cm.exception.extra["taken"],
            [{"day": self.days[1].isoformat(), "place_id": self.d1.pk}],
        )
        self.assertEqual(Reservation.objects.filter(holder=self.member).count(), 0)
        with self.assertRaises(BookingError):
            self.book([self.d1], on_taken="request")  # Task 4 plugs in requests

    def test_fixed_place_unavailable(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1, self.d2])
        self.assertEqual(cm.exception.detail, "Some dates cannot be requested.")
        self.assertEqual(
            {(u["day"], u["place_id"]) for u in cm.exception.extra["unavailable"]},
            {(d.isoformat(), self.d1.pk) for d in self.days},
        )
        self.assertEqual(Reservation.objects.count(), 0)

    def test_two_blockers_unavailable(self):
        day = self.days[0]
        booking.book(actor=self.other, holder=self.other, places=[self.d1], day=day, start_hour=9, end_hour=10)
        booking.book(actor=self.lender, holder=self.lender, places=[self.d1], day=day, start_hour=11, end_hour=12)
        # lender is no member but a pool lender, so may book
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1], days=[day])
        self.assertEqual(
            cm.exception.extra["unavailable"],
            [{"day": day.isoformat(), "place_id": self.d1.pk}],
        )

    def test_own_overlap_unavailable(self):
        booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=self.days[0],
            start_hour=11, end_hour=13,
        )
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1], days=[self.days[0]])
        self.assertIn("unavailable", cm.exception.extra)

    def test_limits_checked_on_whole_request(self):
        today = cycles.today()
        with mock.patch("desksharing.cycles.today", return_value=today):
            DeskSettings.objects.filter(pool=self.pool).update(advance_days=2)
            window = cycles.booking_window(self.pool)
            first = window.open_until + timedelta(days=1)
            first += timedelta(days=(1 - first.weekday()) % 7)
            beyond = [first + timedelta(weeks=i) for i in range(3)]
            with self.assertRaises(BookingError) as cm:
                self.book([self.d1], days=beyond)
        self.assertEqual(cm.exception.code, "advance_days")
        self.assertEqual(Reservation.objects.count(), 0)

    def test_desks_multi_day_allowed(self):
        tue = self.days[0]
        rows, _ = self.book([self.d1], days=[tue, tue + timedelta(days=1)])
        self.assertEqual(len(rows), 2)

    def test_payload_limits(self):
        client = APIClient()
        client.force_authenticate(self.member)
        day = self.days[0].isoformat()
        base = {"place_ids": [self.d1.pk], "days": [day], "start_hour": 9, "end_hour": 10}
        self.assertEqual(client.post(URL, base, format="json").status_code, 201)
        bad = [
            {**base, "place_ids": list(range(1, 22))},
            {**base, "days": [(self.days[0] + timedelta(days=i)).isoformat() for i in range(367)]},
            {**base, "days": [day, day]},
        ]
        for body in bad:
            self.assertEqual(client.post(URL, body, format="json").status_code, 400, body)

    def test_endpoint_taken_body(self):
        self.other_books(self.d1, self.days[0])
        client = APIClient()
        client.force_authenticate(self.member)
        r = client.post(URL, {"place_ids": [self.d1.pk], "days": [self.days[0].isoformat()],
                              "start_hour": 9, "end_hour": 12}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["taken"][0]["place_id"], self.d1.pk)
