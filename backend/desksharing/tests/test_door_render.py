# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Door display renderer: sizes, frame format, stable ETags, text fitting."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from PIL import Image, ImageChops, ImageDraw

from desksharing import door_render, door_render_layouts
from desksharing.door_session import Screen
from desksharing.door_view import DeskTile, DoorView, MeetingInfo, MeetingSlot
from desksharing.hours import TZ

NOW = datetime(2026, 11, 23, 10, 40, tzinfo=TZ)
LONG_NAME = "Maximilian-Alexander von Hohenzollern-Sigmaringen"


def at(hour, minute=0):
    return NOW.replace(hour=hour, minute=minute)


def tile(i, state="free", label=None, until=None, free_note=None, actionable=None):
    booked = state != "free" or actionable is not None  # free + check-in window open
    return DeskTile(
        place_id=i, name=f"Platz {i}", state=state, label=label, until=until,
        free_note=free_note, reservation_id=(100 + i) if booked else None,
        actionable=actionable, qr_url=f"https://example.org/desks/q/token{i}",
    )


def office_tiles(count):
    states = [
        ("checked_in", "Jana Hoffmann", "check_out"),
        ("free", None, None),
        ("booked", "belegt", None),
        ("potentially_free", "Lea Schulz", "check_in"),
    ]
    out = []
    for i in range(count):
        state, label, action = states[i % len(states)]
        out.append(tile(
            i + 1, state, label=label, actionable=action,
            until=at(11) if i == 3 else None,
            free_note="ab 13:00 gebucht" if state == "free" and i == 1 else None,
        ))
    return out


def meeting_info(state):
    schedule = [
        MeetingSlot(at(15), at(16, 30), "Team Lehre"),
        MeetingSlot(at(16, 30), at(17), "frei"),
        MeetingSlot(at(17), at(18), "Marco Kaya"),
        MeetingSlot(at(18), at(20), "frei"),
    ]
    common = dict(
        max_hours=4, qr_url="https://example.org/desks/q/meet", schedule=schedule,
        next_label="15:00–16:30 Team Lehre",
    )
    if state == "free":
        return MeetingInfo(
            state="free", title=None, holder=None, start=None, end=None,
            free_until=at(15), release_at=None, reservation_id=None, **common,
        )
    checked = state == "checked_in"
    return MeetingInfo(
        state=state, title="Projekttreffen Lehrportal", holder="Jana Hoffmann",
        start=at(10), end=at(15), free_until=None,
        release_at=None if checked else at(10, 15), reservation_id=7, **common,
    )


def view(kind, desks=(), meeting=None, **extra):
    desks = list(desks)
    free = sum(1 for d in desks if d.state == "free")
    return DoorView(
        room_name="Büro 15/2.06", kind=kind, now=NOW, desks=desks, meeting=meeting,
        free_count=free, total=len(desks) or 1,
        room_qr_url="https://example.org/desks?room=1" if free else None,
        next_wake=300, **extra,
    )


def screen(v, mode="normal", selected=None, confirm_text=None, message=None):
    return Screen(
        view=v, mode=mode, selected=selected, hours=2, confirm_text=confirm_text,
        message=message, session_timeout=0 if mode == "normal" else 20,
    )


