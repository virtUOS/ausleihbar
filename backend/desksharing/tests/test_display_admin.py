# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import io
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from catalog.models import Product, ProductType, Resource
from desksharing import displays, hours, privacy
from desksharing.models import Display, DisplayEvent, Room
from desksharing.tests.test_booking import setup_department
from desksharing.tests.test_rights import make_pool

User = get_user_model()
BASE = "/api/desks/manage/displays/"
FRAME = "/api/displays/frame/"
NOW = datetime(2027, 3, 2, 9, 0, tzinfo=hours.TZ)


def secret(n=0):
    return f"{n:02x}" * 32


class DisplayAdminTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.pool_b = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        self.room_b = Room.objects.create(floor=self.floor, pool=self.pool_b, name="RB")
        self.admin_b = User.objects.create_user("admin_b", password="x")
        self.pool_b.lender_group.members.add(self.admin_b)
        self.app_admin = User.objects.create_user("root", password="x", is_staff=True)
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.clear()
        caches["throttle"].clear()
        self.api = APIClient()
        self.api.force_authenticate(self.app_admin)
        self.dept_api = APIClient()
        self.dept_api.force_authenticate(self.lender)

    def pending(self, n=1, code="ABCD2345"):
        return Display.objects.create(
            panel="5.79", secret_hash=displays.hash_secret(secret(n)),
            pairing_code=code, pairing_expires_at=NOW + timedelta(minutes=5),
        )

    def paired(self, room=None, n=2, name="Door"):
        return Display.objects.create(
            panel="5.79", secret_hash=displays.hash_secret(secret(n)),
            room=room or self.room, name=name, paired_at=NOW, ui_state={"mode": "select"},
            last_etag="old",
        )

    def make_resource(self, number="WS-1", title="Laser", pool=None, selfservice=True, **kw):
        ptype, _ = ProductType.objects.get_or_create(name="T")
        product = Product.objects.create(
            product_type=ptype, title=title,
            use_type="onsite" if selfservice else "loan",
            requires_handout=not selfservice,
        )
        return Resource.objects.create(
            product=product, resource_pool=pool or self.pool, inventory_number=number,
            qr_code_id="QR-" + number, **kw,
        )

    def test_department_admin_forbidden(self):
        d = self.paired()
        self.pending()
        for call in (
            self.dept_api.get(BASE),
            self.dept_api.post(BASE + "claim/", {"code": "ABCD2345", "room": self.room.pk},
                               format="json"),
            self.dept_api.patch(f"{BASE}{d.pk}/", {"name": "x"}, format="json"),
            self.dept_api.delete(f"{BASE}{d.pk}/"),
            self.dept_api.get(f"{BASE}{d.pk}/preview.png"),
            self.dept_api.get(BASE + "resources/"),
        ):
            self.assertEqual(call.status_code, 403)
        self.assertTrue(Display.objects.filter(pk=d.pk).exists())

    def test_claim_with_resource(self):
        d = self.pending()
        res = self.make_resource()
        r = self.api.post(BASE + "claim/", {"code": "ABCD2345", "resource": res.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d.refresh_from_db()
        self.assertEqual((d.resource, d.room, d.last_etag), (res, None, ""))
        body = r.json()
        self.assertEqual(body["target_kind"], "resource")
        self.assertIsNone(body["room"])
        self.assertEqual(body["resource"], {
            "id": res.pk, "inventory_number": "WS-1", "product_title": "Laser",
            "pool": self.pool.pk})

    def test_claim_target_validation(self):
        self.pending()
        retired = self.make_resource("R-1", status=Resource.Status.RETIRED)
        loan = self.make_resource("L-1", selfservice=False)
        ok = self.make_resource("O-1")
        post = lambda body: self.api.post(  # noqa: E731
            BASE + "claim/", {"code": "ABCD2345", **body}, format="json")
        for body in ({}, {"room": self.room.pk, "resource": ok.pk}):
            r = post(body)
            self.assertEqual(r.status_code, 400)
            self.assertIn("target", r.json())
        for res in (retired, loan):
            r = post({"resource": res.pk})
            self.assertEqual(r.status_code, 400)
            self.assertIn("resource", r.json())
        self.assertEqual(post({"resource": 99999}).status_code, 400)
        self.assertEqual(Display.objects.get().pairing_code, "ABCD2345")

    def test_patch_switch_targets_resets_state(self):
        d = self.paired()
        res = self.make_resource()
        r = self.api.patch(f"{BASE}{d.pk}/", {"resource": res.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d.refresh_from_db()
        self.assertEqual((d.room, d.resource, d.ui_state, d.last_etag), (None, res, {}, ""))
        Display.objects.filter(pk=d.pk).update(ui_state={"a": 1}, last_etag="e")
        res2 = self.make_resource("WS-2")
        self.assertEqual(
            self.api.patch(f"{BASE}{d.pk}/", {"resource": res2.pk}, format="json").status_code, 200)
        d.refresh_from_db()
        self.assertEqual((d.resource, d.ui_state, d.last_etag), (res2, {}, ""))
        Display.objects.filter(pk=d.pk).update(ui_state={"a": 1}, last_etag="e")
        r = self.api.patch(f"{BASE}{d.pk}/", {"room": self.room.pk, "resource": None},
                           format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d.refresh_from_db()
        self.assertEqual((d.room, d.resource, d.last_etag), (self.room, None, ""))

    def test_patch_target_errors_and_rename_keeps_state(self):
        res = self.make_resource()
        d = self.paired()
        Display.objects.filter(pk=d.pk).update(resource=None)
        url = f"{BASE}{d.pk}/"
        self.assertEqual(self.api.patch(
            url, {"room": self.room.pk, "resource": res.pk}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(url, {"room": None}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(
            url, {"name": "Neu", "room": self.room.pk}, format="json").status_code, 200)
        d.refresh_from_db()
        self.assertEqual((d.name, d.room, d.last_etag), ("Neu", self.room, "old"))

    def test_item_display_list_filter_and_preview(self):
        res = self.make_resource(pool=self.pool_b)
        item = Display.objects.create(
            panel="5.79", secret_hash=displays.hash_secret(secret(7)), resource=res,
            name="Item", paired_at=NOW)
        room = self.paired(self.room, 2)
        rows = {x["id"]: x for x in self.api.get(BASE).json()}
        self.assertEqual(set(rows), {item.pk, room.pk})
        self.assertEqual(rows[item.pk]["target_kind"], "resource")
        self.assertEqual(rows[room.pk]["target_kind"], "room")
        self.assertEqual(rows[room.pk]["resource"], None)
        ids = lambda r: {x["id"] for x in r.json()}  # noqa: E731
        self.assertEqual(ids(self.api.get(BASE + f"?pool={self.pool_b.pk}")), {item.pk})
        self.assertEqual(ids(self.api.get(BASE + f"?pool={self.pool.pk}")), {room.pk})
        self.assertEqual(self.png_size(self.api.get(f"{BASE}{item.pk}/preview.png")), (792, 272))
        self.assertEqual(self.api.delete(f"{BASE}{item.pk}/").status_code, 204)

    def test_resource_search(self):
        a = self.make_resource("AAA-1", "Lasercutter")
        self.make_resource("BBB-1", "Drucker")
        self.make_resource("LOAN-1", "Lasercutter Leih", selfservice=False)
        self.make_resource("RET-1", "Lasercutter alt", status=Resource.Status.RETIRED)
        r = self.api.get(BASE + "resources/?search=laser")
        self.assertEqual([x["id"] for x in r.json()], [a.pk])
        self.assertEqual(r.json()[0], {
            "id": a.pk, "inventory_number": "AAA-1", "product_title": "Lasercutter",
            "pool_name": self.pool.name})
        self.assertEqual([x["inventory_number"] for x in self.api.get(
            BASE + "resources/?search=bbb").json()], ["BBB-1"])
        self.assertEqual(
            [x["product_title"] for x in self.api.get(BASE + "resources/").json()],
            ["Drucker", "Lasercutter"])

    def test_claim_pairs_and_clears_code(self):
        d = self.pending()
        r = self.api.post(
            BASE + "claim/", {"code": "abcd-23 45", "room": self.room.pk, "name": "Tür"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        d.refresh_from_db()
        self.assertEqual(d.room, self.room)
        self.assertEqual(d.name, "Tür")
        self.assertEqual(d.pairing_code, "")
        self.assertIsNone(d.pairing_expires_at)
        self.assertEqual(d.paired_at, NOW)
        self.assertEqual(d.last_etag, "")
        self.assertEqual(r.json()["room"], {
            "id": self.room.pk, "name": "R1", "floor": "EG", "building": "B1"})
        self.assertEqual(
            set(r.json()),
            {"id", "name", "panel", "room", "resource", "target_kind", "last_seen_at",
             "battery_mv", "firmware", "paired_at"},
        )

    def test_claim_unknown_or_expired_code_404(self):
        d = self.pending()
        r = self.api.post(BASE + "claim/", {"code": "ZZZZZZZZ", "room": self.room.pk}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (404, "unknown_code"))
        Display.objects.filter(pk=d.pk).update(pairing_expires_at=NOW - timedelta(seconds=1))
        r = self.api.post(BASE + "claim/", {"code": "ABCD2345", "room": self.room.pk}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_list_all_and_pool_filter(self):
        a = self.paired(self.room, 2)
        b = self.paired(self.room_b, 3)
        self.pending(4, "WXYZ2345")
        ids = lambda r: {x["id"] for x in r.json()}  # noqa: E731
        self.assertEqual(ids(self.api.get(BASE)), {a.pk, b.pk})
        self.assertEqual(ids(self.api.get(BASE + f"?pool={self.pool_b.pk}")), {b.pk})

    def test_unnamed_display_lists_fallback_name(self):
        d = self.paired(self.room, 2, name="")
        [row] = self.api.get(BASE).json()
        self.assertEqual(row["name"], f"Display {d.pk}")

    def test_patch_name_and_room(self):
        d = self.paired()
        other = Room.objects.create(floor=self.floor, pool=self.pool, name="R2")
        r = self.api.patch(f"{BASE}{d.pk}/", {"name": "Neu", "room": other.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d.refresh_from_db()
        self.assertEqual((d.name, d.room), ("Neu", other))
        self.assertEqual((d.ui_state, d.last_etag), ({}, ""))

    def test_non_admin_forbidden(self):
        self.api.force_authenticate(self.member)
        self.assertEqual(self.api.get(BASE).status_code, 403)

    def test_revoke_then_device_gets_pairing_frame(self):
        d = self.paired(n=1)
        hdr = {"HTTP_AUTHORIZATION": f"Bearer {secret(1)}", "HTTP_X_PANEL": "5.79"}
        self.assertEqual(self.client.get(FRAME, **hdr).status_code, 200)
        self.assertEqual(self.api.delete(f"{BASE}{d.pk}/").status_code, 204)
        self.assertFalse(Display.objects.filter(pk=d.pk).exists())
        r = self.client.get(FRAME, **hdr)
        self.assertEqual(r["X-Next-Wake"], "30")
        self.assertFalse(Display.objects.get().is_paired)

    def png_size(self, r):
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(r["Cache-Control"], "no-store")
        return Image.open(io.BytesIO(r.content)).size

    def test_display_preview_png(self):
        d = self.paired()
        self.assertEqual(self.png_size(self.api.get(f"{BASE}{d.pk}/preview.png")), (792, 272))

    def test_room_preview_png(self):
        url = f"/api/desks/manage/rooms/{self.room.pk}/door-preview.png"
        self.assertEqual(self.png_size(self.api.get(url)), (792, 272))
        self.assertEqual(self.png_size(self.api.get(url + "?panel=2.1")), (250, 122))
        self.assertEqual(self.api.get(url + "?panel=9").status_code, 400)
        rb = f"/api/desks/manage/rooms/{self.room_b.pk}/door-preview.png"
        self.assertEqual(self.api.get(rb).status_code, 200)  # app admin
        # department admins keep the room preview, within their own rooms
        self.assertEqual(self.png_size(self.dept_api.get(url)), (792, 272))
        self.assertEqual(self.dept_api.get(rb).status_code, 403)

    def test_display_events_retention(self):
        def event(pool, days):
            e = DisplayEvent.objects.create(display_label="x", pool=pool, action="book")
            DisplayEvent.objects.filter(pk=e.pk).update(created_at=NOW - timedelta(days=days))
            return e.pk

        old = event(self.pool, 91)
        fresh = event(self.pool, 10)
        old_none = event(None, 91)
        counts = privacy.anonymize_due(NOW)
        self.assertEqual(counts["display_events"], 2)
        self.assertEqual(
            set(DisplayEvent.objects.values_list("pk", flat=True)), {fresh}
        )
        self.assertNotIn(old, [fresh])
        self.assertNotIn(old_none, [fresh])
