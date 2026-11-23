# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from desksharing import booking, displays, door_render, hours
from desksharing.models import Display, Reservation
from desksharing.tests.test_booking import setup_department

DAY = date(2027, 3, 2)  # a Tuesday
FRAME = "/api/displays/frame/"
EVENT = "/api/displays/event/"


def at(hour, minute=0):
    return datetime(2027, 3, 2, hour, minute, tzinfo=hours.TZ)


def secret(n=0):
    return f"{n:02x}" * 32


class DisplayApiTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.now = at(9)
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.clear()

    def hdr(self, sec=None, panel="5.79", **extra):
        out = {"HTTP_AUTHORIZATION": f"Bearer {sec or secret(1)}", "HTTP_X_PANEL": panel}
        out.update(extra)
        return out

    def frame(self, sec=None, **kw):
        return self.client.get(FRAME, **self.hdr(sec, **kw))

    def event(self, button, sec=None, **kw):
        return self.client.post(
            EVENT, {"button": button}, content_type="application/json", **self.hdr(sec, **kw)
        )

    def pair(self, sec=None, room=None):
        return Display.objects.create(
            panel="5.79", secret_hash=displays.hash_secret(sec or secret(1)),
            room=room or self.room, paired_at=self.now,
        )

    def book(self, place, start, end):
        shown, self.now = self.now, at(5)
        try:
            [res] = booking.book(
                actor=self.member, holder=self.member, places=[place], day=DAY,
                start_hour=start, end_hour=end,
            )
        finally:
            self.now = shown
        return res

    # pairing
    def test_unknown_secret_gets_pairing_frame_and_pending_row(self):
        r = self.frame()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/octet-stream")
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertEqual(r["X-Next-Wake"], "30")
        self.assertEqual(r["X-Session-Timeout"], "0")
        d = Display.objects.get()
        self.assertFalse(d.is_paired)
        self.assertEqual(len(d.pairing_code), 8)
        self.assertEqual(d.pairing_expires_at, self.now + timedelta(minutes=10))
        self.assertNotEqual(d.secret_hash, secret(1))
        expected = door_render.to_frame(door_render.render_pairing(d.pairing_code, "5.79"))
        self.assertEqual(r.content, expected)
        self.assertEqual(d.last_etag, door_render.frame_etag(expected))

    def test_bad_secret_or_panel_creates_nothing(self):
        for sec in ("short", "z" * 64, "ab" * 300):
            self.assertEqual(self.frame(sec).status_code, 400)
        self.assertEqual(self.frame(panel="9.9").status_code, 400)
        self.assertEqual(self.client.get(FRAME, HTTP_X_PANEL="2.1").status_code, 401)
        self.assertEqual(Display.objects.count(), 0)

    def test_same_secret_keeps_code_until_expiry_then_rotates(self):
        self.frame()
        code = Display.objects.get().pairing_code
        self.now = at(9, 5)
        self.frame()
        self.assertEqual(Display.objects.get().pairing_code, code)
        self.now = at(9, 11)
        with mock.patch.object(displays, "_new_code", return_value="ZZZZZZZZ"):
            r = self.frame()
        self.assertEqual(Display.objects.get().pairing_code, "ZZZZZZZZ")
        self.assertEqual(Display.objects.count(), 1)
        self.assertEqual(r.status_code, 200)

    def test_pending_cap_returns_429(self):
        for n in range(displays.MAX_PENDING):
            self.assertEqual(self.frame(secret(n)).status_code, 200)
        self.assertEqual(self.frame(secret(200)).status_code, 429)
        self.assertEqual(Display.objects.count(), displays.MAX_PENDING)
        # an already known pending display still works
        self.assertEqual(self.frame(secret(3)).status_code, 200)

    def test_codes_unique_among_unexpired(self):
        for n in range(20):
            self.frame(secret(n))
        codes = list(Display.objects.values_list("pairing_code", flat=True))
        self.assertEqual(len(set(codes)), 20)

    def test_collision_is_retried(self):
        self.frame(secret(1))
        first = Display.objects.get().pairing_code
        letters = iter(list(first) + list("BBBBBBBB"))
        with mock.patch.object(displays.secrets, "choice", side_effect=lambda a: next(letters)):
            self.frame(secret(2))
        self.assertEqual(
            Display.objects.get(secret_hash=displays.hash_secret(secret(2))).pairing_code,
            "BBBBBBBB",
        )

    def test_stale_unpaired_rows_are_cleaned(self):
        old = Display.objects.create(
            panel="2.1", secret_hash="o" * 64, last_seen_at=self.now - timedelta(days=2)
        )
        paired = Display.objects.create(
            panel="2.1", secret_hash="p" * 64, room=self.room,
            last_seen_at=self.now - timedelta(days=9),
        )
        self.frame()
        self.assertFalse(Display.objects.filter(pk=old.pk).exists())
        self.assertTrue(Display.objects.filter(pk=paired.pk).exists())

    def test_deleted_room_unpairs(self):
        self.pair()
        self.room.delete()
        r = self.frame()
        d = Display.objects.get()
        self.assertFalse(d.is_paired)
        self.assertEqual(len(d.pairing_code), 8)
        self.assertEqual(r["X-Next-Wake"], "30")
        self.assertEqual(self.event("top").status_code, 401)

    # frame
    def test_paired_frame_and_304(self):
        self.pair()
        r = self.frame()
        self.assertEqual(r.status_code, 200)
        etag = r["ETag"]
        self.assertEqual(Display.objects.get().last_etag, etag.strip('"'))
        self.assertGreater(int(r["X-Next-Wake"]), 0)
        self.assertEqual(r["X-Session-Timeout"], "0")
        r2 = self.client.get(FRAME, **self.hdr(HTTP_IF_NONE_MATCH=etag))
        self.assertEqual(r2.status_code, 304)
        self.assertEqual(r2["ETag"], etag)
        self.assertEqual(r2["X-Next-Wake"], r["X-Next-Wake"])
        self.assertIn("X-Session-Timeout", r2)
        # only the "Stand" stamp changes with the clock -> still 304
        self.now = at(9, 2)
        r3 = self.client.get(FRAME, **self.hdr(HTTP_IF_NONE_MATCH=etag))
        self.assertEqual(r3.status_code, 304)
        # a content change is a new frame
        self.book(self.d1, 9, 11)
        r4 = self.client.get(FRAME, **self.hdr(HTTP_IF_NONE_MATCH=etag))
        self.assertEqual(r4.status_code, 200)
        self.assertNotEqual(r4["ETag"], etag)

    def test_frame_scoped_to_room(self):
        self.pair(room=self.m1.room)
        self.book(self.d1, 9, 11)
        r = self.frame()
        from desksharing import door_session

        shown = door_session.current_screen(Display.objects.get(), self.now)
        expected = door_render.to_frame(door_render.render(shown, "5.79"))
        self.assertEqual(r.content, expected)
        self.assertNotIn("Max", [t.label for t in shown.view.desks])
        self.assertEqual(shown.view.desks, [])

    def test_telemetry_saved(self):
        self.pair()
        self.frame(HTTP_X_BATTERY_MV="3987", HTTP_X_FIRMWARE="0.3.1")
        d = Display.objects.get()
        self.assertEqual((d.battery_mv, d.firmware, d.last_seen_at), (3987, "0.3.1", self.now))
        self.frame(HTTP_X_BATTERY_MV="junk")
        self.assertEqual(Display.objects.get().battery_mv, 3987)

    def test_secret_not_stored_plain(self):
        self.pair()
        self.assertFalse(Display.objects.filter(secret_hash=secret(1)).exists())

    # events
    def test_event_checks_in(self):
        self.pair()
        res = self.book(self.d1, 9, 11)
        r = self.event("down")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["X-Session-Timeout"], "20")
        self.assertEqual(self.event("top").status_code, 200)
        res.refresh_from_db()
        self.assertIsNotNone(res.checked_in_at)
        self.assertEqual(res.status, Reservation.Status.ACTIVE)

    def test_event_unknown_secret_401(self):
        self.assertEqual(self.event("top").status_code, 401)
        self.assertEqual(Display.objects.count(), 0)
        Display.objects.create(panel="5.79", secret_hash=displays.hash_secret(secret(1)))
        self.assertEqual(self.event("top").status_code, 401)

    def test_event_bad_input_400(self):
        self.pair()
        self.assertEqual(self.event("explode").status_code, 400)
        r = self.client.post(EVENT, "{", content_type="application/json", **self.hdr())
        self.assertEqual(r.status_code, 400)

    def test_event_rate_limit_429(self):
        self.pair()
        with mock.patch("desksharing.views_display.door_session.press") as press:
            from desksharing import door_session

            press.side_effect = lambda d, b, n: door_session.current_screen(d, n)
            for _ in range(displays.EVENT_LIMIT):
                self.assertEqual(self.event("wake").status_code, 200)
            calls = press.call_count
            self.assertEqual(self.event("wake").status_code, 429)
            self.assertEqual(press.call_count, calls)
        self.now = at(9, 1)
        self.assertEqual(self.event("wake").status_code, 200)