def all_screens():
    """Every kind / state / mode combination the renderer must handle."""
    out = {}
    for state in ("free", "booked", "checked_in"):
        out[f"meeting-{state}"] = screen(view("meeting", meeting=meeting_info(state)))
    out["meeting-select"] = screen(view("meeting", meeting=meeting_info("free")), mode="select")
    out["meeting-confirm"] = screen(
        view("meeting", meeting=meeting_info("checked_in")), mode="confirm",
        confirm_text="Meeting beenden?",
    )
    out["meeting-message"] = screen(
        view("meeting", meeting=meeting_info("free")), message="Belegt bis 12:00"
    )
    for count in (2, 3, 4, 8, 11):
        out[f"office-{count}"] = screen(view("office", office_tiles(count)))
    taken = [tile(i, "checked_in", label="Murat Kaya") for i in range(1, 5)]
    out["office-4-full"] = screen(view("office", taken))
    out["office-select-free"] = screen(view("office", office_tiles(4)), mode="select", selected=1)
    out["office-select-booked"] = screen(view("office", office_tiles(4)), mode="select", selected=3)
    out["office-confirm"] = screen(
        view("office", office_tiles(4)), mode="confirm", selected=0,
        confirm_text="Jana Hoffmann auschecken?",
    )
    out["office-message"] = screen(view("office", office_tiles(4)), message="Eingecheckt ✓")
    out["single-booked"] = screen(
        view("single", [tile(1, "booked", label="Jana Hoffmann", actionable="check_in")])
    )
    out["single-checked-in"] = screen(
        view("single", [tile(1, "checked_in", label="Jana Hoffmann", actionable="check_out")])
    )
    out["single-confirm"] = screen(
        view("single", [tile(1, "checked_in", label="Jana Hoffmann", actionable="check_out")]),
        mode="confirm", confirm_text="Jana Hoffmann auschecken?",
    )
    out["single-free"] = screen(
        view("single", [tile(1, "free", free_note="ab 13:00 gebucht")])
    )
    out["single-closed"] = screen(view("single", [tile(1, "closed")]))
    out["empty"] = screen(view("empty"))
    out["closed"] = screen(view(
        "closed", next_open=at(8) + timedelta(days=1),
        next_booking=MeetingSlot(
            at(9) + timedelta(days=1), at(11) + timedelta(days=1), "Team Lehre"
        ),
    ))
    out["closed-nothing"] = screen(view("closed"))
    out["office-no-desks"] = screen(view("office"))
    # Free now, but the next booking's check-in window is open (Task 4 checks in).
    out["single-pending"] = screen(view("single", [
        tile(1, "free", free_note="ab 10:45 gebucht", actionable="check_in")
    ]))
    pending_tiles = office_tiles(4)
    pending_tiles[1] = tile(2, "free", free_note="ab 10:45 gebucht", actionable="check_in")
    out["office-select-pending"] = screen(view("office", pending_tiles), mode="select", selected=1)
    pending = meeting_info("free")
    pending.reservation_id, pending.free_until = 9, at(10, 45)
    pending.next_label = "10:45–12:00 Projekttreffen Lehrportal"
    out["meeting-pending"] = screen(view("meeting", meeting=pending))
    many = [tile(i, "checked_in", label="Murat Kaya") for i in range(1, 10)] + [tile(10), tile(11)]
    out["office-hidden-free"] = screen(view("office", many))
    out["meeting-missing"] = screen(view("meeting"))
    # Degenerate / edge data.
    no_title = meeting_info("checked_in")
    no_title.title = None
    out["meeting-no-title"] = screen(view("meeting", meeting=no_title))
    anon = meeting_info("checked_in")
    anon.title, anon.holder = "Spontan belegt", None
    out["meeting-anonymous"] = screen(view("meeting", meeting=anon))
    full = meeting_info("free")
    full.max_hours, full.schedule, full.free_until = 0, [], None
    out["meeting-no-hours"] = screen(view("meeting", meeting=full))
    maybe = meeting_info("booked")
    maybe.state = "potentially_free"
    out["meeting-potentially-free"] = screen(view("meeting", meeting=maybe))
    closed = meeting_info("free")
    closed.state, closed.free_until = "closed", None
    out["meeting-closed"] = screen(view("meeting", meeting=closed))
    for count in (1, 5, 7):
        out[f"office-{count}"] = screen(view("office", office_tiles(count)))
    nolabel = office_tiles(4)
    nolabel[2].label = None
    out["office-no-label"] = screen(view("office", nolabel))
    out["office-select-taken"] = screen(view("office", office_tiles(4)), mode="select", selected=2)
    out["office-select-11"] = screen(view("office", office_tiles(11)), mode="select", selected=10)
    out["single-select"] = screen(
        view("single", [tile(1, "booked", label=LONG_NAME, actionable="check_in")]), mode="select"
    )
    return out


