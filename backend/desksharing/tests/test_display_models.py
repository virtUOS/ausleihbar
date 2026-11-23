# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime

from django.test import TestCase

from desksharing import booking, hours
from desksharing.models import Display, DisplayEvent, Reservation
from desksharing.tests.test_booking import setup_department


class DisplayModelTests(TestCase):
    def setUp(self):
        setup_department(self)

    def make_display(self, **kw):
        kw.setdefault("secret_hash", "h" * 64)
        return Display.objects.create(**kw)

    def test_display_str_and_is_paired(self):
        d = self.make_display()
        self.assertFalse(d.is_paired)
        self.assertEqual(str(d), f"Display {d.pk}")
        d.room = self.room
        d.name = "Door R1"
        self.assertTrue(d.is_paired)
        self.assertEqual(str(d), "Door R1")

    def test_reservation_display_set_null(self):
        d = self.make_display(room=self.room)
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=date(2027, 3, 2), start_hour=9, end_hour=10,
        )
        Reservation.objects.filter(pk=res.pk).update(display=d)
        res.refresh_from_db()
        self.assertEqual(res.display_id, d.pk)
        d.delete()
        res.refresh_from_db()
        self.assertIsNone(res.display)

    def test_event_survives_display_delete(self):
        d = self.make_display(room=self.room, name="Door R1")
        ev = DisplayEvent.objects.create(
            display=d, display_label="Door R1", pool=self.pool, room=self.room,
            place=self.d1, action=DisplayEvent.Action.CHECK_IN,
        )
        d.delete()
        ev.refresh_from_db()
        self.assertIsNone(ev.display)
        self.assertEqual(ev.display_label, "Door R1")
        self.assertEqual(ev.action, "check_in")
