# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from unittest import mock

from django.core.cache import cache, caches
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
        caches["throttle"].clear()

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
            self.assertEqual(self.frame(secret(n), REMOTE_ADDR=f"10.1.0.{n}").status_code, 200)
        self.assertEqual(self.frame(secret(200), REMOTE_ADDR="10.2.0.1").status_code, 429)
        self.assertEqual(Display.objects.count(), displays.MAX_PENDING)
        # an already known pending display still works
        self.assertEqual(self.frame(secret(3), REMOTE_ADDR="10.2.0.2").status_code, 200)

    def test_codes_unique_among_unexpired(self):
        for n in range(20):
            self.frame(secret(n), REMOTE_ADDR=f"10.1.0.{n}")
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
        self.now = at(9, 59)
        self.assertEqual(
            self.client.get(FRAME, **self.hdr(HTTP_IF_NONE_MATCH=etag)).status_code, 304
        )
        # a content change is a new frame
        self.book(self.d1, 9, 11)
        r4 = self.client.get(FRAME, **self.hdr(HTTP_IF_NONE_MATCH=etag))
        self.assertEqual(r4.status_code, 200)
        self.assertNotEqual(r4["ETag"], etag)

    def test_screen_etag_changes_with_the_local_hour(self):
        data = b"\x00" * 16
        same = door_render.screen_etag(data, at(9, 1))
        self.assertEqual(door_render.screen_etag(data, at(9, 59)), same)
        self.assertNotEqual(door_render.screen_etag(data, at(10)), same)
        self.assertNotEqual(door_render.screen_etag(b"\x01" * 16, at(9, 1)), same)

    def test_quiet_sign_redraws_hourly(self):
        self.pair()
        with mock.patch.object(
            door_render, "render", side_effect=lambda s, p, stamp=True: door_render.render_pairing(
                "SAMESAME", p
            ),
        ):
            etag = self.frame()["ETag"]
            self.now = at(9, 40)
            self.assertEqual(self.frame(HTTP_IF_NONE_MATCH=etag).status_code, 304)
            self.now = at(10, 0)
            r = self.frame(HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r["ETag"], etag)

    def test_frame_scoped_to_room(self):
        self.pair(secret(1), room=self.room)
        self.pair(secret(2), room=self.m1.room)
        self.book(self.d1, 9, 11)  # Max in room A (office)
        a, b = self.frame(secret(1)), self.frame(secret(2))
        self.assertNotEqual(a.content, b.content)
        from desksharing import door_session

        shown_b = door_session.current_screen(
            Display.objects.get(secret_hash=displays.hash_secret(secret(2))), self.now
        )
        labels = [t.label for t in shown_b.view.desks] + [str(shown_b.view.meeting)]
        self.assertNotIn("Max", " ".join(labels))
        self.assertEqual(
            b.content, door_render.to_frame(door_render.render(shown_b, "5.79"))
        )

    def test_hostile_headers_do_not_500(self):
        self.pair()
        r = self.frame(HTTP_X_BATTERY_MV="\xb2", HTTP_X_FIRMWARE="\xb2" + "x" * 99)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(Display.objects.get().battery_mv)
        self.assertLessEqual(len(Display.objects.get().firmware), 40)
        self.assertEqual(self.frame(secret(9), HTTP_X_BATTERY_MV="\xb2").status_code, 200)

    def test_pairing_requests_throttled_per_ip(self):
        for n in range(displays.PAIRING_LIMIT):
            # new devices up to the per-IP pending cap, then known ones re-poll
            sec = secret(min(n, displays.PENDING_PER_IP - 1))
            self.assertEqual(self.frame(sec).status_code, 200)
        r = self.frame(secret(100))
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r["Retry-After"], "60")
        self.assertEqual(Display.objects.count(), displays.PENDING_PER_IP)
        # a known pending display from the same IP is throttled too (no render/write)
        self.assertEqual(self.frame(secret(1)).status_code, 429)
        # other IPs and the next window are unaffected
        self.assertEqual(self.frame(secret(101), REMOTE_ADDR="10.0.0.9").status_code, 200)
        self.now = at(9, 1)
        self.assertEqual(self.frame(secret(1)).status_code, 200)

    def test_new_pending_capped_per_ip(self):
        for n in range(displays.PENDING_PER_IP):
            self.now = at(9, n % 2)  # stay under the per-minute pairing limit
            self.assertEqual(self.frame(secret(n)).status_code, 200)
        r = self.frame(secret(50))
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r["Retry-After"], str(displays.PENDING_IP_WINDOW))
        self.assertEqual(Display.objects.count(), displays.PENDING_PER_IP)
        # known pending displays of that IP keep polling; other IPs may pair
        self.assertEqual(self.frame(secret(0)).status_code, 200)
        self.assertEqual(self.frame(secret(51), REMOTE_ADDR="10.0.0.9").status_code, 200)
        # the next code lifetime frees the IP again
        self.now = at(9, 10)
        self.assertEqual(self.frame(secret(52)).status_code, 200)

    def test_paired_frame_requests_throttled(self):
        self.pair()
        for _ in range(displays.FRAME_LIMIT):
            self.assertEqual(self.frame().status_code, 200)
        r = self.frame()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r["Retry-After"], str(displays.FRAME_WINDOW))
        # another paired display is unaffected; the next window works again
        self.pair(secret(2), room=self.m1.room)
        self.assertEqual(self.frame(secret(2)).status_code, 200)
        self.now = at(9, 1)
        self.assertEqual(self.frame().status_code, 200)

    def test_paired_display_not_pairing_throttled(self):
        self.pair()
        for _ in range(displays.PAIRING_LIMIT + 5):
            self.assertEqual(self.frame().status_code, 200)

    def test_rotation_respects_pending_cap(self):
        self.frame(secret(1))
        for n in range(2, displays.MAX_PENDING + 1):
            displays.ensure_pending(secret(n), "5.79", self.now)
        self.assertEqual(
            Display.objects.filter(pairing_expires_at__gt=self.now).count(),
            displays.MAX_PENDING,
        )
        # the first display's code expires; the other 49 stay live ... so it rotates
        Display.objects.filter(secret_hash=displays.hash_secret(secret(1))).update(
            pairing_expires_at=self.now - timedelta(minutes=1)
        )
        # ... after a new pending row takes the free slot, rotation must be refused
        displays.ensure_pending(secret(99), "5.79", self.now)
        self.assertEqual(self.frame(secret(1)).status_code, 429)
        old = Display.objects.get(secret_hash=displays.hash_secret(secret(1)))
        self.assertLess(old.pairing_expires_at, self.now)
        self.assertEqual(
            Display.objects.filter(pairing_expires_at__gt=self.now).count(),
            displays.MAX_PENDING,
        )

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