class RenderSizeTests(SimpleTestCase):
    def test_sizes_and_mode(self):
        for name, scr in all_screens().items():
            for panel, size in door_render.SIZES.items():
                with self.subTest(screen=name, panel=panel):
                    image = door_render.render(scr, panel)
                    self.assertEqual(image.mode, "1")
                    self.assertEqual(image.size, size)

    def test_long_title_renders(self):
        info = meeting_info("checked_in")
        info.title = "x" * 200
        info.holder = LONG_NAME
        scr = screen(view("meeting", meeting=info))
        for panel in door_render.SIZES:
            self.assertEqual(door_render.render(scr, panel).size, door_render.SIZES[panel])

    def test_pairing_frame_contains_dark_pixels(self):
        for panel, size in door_render.SIZES.items():
            image = door_render.render_pairing("ABCD2345", panel)
            self.assertEqual(image.size, size)
            self.assertEqual(image.mode, "1")
            self.assertGreater(image.histogram()[0], 100)

    def test_message_frame(self):
        for panel, size in door_render.SIZES.items():
            image = door_render.render_message("Kein buchbarer Platz", panel)
            self.assertEqual(image.size, size)
            self.assertGreater(image.histogram()[0], 50)


class TimezoneTests(SimpleTestCase):
    def test_utc_inputs_render_local_time(self):
        """Datetimes arrive in UTC from the database; output must not depend on it."""
        utc = ZoneInfo("UTC")
        for name in ("meeting-free", "meeting-booked", "office-4", "closed"):
            with self.subTest(screen=name):
                local = all_screens()[name]
                shifted = all_screens()[name]
                v = shifted.view
                v.now = v.now.astimezone(utc)
                if v.next_open:
                    v.next_open = v.next_open.astimezone(utc)
                if v.next_booking:
                    v.next_booking.start = v.next_booking.start.astimezone(utc)
                    v.next_booking.end = v.next_booking.end.astimezone(utc)
                for t in v.desks:
                    t.until = t.until.astimezone(utc) if t.until else None
                if v.meeting:
                    m = v.meeting
                    for f in ("start", "end", "free_until", "release_at"):
                        if getattr(m, f):
                            setattr(m, f, getattr(m, f).astimezone(utc))
                    for slot in m.schedule:
                        slot.start, slot.end = slot.start.astimezone(utc), slot.end.astimezone(utc)
                for panel in door_render.SIZES:
                    self.assertEqual(
                        door_render.render(local, panel).tobytes(),
                        door_render.render(shifted, panel).tobytes(),
                    )


class FrameFormatTests(SimpleTestCase):
    def test_frame_bytes_length(self):
        scr = all_screens()["office-4"]
        self.assertEqual(len(door_render.to_frame(door_render.render(scr, "5.79"))), 99 * 272)
        self.assertEqual(len(door_render.to_frame(door_render.render(scr, "2.1"))), 32 * 122)

    def test_bit_order(self):
        image = Image.new("1", (9, 1), 1)
        image.putpixel((0, 0), 0)
        data = door_render.to_frame(image)
        self.assertEqual(data, bytes([0x80, 0x00]))
        image.putpixel((8, 0), 0)
        self.assertEqual(door_render.to_frame(image), bytes([0x80, 0x80]))

    def test_white_is_zero(self):
        self.assertEqual(door_render.to_frame(Image.new("1", (16, 2), 1)), bytes(4))

    def test_etag_stable(self):
        for name, scr in all_screens().items():
            with self.subTest(screen=name):
                first = door_render.to_frame(door_render.render(scr, "5.79"))
                second = door_render.to_frame(door_render.render(scr, "5.79"))
                self.assertEqual(door_render.frame_etag(first), door_render.frame_etag(second))
        etag = door_render.frame_etag(b"abc")
        self.assertEqual(len(etag), 64)
        self.assertNotEqual(etag, door_render.frame_etag(b"abd"))


