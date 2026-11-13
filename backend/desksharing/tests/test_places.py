# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import rights
from desksharing.models import DeskSettings, Feature, Floor, Place, Room
from desksharing.tests.test_rights import make_pool

User = get_user_model()
BASE = "/api/desks/manage"


class PlaceTestBase(TestCase):
    def setUp(self):
        self.group = AccessGroup.objects.create(name="Dept A")
        self.pool = make_pool("PoolA", self.group)
        self.other_pool = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        self.lender = User.objects.create_user("lender", password="x")
        self.pool.lender_group.members.add(self.lender)
        self.member = User.objects.create_user("member", password="x")
        self.group.members.add(self.member)
        self.floor = Floor.objects.create(pool=self.pool, building="B1", name="EG")
        self.room = Room.objects.create(floor=self.floor, name="R1")
        self.client = APIClient()
        self.client.force_authenticate(self.lender)

    def desk(self, name="D1", **kw):
        return Place.objects.create(room=self.room, name=name, **kw)


class PlaceRightsTests(PlaceTestBase):
    def test_restricted_place(self):
        gf = AccessGroup.objects.create(name="GF")
        place = self.desk()
        place.access_groups.add(gf)
        self.assertFalse(rights.can_book_place(self.member, place))
        gf.members.add(self.member)
        self.member = User.objects.get(pk=self.member.pk)
        self.assertTrue(rights.can_book_place(self.member, place))
        self.assertTrue(rights.can_book_place(self.lender, place))

    def test_open_place_for_pool_member(self):
        self.assertTrue(rights.can_book_place(self.member, self.desk()))
        outsider = User.objects.create_user("out", password="x")
        self.assertFalse(rights.can_book_place(outsider, self.desk(name="D2")))

    def test_assistant_pools_require_enabled(self):
        assistants = AccessGroup.objects.create(name="Assist")
        user = User.objects.create_user("assist", password="x")
        assistants.members.add(user)
        s = DeskSettings.for_pool(self.pool)
        s.assistant_group = assistants
        s.enabled = False
        s.save()
        self.assertNotIn(self.pool.pk, rights.assistant_pool_ids(user))
        s.enabled = True
        s.save()
        user = User.objects.get(pk=user.pk)
        self.assertIn(self.pool.pk, rights.assistant_pool_ids(user))


