# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from unittest import mock

from django.test import TestCase

from desksharing import booking, door_session, hours, privacy
from desksharing.models import Display, DisplayEvent, Reservation
from desksharing.tests.test_booking import setup_department

DAY = date(2027, 3, 2)  # a Tuesday


def at(hour, minute=0, second=0):
    return datetime(2027, 3, 2, hour, minute, second, tzinfo=hours.TZ)


class DoorSessionTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.now = at(9)
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.office = Display.objects.create(panel="5.79", secret_hash="o" * 64, room=self.room)
        self.meeting = Display.objects.create(
            panel="5.79", secret_hash="m" * 64, room=self.m1.room
        )

    def book(self, place, start, end, holder=None):
        holder = holder or self.member
        shown, self.now = self.now, at(5)
        try:
            [res] = booking.book(
                actor=holder, holder=holder, places=[place], day=DAY,
                start_hour=start, end_hour=end,
            )
        finally:
            self.now = shown
        return res

    def single_display(self):
        from desksharing.models import Place, Room

        room = Room.objects.create(floor=self.floor, pool=self.pool, name="Solo")
        self.solo = Place.objects.create(room=room, name="S1")
        return Display.objects.create(panel="2.1", secret_hash="s" * 64, room=room)

    # single
    def test_single_any_button_checks_in(self):
        display = self.single_display()
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.solo], day=DAY,
            start_hour=9, end_hour=11,
        )
        screen = door_session.press(display, "up", self.now)
        res.refresh_from_db()
        self.assertEqual(res.checked_in_at, self.now)
        self.assertEqual(screen.message, "Eingecheckt ✓")
        self.assertEqual(screen.mode, "normal")
        self.assertEqual(screen.session_timeout, 0)

    def test_single_checkout_needs_second_press(self):
        display = self.single_display()
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.solo], day=DAY,
            start_hour=9, end_hour=11,
        )
        door_session.press(display, "top", self.now)
        screen = door_session.press(display, "bottom", self.now)
        self.assertEqual(screen.mode, "confirm")
        self.assertEqual(screen.session_timeout, 10)
        self.assertFalse(DisplayEvent.objects.filter(action="check_out").exists())
        screen = door_session.press(display, "down", self.now)
        self.assertEqual(screen.message, "Ausgecheckt")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)

    def test_single_confirm_expires_after_10s(self):
        display = self.single_display()
        booking.book(
            actor=self.member, holder=self.member, places=[self.solo], day=DAY,
            start_hour=9, end_hour=11,
        )
        door_session.press(display, "top", self.now)
        door_session.press(display, "top", self.now)
        later = self.now + timedelta(seconds=11)
        self.assertEqual(door_session.current_screen(display, later).mode, "normal")
        self.assertEqual(Reservation.objects.get().status, Reservation.Status.ACTIVE)
        self.assertEqual(door_session.press(display, "wake", later).mode, "normal")

    def test_single_free_just_refreshes(self):
        display = self.single_display()
        screen = door_session.press(display, "top", self.now)
        self.assertEqual((screen.mode, screen.message), ("normal", None))

    # office
    def test_office_select_wraps_and_times_out(self):
        screen = door_session.press(self.office, "down", self.now)
        self.assertEqual((screen.mode, screen.selected, screen.session_timeout), ("select", 0, 20))
        screen = door_session.press(self.office, "up", self.now)
        self.assertEqual(screen.selected, 2)  # wrapped to the last tile
        screen = door_session.press(self.office, "down", self.now)
        self.assertEqual(screen.selected, 0)
        later = self.now + timedelta(seconds=21)
        self.assertEqual(door_session.current_screen(self.office, later).mode, "normal")

    def test_office_select_starts_at_first_actionable(self):
        self.book(self.d2, 9, 11)
        screen = door_session.press(self.office, "down", self.now)
        self.assertEqual(screen.selected, 1)

    def test_office_checkin_selected(self):
        res = self.book(self.d2, 9, 11)
        door_session.press(self.office, "down", self.now)
        screen = door_session.press(self.office, "top", self.now)
        res.refresh_from_db()
        self.assertEqual(res.checked_in_at, self.now)
        self.assertEqual((screen.mode, screen.message), ("normal", "Eingecheckt ✓"))

    def test_office_checkout_confirm_text_hidden_name(self):
        privacy.set_hide_name(self.member, True)
        res = self.book(self.d1, 9, 11)
        door_session.press(self.office, "down", self.now)
        door_session.press(self.office, "top", self.now)  # check in
        door_session.press(self.office, "down", self.now)  # select
        screen = door_session.press(self.office, "top", self.now)
        self.assertEqual((screen.mode, screen.confirm_text), ("confirm", "D1 auschecken?"))
        screen = door_session.press(self.office, "top", self.now)
        self.assertEqual(screen.message, "Ausgecheckt")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)

    def test_office_confirm_text_shows_name_and_bottom_cancels(self):
        self.book(self.d1, 9, 11)
        door_session.press(self.office, "down", self.now)
        door_session.press(self.office, "top", self.now)
        door_session.press(self.office, "down", self.now)
        screen = door_session.press(self.office, "top", self.now)
        self.assertEqual(screen.confirm_text, f"{privacy.display_name(self.member)} auschecken?")
        screen = door_session.press(self.office, "bottom", self.now)
        self.assertEqual(screen.mode, "normal")
        self.assertEqual(Reservation.objects.get().status, Reservation.Status.ACTIVE)

    def test_confirm_after_reservation_released_does_nothing(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=DAY,
            start_hour=9, end_hour=11,
        )
        door_session.press(self.office, "down", self.now)
        door_session.press(self.office, "top", self.now)
        door_session.press(self.office, "down", self.now)
        screen = door_session.press(self.office, "top", self.now)
        self.assertEqual(screen.mode, "confirm")
        booking.cancel(res, actor=self.member)
        screen = door_session.press(self.office, "top", self.now)
        self.assertFalse(DisplayEvent.objects.filter(action="check_out").exists())
        self.assertEqual((screen.mode, screen.message), ("normal", None))

    # 2.1" bound to a non-single room
    def test_small_panel_on_office_does_nothing(self):
        self.office.panel = "2.1"
        self.office.save()
        self.book(self.d1, 9, 11)
        screen = door_session.press(self.office, "top", self.now)
        self.assertEqual((screen.mode, screen.message), ("normal", None))
        self.assertFalse(DisplayEvent.objects.exists())
        self.assertEqual(door_session.press(self.office, "down", self.now).mode, "normal")

    def test_closed_room_buttons_refresh_only(self):
        late = at(22)
        self.assertEqual(door_session.press(self.office, "top", late).view.kind, "closed")

    # meeting
    def test_meeting_duration_clamped(self):
        self.book(self.m1, 11, 12)
        self.now = at(9, 10)
        screen = door_session.press(self.meeting, "down", self.now)
        self.assertEqual((screen.mode, screen.hours, screen.session_timeout), ("select", 1, 20))
        for button, expected in (("up", 2), ("up", 2), ("down", 1), ("down", 1), ("up", 2)):
            self.assertEqual(door_session.press(self.meeting, button, self.now).hours, expected)
        screen = door_session.press(self.meeting, "top", self.now)
        self.assertEqual(screen.message, "Belegt bis 11:00")
        res = Reservation.objects.get(holder=None)
        self.assertEqual(res.period, hours.local_range(DAY, 9, 11))
        self.assertEqual(DisplayEvent.objects.filter(action="book").count(), 1)

    def test_meeting_book_default_one_hour(self):
        screen = door_session.press(self.meeting, "top", self.now)
        self.assertEqual(screen.message, "Belegt bis 10:00")

    def test_meeting_booked_checkin_then_end_confirm(self):
        res = self.book(self.m1, 9, 10)
        screen = door_session.press(self.meeting, "top", self.now)
        self.assertEqual(screen.message, "Eingecheckt ✓")
        screen = door_session.press(self.meeting, "top", self.now)
        self.assertEqual((screen.mode, screen.confirm_text), ("confirm", "Meeting beenden?"))
        screen = door_session.press(self.meeting, "top", self.now)
        self.assertEqual(screen.message, "Ausgecheckt")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
