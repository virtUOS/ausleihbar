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
        self.api.force_authenticate(self.lender)

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
            {"id", "name", "panel", "room", "last_seen_at", "battery_mv", "firmware", "paired_at"},
        )

    def test_claim_unknown_or_expired_code_404(self):
        d = self.pending()
        r = self.api.post(BASE + "claim/", {"code": "ZZZZZZZZ", "room": self.room.pk}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (404, "unknown_code"))
        Display.objects.filter(pk=d.pk).update(pairing_expires_at=NOW - timedelta(seconds=1))
        r = self.api.post(BASE + "claim/", {"code": "ABCD2345", "room": self.room.pk}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_claim_foreign_room_403(self):
        d = self.pending()
        r = self.api.post(BASE + "claim/", {"code": "ABCD2345", "room": self.room_b.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        d.refresh_from_db()
        self.assertIsNone(d.room_id)

    def test_list_only_own_departments(self):
        a = self.paired(self.room, 2)
        b = self.paired(self.room_b, 3)
        self.pending(4, "WXYZ2345")
        ids = lambda r: {x["id"] for x in r.json()}  # noqa: E731
        self.assertEqual(ids(self.api.get(BASE)), {a.pk})
        self.api.force_authenticate(self.app_admin)
        self.assertEqual(ids(self.api.get(BASE)), {a.pk, b.pk})
        self.assertEqual(ids(self.api.get(BASE + f"?pool={self.pool_b.pk}")), {b.pk})

    def test_patch_name_room_and_foreign(self):
        d = self.paired()
        other = Room.objects.create(floor=self.floor, pool=self.pool, name="R2")
        r = self.api.patch(f"{BASE}{d.pk}/", {"name": "Neu", "room": other.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d.refresh_from_db()
        self.assertEqual((d.name, d.room), ("Neu", other))
        self.assertEqual((d.ui_state, d.last_etag), ({}, ""))
        r = self.api.patch(f"{BASE}{d.pk}/", {"room": self.room_b.pk}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_foreign_display_404(self):
        b = self.paired(self.room_b, 3)
        self.assertEqual(self.api.patch(f"{BASE}{b.pk}/", {"name": "x"}, format="json").status_code, 404)
        self.assertEqual(self.api.delete(f"{BASE}{b.pk}/").status_code, 404)
        self.assertEqual(self.api.get(f"{BASE}{b.pk}/preview.png").status_code, 404)
        self.assertTrue(Display.objects.filter(pk=b.pk).exists())

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
        self.assertEqual(self.api.get(rb).status_code, 403)

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