class FitTextTests(SimpleTestCase):
    def setUp(self):
        self.draw = ImageDraw.Draw(Image.new("1", (10, 10), 1))

    def width(self, text, font):
        return self.draw.textlength(text, font=font)

    def test_long_texts_stay_in_box(self):
        cases = (
            ("x" * 200, 400, False), (LONG_NAME, 220, True), (LONG_NAME, 60, True),
            ("x" * 200, 30, False), (LONG_NAME, 300, False),
        )
        for text, box, name in cases:
            with self.subTest(text=text[:20], box=box):
                fitted, font = door_render.fit_text(self.draw, text, box, (40, 30, 22), name=name)
                self.assertLessEqual(self.width(fitted, font), box)
                self.assertTrue(
                    fitted.endswith("…") or fitted == "M. von Hohenzollern-Sigmaringen",
                    fitted,
                )

    def test_short_form_for_names(self):
        # DejaVu Sans Bold 22 px: "Jana Hoffmann" 185 px, "J. Hoffmann" 147 px.
        fitted, font = door_render.fit_text(self.draw, "Jana Hoffmann", 150, (22,), name=True)
        self.assertEqual(fitted, "J. Hoffmann")
        fitted, font = door_render.fit_text(self.draw, "Jana Hoffmann", 190, (22,), name=True)
        self.assertEqual(fitted, "Jana Hoffmann")

    def test_no_short_form_for_titles(self):
        fitted, font = door_render.fit_text(self.draw, "Jana Hoffmann", 150, (22,))
        self.assertTrue(fitted.endswith("…"), fitted)
        self.assertLessEqual(self.width(fitted, font), 150)

    def test_largest_size_that_fits(self):
        fitted, font = door_render.fit_text(self.draw, "FREI", 500, (40, 30, 22))
        self.assertEqual(fitted, "FREI")
        self.assertEqual(font.size, 40)


class UserTextTests(SimpleTestCase):
    """Free texts (comments, names) may hold newlines, tabs or be very long."""

    def test_whitespace_in_user_texts(self):
        info = meeting_info("booked")
        info.holder = "Jana\nHoffmann"
        info.title = "Projekt\ttreffen\nLehrportal"
        info.next_label = "10:45–12:00 Team\nLehre"
        info.schedule[0].label = "Team\nLehre\twöchentlich"
        info.schedule[2].label = "x" * 200
        pending = meeting_info("free")
        pending.reservation_id, pending.next_label = 9, "10:45–12:00 a\nb\tc"
        tiles = office_tiles(4)
        tiles[0].label, tiles[0].name = "Jana\nHoffmann", "Platz\n1"
        screens = [
            screen(view("meeting", meeting=info)),
            screen(view("meeting", meeting=pending)),
            screen(view("office", tiles)),
            screen(view("office", tiles), mode="select", selected=0),
            screen(view("single", [tile(1, "booked", label="Jana\tHoffmann")])),
        ]
        for scr in screens:
            for panel in door_render.SIZES:
                self.assertEqual(door_render.render(scr, panel).size, door_render.SIZES[panel])

    def test_fit_text_and_truncate_accept_newlines(self):
        draw = ImageDraw.Draw(Image.new("1", (10, 10), 1))
        text, font = door_render.fit_text(draw, "a\nb", 300, (13,), bold=False)
        self.assertEqual(text, "a b")
        self.assertTrue(door_render.truncate(draw, "x\n" * 100, 50, font).endswith("…"))


def diff_box(a, b):
    return ImageChops.difference(a.convert("L"), b.convert("L")).getbbox()


def inside(box, area):
    return box is None or (
        box[0] >= area[0] and box[1] >= area[1] and box[2] <= area[2] and box[3] <= area[3]
    )