class PlaceApiTests(PlaceTestBase):
    def test_lender_of_other_pool_gets_404(self):
        other = User.objects.create_user("l2", password="x")
        self.other_pool.lender_group.members.add(other)
        self.client.force_authenticate(other)
        place = self.desk()
        for url in (
            f"{BASE}/places/{place.pk}/",
            f"{BASE}/floors/{self.floor.pk}/",
            f"{BASE}/rooms/{self.room.pk}/",
        ):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/settings/{self.pool.pk}/").status_code, 404)
        r = self.client.post(
            f"{BASE}/rooms/", {"floor": self.floor.pk, "name": "X"}, format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_non_admin_forbidden(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(f"{BASE}/places/").status_code, 403)

    def test_meeting_room_requires_capacity(self):
        data = {"room": self.room.pk, "kind": "meeting_room", "name": "M1"}
        self.assertEqual(self.client.post(f"{BASE}/places/", data, format="json").status_code, 400)
        data["capacity"] = 8
        r = self.client.post(f"{BASE}/places/", data, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_plan_rejects_unknown_shape_type(self):
        url = f"{BASE}/floors/{self.floor.pk}/plan/"
        bad = {"plan": {"shapes": [{"id": "a", "type": "sofa", "points": None}]}}
        self.assertEqual(self.client.put(url, bad, format="json").status_code, 400)
        bad = {"plan": {"shapes": [{"id": "a", "type": "wall", "points": [["x", 1]]}]}}
        self.assertEqual(self.client.put(url, bad, format="json").status_code, 400)
        good = {"plan": {"shapes": [
            {"id": "a", "type": "room", "points": [[0, 0], [1, 0], [1, 1]],
             "text": None, "room_id": self.room.pk}
        ]}}
        self.assertEqual(self.client.put(url, good, format="json").status_code, 200)
        self.floor.refresh_from_db()
        self.assertEqual(self.floor.plan["shapes"][0]["id"], "a")

    def test_qr_token_unique_and_regenerable(self):
        a, b = self.desk(), self.desk(name="D2")
        self.assertNotEqual(a.qr_token, b.qr_token)
        old = a.qr_token
        r = self.client.post(f"{BASE}/places/{a.pk}/regenerate-qr/")
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertNotEqual(a.qr_token, old)

    def test_delete_without_reservations_is_hard(self):
        place = self.desk()
        self.assertEqual(self.client.delete(f"{BASE}/places/{place.pk}/").status_code, 204)
        self.assertFalse(Place.objects.filter(pk=place.pk).exists())

    def test_feature_of_other_pool_rejected(self):
        f = Feature.objects.create(pool=self.other_pool, name="Dock")
        data = {"room": self.room.pk, "name": "D3", "features": [f.pk]}
        self.assertEqual(self.client.post(f"{BASE}/places/", data, format="json").status_code, 400)

    def test_settings_validation_and_rights_refresh(self):
        url = f"{BASE}/settings/{self.pool.pk}/"
        self.assertEqual(self.client.get(url).status_code, 200)
        hours = {str(d): [6, 20] for d in range(7)}
        hours["6"] = None
        r = self.client.put(url, {"business_hours": hours, "enabled": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        hours["1"] = [5, 20]
        self.assertEqual(self.client.put(url, {"business_hours": hours}, format="json").status_code, 400)
        self.assertEqual(
            self.client.put(url, {"business_hours": {"0": None}}, format="json").status_code, 400
        )

    def test_settings_put_refreshes_cached_rights(self):
        assistants = AccessGroup.objects.create(name="Assist")
        user = User.objects.create_user("assist", password="x")
        assistants.members.add(user)
        self.assertNotIn(self.pool.pk, rights.assistant_pool_ids(user))  # primes the memo
        r = self.client.put(
            f"{BASE}/settings/{self.pool.pk}/",
            {"assistant_group": assistants.pk},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn(self.pool.pk, rights.assistant_pool_ids(user))  # same user object

    def test_settings_enable_needs_access_group(self):
        pool = make_pool("Open", enabled=False)
        pool.lender_group.members.add(self.lender)
        r = self.client.put(f"{BASE}/settings/{pool.pk}/", {"enabled": True}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_app_admin_enables_not_yet_enabled_pool(self):
        group = AccessGroup.objects.create(name="Dept C")
        pool = make_pool("PoolC", group, enabled=False)
        admin = User.objects.create_superuser("root", password="x")
        self.client.force_authenticate(admin)
        url = f"{BASE}/settings/{pool.pk}/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.put(url, {"enabled": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(DeskSettings.objects.get(pool=pool).enabled)
        pool.is_active = False
        pool.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_template_upload_is_private_and_admin_gated(self):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, "PNG")
        url = f"{BASE}/floors/{self.floor.pk}/template/"
        up = SimpleUploadedFile("t.png", buf.getvalue(), content_type="image/png")
        r = self.client.post(url, {"file": up}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn("/media/", r.content.decode())
        self.assertEqual(r.json()["template_url"], url)
        bad = SimpleUploadedFile("t.png", b"nope", content_type="image/png")
        self.assertEqual(self.client.post(url, {"file": bad}, format="multipart").status_code, 400)
        # Admin of the pool gets the bytes.
        got = self.client.get(url)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got["Content-Type"], "image/png")
        self.assertTrue(got.content.startswith(b"\x89PNG"))
        listing = self.client.get(f"{BASE}/floors/").content.decode()
        self.assertNotIn("/media/", listing)
        self.assertNotIn("template_data", listing)
        # Other pool's admin: 404; plain member: 403; anonymous: denied.
        other = User.objects.create_user("l2", password="x")
        self.other_pool.lender_group.members.add(other)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(url).status_code, (401, 403))


class FixedOwnerSyncTests(PlaceTestBase):
    """Changing a place's fixed owner keeps ``Reservation.owner_use`` right
    for reservations not yet ended."""

    def test_owner_change_recomputes_owner_use(self):
        from datetime import timedelta
        from unittest import mock

        from django.utils import timezone

        from desksharing import release
        from desksharing.models import Reservation

        desk = self.desk()
        now = timezone.now()

        def reserve(start, end):
            return Reservation.objects.create(
                place=desk, holder=self.member, booked_by=self.member,
                period=(now + start, now + end),
            )

        running = reserve(timedelta(hours=-1), timedelta(hours=1))
        future = reserve(timedelta(days=2), timedelta(days=2, hours=1))
        ended = reserve(timedelta(days=-2), timedelta(days=-2, hours=-1) + timedelta(hours=2))
        self.assertFalse(running.owner_use)
        url = f"{BASE}/places/{desk.pk}/"
        # Assign the member as fixed owner through the admin place API.
        r = self.client.patch(url, {"fixed_owner": self.member.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        for res in (running, future, ended):
            res.refresh_from_db()
        self.assertEqual((running.owner_use, future.owner_use, ended.owner_use),
                         (True, True, False))
        # One desk, none free: scarce. The owner's running reservation survives.
        with mock.patch("desksharing.notify.notify"):
            release.tick(now)
        running.refresh_from_db()
        self.assertEqual(running.status, Reservation.Status.ACTIVE)
        self.assertFalse(running.no_show)
        # Remove the owner: not-ended rows lose owner_use, ended ones keep it.
        Reservation.objects.filter(pk=ended.pk).update(owner_use=True)
        r = self.client.patch(url, {"fixed_owner": None}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        for res in (running, future, ended):
            res.refresh_from_db()
        self.assertEqual((running.owner_use, future.owner_use, ended.owner_use),
                         (False, False, True))
        # Saving other fields leaves owner_use alone (no extra work).
        desk.refresh_from_db()
        desk.name = "D1b"
        desk.save(update_fields=["name"])
        future.refresh_from_db()
        self.assertFalse(future.owner_use)
