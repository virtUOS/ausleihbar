# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Item door signs: frames for every state on both panels (spec §6.5)."""
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from PIL import ImageChops

from desksharing import door_render
from desksharing.door_session import Screen
from desksharing.item_view import ItemSlot, ItemView, build_item_view
from desksharing.tests.test_item_view import add_item, at, make_item_fixture

PANELS = ("2.1", "5.79")
LONG_TITLE = "Großformat-Lasercutter Epilog Fusion Pro 48 mit Absaugung und Kühlung"


def screen(view):
    return Screen(view=view, mode="normal", selected=None, hours=0, confirm_text=None,
                  message=None, session_timeout=0)


def item_view(state, **kw):
    slot = ItemSlot(at(9), at(10), "R-00042")
    base = dict(
        title=LONG_TITLE, inventory_number="WERKSTATT-LASER-000042", state=state, now=at(9, 20),
        slot=None, late_minutes=None, release_at=None, next_start=None, next_open=None,
        upcoming=[], next_wake=300,
    )
    if state in ("reserved", "late", "in_use"):
        base["slot"] = slot
    if state == "late":
        base.update(late_minutes=128, release_at=at(9, 30))
    if state == "free":
        base["next_start"] = at(14)
    if state == "closed":
        base["next_open"] = at(8, day=3)
    base["upcoming"] = [ItemSlot(at(h), at(h + 1), f"R-{h:05d}") for h in (11, 13, 15)]
    base.update(kw)
    return ItemView(**base)


STATES = ("free", "reserved", "late", "in_use", "closed", "out_of_service")


class ItemRenderTests(SimpleTestCase):
    def test_every_state_renders_on_both_panels(self):
        for panel in PANELS:
            for state in STATES:
                image = door_render.render(screen(item_view(state)), panel)
                self.assertEqual(image.size, door_render.SIZES[panel], (panel, state))
                self.assertEqual(image.mode, "1")

    def test_free_without_reservation(self):
        for panel in PANELS:
            image = door_render.render(screen(item_view("free", next_start=None, upcoming=[])),
                                       panel)
            self.assertEqual(image.size, door_render.SIZES[panel])

    def test_free_and_late_differ(self):
        for panel in PANELS:
            free = door_render.render(screen(item_view("free")), panel)
            late = door_render.render(screen(item_view("late")), panel)
            self.assertIsNotNone(ImageChops.difference(free, late).getbbox())

    def test_inventory_number_keeps_its_end(self):
        """The 2.1" header shortens a long inventory number from the start so
        the distinguishing suffix stays visible; the title gives way first."""
        from PIL import Image, ImageDraw

        from desksharing.door_render_layouts import _item_header_texts

        draw = ImageDraw.Draw(Image.new("1", (250, 122)))
        view = item_view("free")
        title, inv = _item_header_texts(
            draw, view, 228, door_render.font(11, True), door_render.font(9)
        )
        self.assertEqual(inv, "WERKSTATT-LASER-000042")
        self.assertTrue(title.endswith("…"))
        view = item_view("free", inventory_number="WERKSTATT-LASERCUTTER-RAUM-12-000042")
        _, inv = _item_header_texts(
            draw, view, 228, door_render.font(11, True), door_render.font(9)
        )
        self.assertTrue(inv.startswith("…"), inv)
        self.assertTrue(inv.endswith("000042"), inv)

    def test_stamp_only_changes_with_stamp(self):
        for panel in PANELS:
            view = item_view("in_use")
            plain = door_render.render(screen(view), panel, stamp=False)
            stamped = door_render.render(screen(view), panel, stamp=True)
            self.assertIsNotNone(ImageChops.difference(plain, stamped).getbbox())
            later = item_view("in_use", now=at(9, 50))
            self.assertEqual(
                door_render.to_frame(plain),
                door_render.to_frame(door_render.render(screen(later), panel, stamp=False)),
            )


class ItemRenderPrivacyTests(TestCase):
    def setUp(self):
        make_item_fixture(self)

    def test_building_and_rendering_never_read_the_borrower(self):
        add_item(self, at(9), at(10))
        add_item(self, at(10), at(11))
        with CaptureQueriesContext(connection) as queries:
            view = build_item_view(self.resource, now=at(9, 20))
            for panel in PANELS:
                door_render.render(screen(view), panel)
        self.assertEqual(view.state, "late")
        user_table = "accounts_user"
        for query in queries.captured_queries:
            self.assertNotIn(user_table, query["sql"])
