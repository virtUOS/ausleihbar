# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from unittest import mock

from django.test import TestCase

from desksharing import booking, checkin, door_actions, hours, privacy
from desksharing.door_view import build_door_view, next_wake_seconds
from desksharing.models import DeskSettings, Display, Place, Room
from desksharing.qr import room_qr_url
from desksharing.tests.test_booking import setup_department

DAY = date(2027, 3, 2)  # a Tuesday


def at(hour, minute=0):
    return datetime(2027, 3, 2, hour, minute, tzinfo=hours.TZ)


class DoorViewTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.meeting_room = self.m1.room
        self.now = at(9)
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def book(self, place, start, end, holder=None, **kw):
        holder = holder or self.member
        shown, self.now = self.now, at(5)  # booking must happen "before"
        try:
            [res] = booking.book(
                actor=holder, holder=holder, places=[place], day=DAY,
                start_hour=start, end_hour=end, **kw,
            )
        finally:
            self.now = shown
        return res

    def check_in(self, res, now=None):
        checkin.check_in(res, user=res.holder, now=now or self.now)

    def view(self, room=None, now=None):
        return build_door_view(room or self.room, panel="5.79", now=now or self.now)

    def tile(self, view, place):
        return next(t for t in view.desks if t.place_id == place.pk)

    def test_office_names_and_hidden(self):
        privacy.set_hide_name(self.member, True)
        self.check_in(self.book(self.d1, 8, 17))
        self.check_in(self.book(self.d2, 8, 17, holder=self.other))
        view = self.view()
        self.assertEqual(view.kind, "office")
        self.assertEqual(self.tile(view, self.d1).label, "belegt")
        self.assertEqual(self.tile(view, self.d2).label, privacy.display_name(self.other))
        self.assertEqual((view.free_count, view.total), (1, 3))
        self.assertIsNone(self.tile(view, self.d3).label)
        self.assertEqual(view.room_qr_url, room_qr_url(self.room))

    def test_until_only_below_five_hours(self):
        self.book(self.d1, 8, 17)
        self.book(self.d2, 8, 11, holder=self.other)
        view = self.view()
        self.assertIsNone(self.tile(view, self.d1).until)
        self.assertEqual(self.tile(view, self.d2).until, at(11))

    def test_fixed_owner_tile_not_actionable(self):
        self.d3.fixed_owner = self.other
        self.d3.save()
        tile = self.tile(self.view(), self.d3)
        self.assertEqual(tile.label, privacy.display_name(self.other))
        self.assertIsNone(tile.actionable)
        self.assertIsNone(tile.reservation_id)

    def test_actionable_states(self):
        res = self.book(self.d1, 9, 11)
        self.assertEqual(self.tile(self.view(), self.d1).actionable, "check_in")
        self.assertEqual(self.tile(self.view(), self.d1).reservation_id, res.pk)
        self.check_in(res)
        self.assertEqual(self.tile(self.view(), self.d1).actionable, "check_out")
        free = self.tile(self.view(), self.d2)
        self.assertIsNone(free.actionable)
        self.assertIsNone(free.reservation_id)

    def test_not_actionable_outside_window(self):
        self.book(self.d1, 12, 14)
        tile = self.tile(self.view(), self.d1)
        self.assertEqual(tile.state, "free")
        self.assertIsNone(tile.actionable)
        self.assertEqual(tile.free_note, "ab 12:00 gebucht")
        self.assertEqual(self.tile(self.view(now=at(11, 50)), self.d1).actionable, "check_in")

    def test_meeting_view(self):
        privacy.set_hide_name(self.member, True)
        res = self.book(self.m1, 9, 10, comment="Projekttreffen")
        self.check_in(res)
        self.book(self.m1, 11, 12, comment="Review", holder=self.other)
        view = self.view(self.meeting_room)
        info = view.meeting
        self.assertEqual(view.kind, "meeting")
        self.assertEqual(info.state, "checked_in")
        self.assertEqual(info.title, "Projekttreffen")
        self.assertEqual(info.holder, privacy.display_name(self.member))
        self.assertEqual((info.start, info.end), (at(9), at(10)))
        self.assertEqual(info.reservation_id, res.pk)
        self.assertEqual(
            [(s.start, s.end, s.label) for s in info.schedule],
            [(at(10), at(11), "frei"), (at(11), at(12), "Review"), (at(12), at(20), "frei")],
        )

    def test_meeting_free(self):
        self.book(self.m1, 11, 12, comment="Review")
        info = self.view(self.meeting_room).meeting
        self.assertEqual(info.state, "free")
        self.assertEqual(info.free_until, at(11))
        self.assertEqual(info.max_hours, 2)
        self.assertIn("Review", info.next_label)
        self.assertIsNone(info.title)

    def test_meeting_anonymous_title(self):
        display = Display.objects.create(panel="5.79", secret_hash="x" * 64, room=self.meeting_room)
        door_actions.book_anonymous(self.m1, display=display, hours_=1, now=self.now)
        info = self.view(self.meeting_room).meeting
        self.assertEqual(info.title, "Spontan belegt")
        self.assertIsNone(info.holder)

    def test_release_at_uses_grace(self):
        DeskSettings.objects.filter(pool=self.pool).update(
            room_grace_short_min=10, room_grace_normal_min=45
        )
        self.book(self.m1, 9, 10)
        # Booked room: 0 free meeting rooms < threshold 2 -> scarce.
        self.assertEqual(self.view(self.meeting_room).meeting.release_at, at(9, 10))
        DeskSettings.objects.filter(pool=self.pool).update(room_scarcity_free_below=0)
        self.assertEqual(self.view(self.meeting_room).meeting.release_at, at(9, 45))

    def test_room_qr_only_when_free(self):
        for place in (self.d1, self.d2, self.d3):
            self.book(place, 8, 17)
        view = self.view()
        self.assertEqual(view.free_count, 0)
        self.assertIsNone(view.room_qr_url)

    def test_single_and_closed(self):
        self.d2.is_active = False
        self.d2.save()
        self.d3.is_active = False
        self.d3.save()
        self.assertEqual(self.view().kind, "single")
        self.assertIsNone(self.view().room_qr_url)
        view = self.view(now=at(22))
        self.assertEqual(view.kind, "closed")
        self.assertEqual(view.next_wake, 14400)

    def test_mixed_room_uses_places_own_department(self):
        other_pool = self._other_pool()
        self.d3.pool = other_pool
        self.d3.pool_overridden = True
        self.d3.save()
        view = self.view()
        self.assertEqual(self.tile(view, self.d3).state, "free")
        self.assertEqual(view.total, 3)

    def _other_pool(self):
        from desksharing.tests.test_booking import make_pool
        return make_pool("PoolB", self.group)

    def test_degenerate_rooms(self):
        floor = self.floor
        empty = Room.objects.create(floor=floor, pool=self.pool, name="E")
        self.assertEqual(self.view(empty).kind, "empty")
        gone = Room.objects.create(floor=floor, pool=self.pool, name="G")
        Place.objects.create(room=gone, name="G1", is_active=False)
        self.assertEqual(self.view(gone).kind, "empty")
        unassigned = Room.objects.create(floor=floor, pool=None, name="U")
        Place.objects.create(room=unassigned, name="U1")
        self.assertEqual(self.view(unassigned).kind, "empty")

    def test_next_wake_bounds(self):
        self.assertEqual(next_wake_seconds(self.pool, at(12)), 300)
        self.assertTrue(60 <= next_wake_seconds(self.pool, at(19, 59)) <= 300)
        self.assertEqual(next_wake_seconds(self.pool, at(22)), 14400)
        before_open = next_wake_seconds(self.pool, at(5, 30))
        self.assertEqual(before_open, 25 * 60)
        sunday = datetime(2027, 3, 7, 12, tzinfo=hours.TZ)
        self.assertTrue(60 <= next_wake_seconds(self.pool, sunday) <= 14400)
        dst_sunday = datetime(2027, 3, 28, 12, tzinfo=hours.TZ)
        self.assertGreater(next_wake_seconds(self.pool, dst_sunday), 0)
        self.assertEqual(next_wake_seconds(None, at(12)), 14400)

    def test_next_wake_mid_day_closure(self):
        from lending.models import Block
        Block.objects.create(period=hours.local_range(DAY, 12, 14), resource_pool=self.pool)
        # 12:30 closed; reopens 14:00 -> wake 13:55 (suggests 1h25m), not tomorrow.
        self.assertEqual(next_wake_seconds(self.pool, at(12, 30)), 85 * 60)

    def test_meeting_qr_url(self):
        from desksharing.qr import place_qr_url
        info = self.view(self.meeting_room).meeting
        self.assertEqual(info.qr_url, place_qr_url(self.m1))

    def test_closed_view_next_open_and_booking(self):
        next_day = DAY + timedelta(days=1)
        shown, self.now = self.now, at(5)
        try:
            booking.book(actor=self.member, holder=self.member, places=[self.m1], day=next_day,
                         start_hour=8, end_hour=9, comment="Frühtreffen")
            booking.book(actor=self.member, holder=self.member, places=[self.d1], day=next_day,
                         start_hour=7, end_hour=9)
        finally:
            self.now = shown
        view = self.view(self.meeting_room, now=at(22))
        self.assertEqual(view.kind, "closed")
        self.assertEqual(view.next_open, hours.local_dt(next_day, 6))
        self.assertEqual(view.next_booking.label, "Frühtreffen")
        self.assertEqual(view.next_booking.start, hours.local_dt(next_day, 8))
        office = self.view(now=at(22))
        self.assertEqual(office.next_booking.label, "D1")
        self.assertEqual(self.view(self.meeting_room).next_open, None)