class TextStaysInBoxTests(SimpleTestCase):
    """A 200-char title and a very long name change only their own box:
    every pixel outside it (hint column, neighbours) matches a short-text
    render."""

    LONG_TITLE = "Projekttreffen " * 14

    def assert_confined(self, short, long, panel, area):
        a, b = door_render.render(short, panel), door_render.render(long, panel)
        box = diff_box(a, b)
        self.assertIsNotNone(box)  # the long text is drawn at all
        self.assertTrue(inside(box, area), f"{panel}: changed {box}, allowed {area}")

    def meeting_pair(self, state):
        short, long = meeting_info(state), meeting_info(state)
        long.title, long.holder = self.LONG_TITLE, LONG_NAME
        return screen(view("meeting", meeting=short)), screen(view("meeting", meeting=long))

    def test_meeting(self):
        for state in ("booked", "checked_in"):
            with self.subTest(state=state):
                short, long = self.meeting_pair(state)
                # Left state area only (divider at x=450 untouched).
                self.assert_confined(short, long, "5.79", (0, 0, 450, 272))
                # 2.1" summary shows neither title nor holder.
                a = door_render.render(short, "2.1")
                self.assertIsNone(diff_box(a, door_render.render(long, "2.1")))

    def test_office_tile(self):
        def build(label):
            tiles = [tile(1, "checked_in", label=label)] + [tile(i) for i in range(2, 5)]
            return screen(view("office", tiles))
        # 4 tiles + QR side: 2x2 grid from x=14, y=50; tile 1 = (14, 50)–(317, 150).
        self.assert_confined(build("Jana Hoffmann"), build(LONG_NAME), "5.79", (14, 50, 317, 150))

    def test_single(self):
        def build(label):
            return screen(view("single", [tile(1, "booked", label=label, actionable="check_in")]))
        # 2.1": below the header rule (y=22..23), left of the hint column
        # (x=232); x from 4 because bold glyphs overhang the 8 px margin by 1 px.
        self.assert_confined(build("Jana Hoffmann"), build(LONG_NAME), "2.1", (4, 24, 226, 104))
        # 5.79": inside the single tile (no side column while taken).
        self.assert_confined(build("Jana Hoffmann"), build(LONG_NAME), "5.79", (14, 50, 762, 262))

    def test_summary_room_name(self):
        short = screen(view("office", office_tiles(4)))
        long = screen(view("office", office_tiles(4)))
        long.view.room_name = "Büro " + "x" * 200
        # 2.1" summary header line only, left of "Stand".
        self.assert_confined(short, long, "2.1", (8, 0, 180, 22))


class StampTests(SimpleTestCase):
    def test_stamp_free_render_ignores_minutes(self):
        for name in ("meeting-free", "office-4", "single-free", "office-confirm", "closed", "empty"):
            with self.subTest(screen=name):
                a, b = all_screens()[name], all_screens()[name]
                b.view.now = a.view.now + timedelta(minutes=7)
                for panel in door_render.SIZES:
                    self.assertEqual(
                        door_render.to_frame(door_render.render(a, panel, stamp=False)),
                        door_render.to_frame(door_render.render(b, panel, stamp=False)),
                    )
                self.assertNotEqual(
                    door_render.render(a, "5.79").tobytes(), door_render.render(b, "5.79").tobytes()
                )

    def test_stamp_is_restored(self):
        scr = all_screens()["office-4"]
        door_render.render(scr, "5.79", stamp=False)
        self.assertTrue(door_render.stand(scr.view))


class HintTests(SimpleTestCase):
    def test_plus_by_upper_rocker_half(self):
        self.assertTrue(door_render_layouts.HINT_DURATION.startswith("+"))
        self.assertTrue(door_render_layouts.HINT_SELECT.startswith("▲"))

    def office_hints(self, tiles):
        from unittest import mock

        with mock.patch.object(
            door_render_layouts, "draw_hints", wraps=door_render_layouts.draw_hints
        ) as hints:
            door_render.render(screen(view("office", tiles)), "5.79")
        return hints.call_args.args[2]

    def test_office_normal_shows_rocker_when_actionable(self):
        self.assertEqual(self.office_hints(office_tiles(4))[1], door_render_layouts.HINT_SELECT)
        quiet = [tile(1), tile(2, state="booked", label="belegt")]
        self.assertEqual(self.office_hints(quiet)[1], "")
