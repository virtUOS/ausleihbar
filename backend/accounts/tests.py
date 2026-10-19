# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for accounts / OIDC claim and group mapping."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from catalog.models import Resource, ResourcePool

User = get_user_model()


class ManageUserApiTests(APITestCase):
    """Admin-only user-management API: roles and pool memberships."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(
            username="alice", email="alice@uni-osnabrueck.de", first_name="Alice"
        )
        self.pool_a = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        self.pool_b = ResourcePool.objects.create(name="Podcast", pool_id="Podcast")

    def test_list_requires_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/users/").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/api/manage/users/").status_code, 200)

    def test_search_by_name_or_email(self):
        self.client.force_login(self.admin)
        res = self.client.get("/api/manage/users/", {"search": "alice@uni"})
        usernames = [u["username"] for u in res.json()["results"]]
        self.assertEqual(usernames, ["alice"])

    def test_active_filter_excludes_inactive_users(self):
        User.objects.create_user(username="alice_old", first_name="Alice", is_active=False)
        self.client.force_login(self.admin)
        res = self.client.get("/api/manage/users/", {"search": "alice", "active": "1"})
        self.assertEqual([u["username"] for u in res.json()["results"]], ["alice"])
        res = self.client.get("/api/manage/users/", {"search": "alice"})
        self.assertEqual(
            sorted(u["username"] for u in res.json()["results"]), ["alice", "alice_old"]
        )

    def test_promote_to_admin_sets_staff_and_superuser(self):
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/manage/users/{self.borrower.id}/",
            {"is_admin": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_admin"])
        self.borrower.refresh_from_db()
        self.assertTrue(self.borrower.is_staff)
        self.assertTrue(self.borrower.is_superuser)

    def test_cannot_remove_own_admin_rights(self):
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/manage/users/{self.admin.id}/",
            {"is_admin": False},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    @override_settings(OIDC_ADMIN_GROUP="ausleihbar-admins", OIDC_GROUPS_CLAIM="groups")
    def test_cannot_demote_oidc_admin(self):
        oidc_admin = User.objects.create_user(
            username="idpadmin", subject="sub-123", is_staff=True, is_superuser=True,
            claims={"groups": ["ausleihbar-admins"]},
        )
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/manage/users/{oidc_admin.id}/",
            {"is_admin": False},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        oidc_admin.refresh_from_db()
        self.assertTrue(oidc_admin.is_staff)
        self.assertTrue(oidc_admin.is_superuser)

    @override_settings(OIDC_ADMIN_GROUP="ausleihbar-admins", OIDC_GROUPS_CLAIM="groups")
    def test_admin_via_oidc_flag_reported(self):
        oidc_admin = User.objects.create_user(
            username="idpadmin2", subject="sub-456", is_staff=True, is_superuser=True,
            claims={"groups": ["ausleihbar-admins"]},
        )
        local_admin = User.objects.create_user(
            username="localadmin", is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)
        self.assertTrue(
            self.client.get(f"/api/manage/users/{oidc_admin.id}/").json()["admin_via_oidc"]
        )
        self.assertFalse(
            self.client.get(f"/api/manage/users/{local_admin.id}/").json()["admin_via_oidc"]
        )

    @override_settings(OIDC_ADMIN_GROUP="ausleihbar-admins", OIDC_GROUPS_CLAIM="groups")
    def test_locally_promoted_admin_can_still_be_demoted(self):
        # is_staff set in-app, not via the IdP group → still editable here.
        local_admin = User.objects.create_user(
            username="localadmin2", is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/manage/users/{local_admin.id}/",
            {"is_admin": False},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        local_admin.refresh_from_db()
        self.assertFalse(local_admin.is_staff)

    def test_set_pools_syncs_lender_memberships(self):
        self.client.force_login(self.admin)
        # Assign two pools -> becomes a lender.
        res = self.client.put(
            f"/api/manage/users/{self.borrower.id}/pools/",
            {"pool_ids": [self.pool_a.id, self.pool_b.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["is_lender"])
        self.assertEqual(len(body["managed_pools"]), 2)

        # Drop one pool.
        res = self.client.put(
            f"/api/manage/users/{self.borrower.id}/pools/",
            {"pool_ids": [self.pool_a.id]},
            format="json",
        )
        pools = [m["pool"] for m in res.json()["managed_pools"]]
        self.assertEqual(pools, [self.pool_a.id])

        # Empty list removes all memberships -> no longer a lender.
        res = self.client.put(
            f"/api/manage/users/{self.borrower.id}/pools/",
            {"pool_ids": []},
            format="json",
        )
        self.assertFalse(res.json()["is_lender"])
        from accounts.models import AccessGroup

        self.assertFalse(
            AccessGroup.objects.filter(
                system_pool__isnull=False, members=self.borrower
            ).exists()
        )

    def test_set_pools_rejects_unknown_pool(self):
        self.client.force_login(self.admin)
        res = self.client.put(
            f"/api/manage/users/{self.borrower.id}/pools/",
            {"pool_ids": [99999]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class PoolEligibilityTests(APITestCase):
    """Group→pool access rules gate shop visibility and booking (concept §3.4)."""

    def setUp(self):
        from catalog.models import Product, ProductType, Resource
        from accounts.models import AccessGroup

        self.AccessGroup = AccessGroup
        ptype = ProductType.objects.create(name="Camera")

        # Open pool (no access groups) and a restricted pool (gated by a group).
        self.open_pool = ResourcePool.objects.create(name="Open", pool_id="OPEN")
        self.restricted_pool = ResourcePool.objects.create(name="Locked", pool_id="LOCK")
        self.group = AccessGroup.objects.create(name="Music")
        self.group.pools.add(self.restricted_pool)

        # Product only in the open pool, and one only in the restricted pool.
        self.open_product = Product.objects.create(product_type=ptype, title="Open Cam")
        Resource.objects.create(
            product=self.open_product, resource_pool=self.open_pool,
            inventory_number="OPEN-1", qr_code_id="QR-OPEN-1",
        )
        self.locked_product = Product.objects.create(product_type=ptype, title="Locked Cam")
        Resource.objects.create(
            product=self.locked_product, resource_pool=self.restricted_pool,
            inventory_number="LOCK-1", qr_code_id="QR-LOCK-1",
        )

        self.member = User.objects.create_user(username="member")
        self.group.members.add(self.member)
        self.outsider = User.objects.create_user(username="outsider")

    def _titles(self, response):
        return {p["title"] for p in response.json()["results"]}

    def test_anonymous_sees_only_open_pool_products(self):
        titles = self._titles(self.client.get("/api/products/"))
        self.assertIn("Open Cam", titles)
        self.assertNotIn("Locked Cam", titles)

    def test_outsider_cannot_see_restricted_product(self):
        self.client.force_login(self.outsider)
        self.assertNotIn("Locked Cam", self._titles(self.client.get("/api/products/")))

    def test_member_sees_restricted_product(self):
        self.client.force_login(self.member)
        self.assertIn("Locked Cam", self._titles(self.client.get("/api/products/")))

    def test_product_without_resources_is_hidden(self):
        from catalog.models import Product, ProductType

        ptype = ProductType.objects.create(name="Empty")
        Product.objects.create(product_type=ptype, title="Ghost Cam")
        self.assertNotIn("Ghost Cam", self._titles(self.client.get("/api/products/")))

    def test_product_with_only_unavailable_resources_is_hidden(self):
        from catalog.models import Product, ProductType, Resource

        ptype = ProductType.objects.create(name="Broken")
        product = Product.objects.create(product_type=ptype, title="Blocked Cam")
        Resource.objects.create(
            product=product, resource_pool=self.open_pool,
            status=Resource.Status.BLOCKED,
            inventory_number="BLK-1", qr_code_id="QR-BLK-1",
        )
        titles = self._titles(self.client.get("/api/products/"))
        self.assertNotIn("Blocked Cam", titles)
        # Adding an available unit makes it appear again.
        Resource.objects.create(
            product=product, resource_pool=self.open_pool,
            inventory_number="BLK-2", qr_code_id="QR-BLK-2",
        )
        self.assertIn("Blocked Cam", self._titles(self.client.get("/api/products/")))

    def test_restricted_availability_is_404_for_outsider(self):
        self.client.force_login(self.outsider)
        res = self.client.get(
            f"/api/products/{self.locked_product.id}/availability/"
            "?start=2026-07-01&end=2026-07-02"
        )
        self.assertEqual(res.status_code, 404)

    def test_outsider_cannot_add_restricted_product_to_cart(self):
        self.client.force_login(self.outsider)
        res = self.client.post(
            "/api/cart/items/",
            {"product": self.locked_product.id, "start": "2026-07-01", "end": "2026-07-02"},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_claim_based_membership(self):
        from accounts.eligibility import eligible_pool_ids

        self.group.claim_key = "groups"
        self.group.claim_values = ["music"]
        self.group.save()
        claimed = User.objects.create_user(username="claimed", claims={"groups": ["music"]})
        self.assertIn(self.restricted_pool.id, eligible_pool_ids(claimed))
        self.assertNotIn(self.restricted_pool.id, eligible_pool_ids(self.outsider))

    def test_lender_of_restricted_pool_has_access(self):
        from accounts.eligibility import eligible_pool_ids
        from accounts.testing import make_lender

        lender = User.objects.create_user(username="lender")
        make_lender(lender, self.restricted_pool)
        self.assertIn(self.restricted_pool.id, eligible_pool_ids(lender))

    def test_admin_only_access_group_crud(self):
        admin = User.objects.create_user(username="boss", is_staff=True, is_superuser=True)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get("/api/manage/access-groups/").status_code, 403)
        self.client.force_login(admin)
        created = self.client.post(
            "/api/manage/access-groups/",
            {"name": "Staff", "pools": [self.restricted_pool.id]},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["pool_names"], ["Locked"])

    def test_set_user_groups_action(self):
        admin = User.objects.create_user(username="boss2", is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        res = self.client.put(
            f"/api/manage/users/{self.outsider.id}/groups/",
            {"group_ids": [self.group.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual([g["id"] for g in res.json()["groups"]], [self.group.id])


class UserBookingHistoryTests(APITestCase):
    """Per-user booking history grouped into upcoming/handed-out/completed."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from catalog.models import Product, ProductType
        from lending.models import Booking
        from lending.services import create_reservation

        self.Booking = Booking
        self._create = create_reservation
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="GoPro")
        self.pool = ResourcePool.objects.create(
            name="DigiLab", pool_id="DigiLab", max_booking_months=0
        )
        self.resources = [
            Resource.objects.create(
                product=product, resource_pool=self.pool,
                inventory_number=f"DigiLab-{i:03d}", qr_code_id=f"QR-{i}",
            )
            for i in range(4)
        ]
        self.now = timezone.now()
        self.day = timedelta(days=1)

    def _booking(self, resource, status, offset_days=1):
        start = self.now + self.day * offset_days
        booking = self._create(
            self.borrower, [(resource, start, start + self.day)],
            status=self.Booking.Status.PENDING,
        )
        self.Booking.objects.filter(pk=booking.pk).update(status=status)
        return booking

    def test_groups_split_by_status_and_name_devices(self):
        self._booking(self.resources[0], self.Booking.Status.PENDING, 1)
        self._booking(self.resources[1], self.Booking.Status.CONFIRMED, 2)
        self._booking(self.resources[2], self.Booking.Status.HANDED_OUT, 3)
        self._booking(self.resources[3], self.Booking.Status.RETURNED, 4)

        self.client.force_login(self.admin)
        base = f"/api/manage/users/{self.borrower.id}/bookings/"

        upcoming = self.client.get(base, {"group": "upcoming"}).json()
        self.assertEqual(upcoming["count"], 2)
        # Devices are named on each item.
        names = upcoming["results"][0]["items"][0]
        self.assertIn("inventory_number", names)
        self.assertTrue(names["inventory_number"])

        self.assertEqual(
            self.client.get(base, {"group": "handed_out"}).json()["count"], 1
        )
        self.assertEqual(
            self.client.get(base, {"group": "completed"}).json()["count"], 1
        )

    def test_completed_is_paginated(self):
        # 12 returned bookings on one resource across distinct days.
        for offset in range(1, 13):
            self._booking(self.resources[0], self.Booking.Status.RETURNED, offset)
        self.client.force_login(self.admin)
        page1 = self.client.get(
            f"/api/manage/users/{self.borrower.id}/bookings/",
            {"group": "completed"},
        ).json()
        self.assertEqual(page1["count"], 12)
        self.assertEqual(len(page1["results"]), 10)
        self.assertIsNotNone(page1["next"])

    def test_requires_admin(self):
        self.client.force_login(self.borrower)
        res = self.client.get(
            f"/api/manage/users/{self.borrower.id}/bookings/?group=upcoming"
        )
        self.assertEqual(res.status_code, 403)


class StrikeFixtureMixin:
    """A lender of pool A, a borrower with a confirmed booking there, and a
    tight strike policy (2 strikes → 7-day block)."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import StrikeSetting
        from accounts.testing import make_lender
        from catalog.models import Product, ProductType
        from lending.services import create_reservation

        self.create_reservation = create_reservation
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(
            username="alice", email="alice@uni.test"
        )
        self.pool = ResourcePool.objects.create(
            name="A", pool_id="A", closed_weekdays=[], max_booking_months=0
        )
        make_lender(self.lender, self.pool)
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Cam")
        self.resource = Resource.objects.create(
            product=product, resource_pool=self.pool,
            inventory_number="A-1", qr_code_id="QR-A-1",
        )
        now = timezone.now()
        self.booking = self.create_reservation(
            self.borrower, [(self.resource, now, now + timedelta(days=1))],
            status="confirmed",
        )
        # Tight policy so 2 strikes already block for 7 days.
        s = StrikeSetting.load()
        s.thresholds = [{"count": 2, "block_days": 7}]
        s.save()


class StrikeTests(StrikeFixtureMixin, APITestCase):
    """Issuing strikes, escalation to a block, enforcement and admin controls."""

    def test_reason_required(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/", {"booking": self.booking.id}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_strike_links_to_booking_and_borrower_sees_it(self):
        # A strike issued over a booking is tied to it, and the borrower's own
        # bookings list flags that reservation (concept §7.3).
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"booking": self.booking.id, "reason": "late return"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.strikes.count(), 1)

        self.client.force_login(self.borrower)
        res = self.client.get("/api/bookings/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        rows = data["results"] if isinstance(data, dict) else data
        mine = next(b for b in rows if b["id"] == self.booking.id)
        self.assertTrue(mine["has_strike"])
        self.assertEqual(mine["strike_reason"], "late return")

    def test_lender_strikes_via_managed_booking_and_escalates_to_block(self):
        self.client.force_login(self.lender)
        for _ in range(2):
            res = self.client.post(
                "/api/manage/strikes/",
                {"booking": self.booking.id, "reason": "late return"},
                format="json",
            )
            self.assertEqual(res.status_code, 201)
        self.borrower.refresh_from_db()
        self.assertTrue(self.borrower.is_blocked())

    def test_lender_cannot_strike_foreign_booking(self):
        other_pool = ResourcePool.objects.create(name="B", pool_id="B")
        other_res = Resource.objects.create(
            product=self.resource.product, resource_pool=other_pool,
            inventory_number="B-1", qr_code_id="QR-B-1",
        )
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        foreign = self.create_reservation(
            self.borrower, [(other_res, now, now + timedelta(days=1))],
            status="confirmed",
        )
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"booking": foreign.id, "reason": "x"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_lender_cannot_strike_via_booking_of_another_pool(self):
        # M4: the permission check is the booking's own resource_pool (a
        # reservation belongs to exactly one pool, #26) — not merely whether
        # one of its items happens to sit in a managed pool. Force a booking
        # whose canonical pool is "other_pool" but whose single item was
        # moved onto a resource in the lender's managed pool (the kind of
        # inconsistency the old item-based check would have missed).
        from django.utils import timezone
        from datetime import timedelta

        other_pool = ResourcePool.objects.create(name="B", pool_id="B")
        other_res = Resource.objects.create(
            product=self.resource.product, resource_pool=other_pool,
            inventory_number="B-2", qr_code_id="QR-B-2",
        )
        # Use a period well clear of self.booking's [now, now+1d) so moving
        # the item onto self.resource below doesn't collide with it.
        later = timezone.now() + timedelta(days=10)
        booking = self.create_reservation(
            self.borrower, [(other_res, later, later + timedelta(days=1))],
            status="confirmed",
        )
        self.assertEqual(booking.resource_pool_id, other_pool.id)
        item = booking.items.get()
        item.resource = self.resource  # in self.pool, managed by self.lender
        item.save(update_fields=["resource"])

        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"booking": booking.id, "reason": "x"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_lender_cannot_strike_via_cart_booking(self):
        # A cart isn't a submitted reservation yet — reject it outright (M4).
        from django.utils import timezone
        from datetime import timedelta

        later = timezone.now() + timedelta(days=10)
        cart = self.create_reservation(
            self.borrower, [(self.resource, later, later + timedelta(days=1))],
            status="cart",
        )
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"booking": cart.id, "reason": "x"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_lender_strikes_borrower_by_user_in_managed_pool(self):
        # From the borrower profile a lender may strike a borrower who has a
        # booking in a pool they manage (no booking id needed).
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"user": self.borrower.id, "reason": "late"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)

    def test_lender_cannot_strike_user_outside_their_pools(self):
        stranger = User.objects.create_user(username="stranger")
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"user": stranger.id, "reason": "x"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_blocked_user_cannot_submit_cart(self):
        from django.utils import timezone
        from datetime import timedelta

        self.borrower.blocked_until = timezone.now() + timedelta(days=3)
        self.borrower.save()
        self.client.force_login(self.borrower)
        res = self.client.post(
            "/api/cart/items/",
            {"product": self.resource.product.id,
             "start": "2027-01-01", "end": "2027-01-02"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_only_admin_deletes_strike_and_unblocks(self):
        from accounts.strikes import issue_strike

        strike = issue_strike(self.borrower, "x", self.lender)
        self.client.force_login(self.lender)
        self.assertEqual(
            self.client.delete(f"/api/manage/strikes/{strike.id}/").status_code, 403
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.delete(f"/api/manage/strikes/{strike.id}/").status_code, 204
        )
        # Unblock action clears suspension.
        from django.utils import timezone
        from datetime import timedelta

        self.borrower.blocked_until = timezone.now() + timedelta(days=5)
        self.borrower.save()
        res = self.client.post(f"/api/manage/users/{self.borrower.id}/unblock/")
        self.assertEqual(res.status_code, 200)
        self.borrower.refresh_from_db()
        self.assertFalse(self.borrower.is_blocked())

    def test_strike_email_uses_borrower_language(self):
        # The strike notification follows the borrower's shop language (#25).
        from accounts.strikes import issue_strike
        from django.core import mail

        self.borrower.email = "b@example.org"
        self.borrower.language = "de"
        self.borrower.save(update_fields=["email", "language"])
        mail.outbox = []
        issue_strike(self.borrower, "zu spät", self.lender)
        self.assertTrue(mail.outbox)
        self.assertIn("Strike erhalten", mail.outbox[0].subject)
        # Same frame as the booking mails (#82): greeting, link, sign-off.
        body = mail.outbox[0].body
        self.assertTrue(body.startswith("Hallo "), body)
        self.assertIn("Grund: zu spät", body)
        self.assertIn("Deine Buchungen ansehen: ", body)
        self.assertIn("/bookings", body)
        self.assertIn("— Ausleihbar", body)

        self.borrower.language = "en"
        self.borrower.save(update_fields=["language"])
        mail.outbox = []
        issue_strike(self.borrower, "late", self.lender)
        self.assertIn("You received a strike", mail.outbox[0].subject)
        body = mail.outbox[0].body
        self.assertTrue(body.startswith("Hi "), body)
        self.assertIn("Reason: late", body)
        self.assertIn("View your bookings: ", body)
        self.assertIn("— Ausleihbar", body)

    def test_strike_email_shows_block_end_with_time(self):
        from datetime import timedelta

        from django.core import mail
        from django.utils import timezone, translation

        from accounts.models import StrikeSetting
        from accounts.strikes import issue_strike
        from lending.notifications import format_date

        setting = StrikeSetting.load()
        setting.thresholds = [{"count": 1, "block_days": 7}]
        setting.save()
        self.borrower.email = "b@example.org"
        self.borrower.language = "de"
        self.borrower.save(update_fields=["email", "language"])
        mail.outbox = []
        issue_strike(self.borrower, "zu spät", self.lender)
        self.borrower.refresh_from_db()
        with translation.override("de"):
            until = format_date(self.borrower.blocked_until, with_time=True)
        self.assertRegex(until, r"^\w\w\., \d\d\.\d\d\.\d{4}, \d\d:\d\d$")
        self.assertIn(f"bis zum {until} gesperrt", mail.outbox[0].body)
        self.assertGreater(self.borrower.blocked_until, timezone.now() + timedelta(days=6))

    def test_strike_setting_admin_only(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/strike-setting/").status_code, 403
        )
        self.client.force_login(self.admin)
        res = self.client.put(
            "/api/manage/strike-setting/",
            {"strike_expiry_days": 200, "thresholds": [{"count": 3, "block_days": 14}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["strike_expiry_days"], 200)


class StrikeUxTests(StrikeFixtureMixin, APITestCase):
    """Strike note, the richer strike mail and its preview (#139)."""

    def setUp(self):
        from accounts.models import StrikeSetting, default_strike_thresholds

        super().setUp()
        # Default escalation: 3 → 30 days, 5 → 180 days, 7 → permanent.
        s = StrikeSetting.load()
        s.thresholds = default_strike_thresholds()
        s.strike_expiry_days = 365
        s.save()
        self.setting = s
        self.pool.email = "verleih@uni.test"
        self.pool.phone = "0541 123"
        self.pool.save(update_fields=["email", "phone"])
        self.borrower.language = "de"
        self.borrower.save(update_fields=["language"])
        self.code = self.booking.code or f"#{self.booking.id}"

    def _add_strikes(self, n, user=None):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import Strike

        for _ in range(n):
            Strike.objects.create(
                user=user or self.borrower, reason="old", issued_by=self.lender,
                expires_at=timezone.now() + timedelta(days=100),
            )

    def _mail(self, **kwargs):
        from datetime import timedelta

        from django.utils import timezone, translation

        from accounts.strikes import strike_mail

        values = {
            "reason": "zu spät",
            "note": "",
            "booking": self.booking,
            "expires_at": timezone.now() + timedelta(days=365),
            "active_count": 1,
            "blocked_until": None,
            "blocked_permanently": False,
        }
        values.update(kwargs)
        with translation.override("de"):
            return strike_mail(self.borrower, **values)

    # --- note -----------------------------------------------------------

    def test_note_is_stored_and_returned(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/",
            {"booking": self.booking.id, "reason": "late", "note": "Bitte pünktlich."},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["note"], "Bitte pünktlich.")
        self.assertEqual(self.borrower.strikes.get().note, "Bitte pünktlich.")

    # --- threshold helpers ----------------------------------------------

    def test_block_for_count_and_next_step(self):
        from accounts.strikes import block_for_count, next_step

        self.assertIsNone(block_for_count(2, self.setting))
        self.assertEqual(block_for_count(3, self.setting), (False, 30))
        self.assertEqual(block_for_count(4, self.setting), (False, 30))
        self.assertEqual(block_for_count(7, self.setting), (True, 0))
        self.assertEqual(next_step(2, self.setting), {"count": 3, "block_days": 30})
        self.assertEqual(next_step(3, self.setting), {"count": 5, "block_days": 180})
        self.assertIsNone(next_step(7, self.setting))

    def test_projected_block_saves_nothing(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.strikes import projected_block

        self._add_strikes(2)
        now = timezone.now()
        projected = projected_block(self.borrower, now)
        self.assertEqual(projected["active_after"], 3)
        self.assertFalse(projected["blocked_permanently"])
        self.assertEqual(projected["blocked_until"], now + timedelta(days=30))
        self.assertEqual(self.borrower.strikes.count(), 2)
        self.borrower.refresh_from_db()
        self.assertIsNone(self.borrower.blocked_until)
        self.assertFalse(self.borrower.blocked_permanently)

    def test_projected_block_keeps_longer_existing_block(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.strikes import projected_block

        self._add_strikes(2)
        later = timezone.now() + timedelta(days=90)
        self.borrower.blocked_until = later
        self.borrower.save(update_fields=["blocked_until"])
        projected = projected_block(self.borrower)
        self.assertEqual(projected["blocked_until"], later)

    def test_projected_block_permanent_step(self):
        from accounts.strikes import projected_block

        self._add_strikes(6)
        projected = projected_block(self.borrower)
        self.assertEqual(projected["active_after"], 7)
        self.assertTrue(projected["blocked_permanently"])

    def test_projected_block_without_step(self):
        from accounts.strikes import projected_block

        projected = projected_block(self.borrower)
        self.assertEqual(projected["active_after"], 1)
        self.assertFalse(projected["blocked_permanently"])
        self.assertIsNone(projected["blocked_until"])

    # --- mail text ------------------------------------------------------

    def test_mail_with_booking(self):
        subject, text = self._mail(note="Bitte pünktlich.", active_count=1)
        self.assertEqual(subject, f"Strike zu deiner Buchung {self.code}")
        self.assertIn(
            f"das Verleihteam von A hat dir wegen deiner Buchung {self.code} "
            "einen Strike gegeben.",
            text,
        )
        self.assertIn("Grund: zu spät", text)
        self.assertIn("Eine Nachricht vom Verleihteam:\nBitte pünktlich.", text)
        self.assertIn("Dieser Strike läuft am ", text)
        self.assertIn("Du hast derzeit 1 aktiven Strike.", text)
        self.assertIn(
            "Ab 3 aktiven Strikes wird dein Konto für 30 Tage gesperrt.", text
        )
        # The pool's short contact block.
        self.assertIn("Kontakt: 0541 123 / verleih@uni.test", text)

    def test_mail_without_note_has_no_note_block(self):
        _subject, text = self._mail(active_count=2)
        self.assertNotIn("Eine Nachricht vom Verleihteam", text)
        self.assertIn("Du hast derzeit 2 aktive Strikes.", text)

    def test_mail_block_line_variants(self):
        from datetime import timedelta

        from django.utils import timezone

        _s, text = self._mail(
            active_count=3, blocked_until=timezone.now() + timedelta(days=30)
        )
        self.assertIn("Dein Konto ist bis zum ", text)
        self.assertNotIn("Ab 5 aktiven", text)

        _s, text = self._mail(active_count=7, blocked_permanently=True)
        self.assertIn("Dein Konto ist jetzt dauerhaft gesperrt.", text)

        _s, text = self._mail(active_count=6)
        self.assertIn("Ab 7 aktiven Strikes wird dein Konto dauerhaft gesperrt.", text)

        _s, text = self._mail(active_count=8)
        self.assertIn("Es gilt noch keine Ausleihsperre.", text)

    def test_mail_without_booking(self):
        subject, text = self._mail(booking=None)
        self.assertEqual(subject, "Du hast einen Strike erhalten")
        self.assertIn("deinem Konto wurde ein Strike hinzugefügt.", text)
        self.assertNotIn("Kontakt:", text)

    # --- preview --------------------------------------------------------

    def test_preview_matches_sent_mail(self):
        from unittest.mock import patch

        from django.core import mail
        from django.utils import timezone

        from accounts.models import Strike

        self._add_strikes(2)
        payload = {
            "booking": self.booking.id, "reason": "zu spät", "note": "Bitte pünktlich.",
        }
        self.client.force_login(self.lender)
        frozen = timezone.now()
        mail.outbox = []
        with patch("django.utils.timezone.now", return_value=frozen):
            preview = self.client.post(
                "/api/manage/strikes/preview/", payload, format="json"
            )
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(len(mail.outbox), 0)
            self.assertEqual(Strike.objects.filter(user=self.borrower).count(), 2)
            res = self.client.post("/api/manage/strikes/", payload, format="json")
        self.assertEqual(res.status_code, 201)
        data = preview.json()
        self.assertEqual(data["active_after"], 3)
        self.assertTrue(data["will_send"])
        self.assertFalse(data["blocked_permanently"])
        self.assertIsNotNone(data["blocked_until"])
        self.assertEqual(data["subject"], mail.outbox[0].subject)
        self.assertEqual(data["body"] + "\n", mail.outbox[0].body)
        self.assertIn("Grund: zu spät", data["body"])

    def test_preview_saves_nothing_and_allows_empty_reason(self):
        from django.core import mail

        from accounts.models import Strike

        self.client.force_login(self.lender)
        mail.outbox = []
        res = self.client.post(
            "/api/manage/strikes/preview/",
            {"booking": self.booking.id, "reason": ""},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("Grund: …", res.json()["body"])
        self.assertFalse(Strike.objects.exists())
        self.borrower.refresh_from_db()
        self.assertIsNone(self.borrower.blocked_until)

    def test_preview_will_send_false_without_email(self):
        self.borrower.email = ""
        self.borrower.save(update_fields=["email"])
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/preview/",
            {"booking": self.booking.id, "reason": "late"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["will_send"])

    def test_mail_one_day_step_is_singular(self):
        self.setting.thresholds = [{"count": 2, "block_days": 1}]
        self.setting.save()
        _s, text = self._mail(active_count=1)
        self.assertIn("Ab 2 aktiven Strikes wird dein Konto für 1 Tag gesperrt.", text)

    def test_preview_in_english_for_english_borrower(self):
        self.borrower.language = "en"
        self.borrower.save(update_fields=["language"])
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/preview/",
            {"user": self.borrower.id, "reason": "late"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["subject"], "You received a strike")
        self.assertTrue(res.json()["body"].startswith("Hi "))

    def test_preview_permissions(self):
        from datetime import timedelta

        from django.utils import timezone

        other_pool = ResourcePool.objects.create(name="B", pool_id="B")
        other_res = Resource.objects.create(
            product=self.resource.product, resource_pool=other_pool,
            inventory_number="B-1", qr_code_id="QR-B-1",
        )
        now = timezone.now()
        foreign = self.create_reservation(
            self.borrower, [(other_res, now, now + timedelta(days=1))],
            status="confirmed",
        )
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/strikes/preview/",
            {"booking": foreign.id, "reason": "x"}, format="json",
        )
        self.assertEqual(res.status_code, 403)
        stranger = User.objects.create_user(username="stranger")
        res = self.client.post(
            "/api/manage/strikes/preview/",
            {"user": stranger.id, "reason": "x"}, format="json",
        )
        self.assertEqual(res.status_code, 403)
        res = self.client.post(
            "/api/manage/strikes/preview/", {"reason": "x"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.client.force_login(self.borrower)
        res = self.client.post(
            "/api/manage/strikes/preview/",
            {"booking": self.booking.id, "reason": "x"}, format="json",
        )
        self.assertEqual(res.status_code, 403)


class UserRoleFilterTests(APITestCase):
    """The ?role= filter on the user list (for the clickable role badges)."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.testing import make_lender

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.lender = User.objects.create_user(username="len")
        pool = ResourcePool.objects.create(name="A", pool_id="A")
        make_lender(self.lender, pool)
        self.inactive = User.objects.create_user(username="ghost", is_active=False)
        self.blocked = User.objects.create_user(username="banned")
        self.blocked.blocked_until = timezone.now() + timedelta(days=5)
        self.blocked.save()
        self.client.force_login(self.admin)

    def _usernames(self, role):
        res = self.client.get("/api/manage/users/", {"role": role})
        return {u["username"] for u in res.json()["results"]}

    def test_filters(self):
        self.assertEqual(self._usernames("admin"), {"boss"})
        self.assertEqual(self._usernames("lender"), {"len"})
        self.assertEqual(self._usernames("inactive"), {"ghost"})
        self.assertEqual(self._usernames("blocked"), {"banned"})
        # borrower = not admin, not lender (active state aside).
        self.assertEqual(
            self._usernames("borrower"), {"alice", "ghost", "banned"}
        )


class WhoAmIContentLanguageTests(APITestCase):
    """whoami exposes the deployment's content-translation config (issue #6)."""

    @override_settings(CONTENT_TRANSLATION_PROVIDER="none", LIBRETRANSLATE_URL="")
    def test_authenticated_whoami_includes_content_language_config(self):
        user = get_user_model().objects.create_user(username="someone")
        self.client.force_login(user)
        data = self.client.get("/api/whoami/").json()
        self.assertEqual(data["content_default_language"], "de")
        self.assertEqual(sorted(data["content_languages"]), ["de", "en"])
        self.assertFalse(data["content_translation_enabled"])

    @override_settings(
        AI_PROVIDER="litellm",
        AI_BASE_URL="https://x/v1",
        AI_API_KEY="k",
        AI_MODEL="qwen-3.5",
    )
    def test_whoami_reports_ai_enabled(self):
        user = get_user_model().objects.create_user(username="someone")
        self.client.force_login(user)
        data = self.client.get("/api/whoami/").json()
        self.assertTrue(data["ai_enabled"])


class SilentLoginTests(TestCase):
    """The /oidc/silent/ entry initiates an OIDC login with prompt=none."""

    def test_silent_login_uses_prompt_none(self):
        res = self.client.get("/oidc/silent/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("prompt=none", res["Location"])


class BorrowerProfileApiTests(APITestCase):
    """Lending-desk borrower profile (lenders + admins, read-only identity)."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.testing import make_lender
        from catalog.models import Product, ProductType
        from lending.services import create_reservation

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(
            username="alice", email="alice@uni.test",
            first_name="Alice", last_name="Doe",
        )
        self.pool = ResourcePool.objects.create(name="A", pool_id="A")
        make_lender(self.lender, self.pool)
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Cam")
        resource = Resource.objects.create(
            product=product, resource_pool=self.pool,
            inventory_number="A-1", qr_code_id="QR-A-1",
        )
        now = timezone.now()
        create_reservation(
            self.borrower, [(resource, now, now + timedelta(days=1))],
            status="confirmed",
        )

    def test_profile_visible_to_lender_with_full_name(self):
        self.client.force_login(self.lender)
        res = self.client.get(f"/api/manage/borrower-profiles/{self.borrower.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["full_name"], "Alice Doe")
        self.assertEqual(res.data["email"], "alice@uni.test")
        self.assertIn("strikes", res.data)
        # Read-only profile must not leak admin role/pool controls.
        self.assertNotIn("is_admin", res.data)
        self.assertNotIn("managed_pools", res.data)

    def test_profile_forbidden_to_plain_borrower(self):
        self.client.force_login(self.borrower)
        res = self.client.get(f"/api/manage/borrower-profiles/{self.borrower.id}/")
        self.assertEqual(res.status_code, 403)

    def test_profile_booking_history(self):
        self.client.force_login(self.lender)
        res = self.client.get(
            f"/api/manage/borrower-profiles/{self.borrower.id}/bookings/",
            {"group": "upcoming"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)


class DataRetentionTests(APITestCase):
    """Anonymizing long-inactive accounts (accounts/retention.py)."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone

        self.timedelta = timedelta
        self.now = timezone.now
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )

    def _inactive(self, username, **extra):
        """A user whose last activity is ~5.5 years ago."""
        user = User.objects.create_user(username=username, **extra)
        past = self.now() - self.timedelta(days=2000)
        User.objects.filter(pk=user.pk).update(last_login=past, date_joined=past)
        return User.objects.get(pk=user.pk)

    def _candidate_ids(self, days=1095):
        from accounts import retention

        return set(retention.inactive_candidates(days).values_list("id", flat=True))

    def test_selection_inactive_borrower_only(self):
        old = self._inactive("old")
        recent = User.objects.create_user(username="recent")  # joined just now
        staff = self._inactive("oldadmin", is_staff=True)
        ids = self._candidate_ids()
        self.assertIn(old.id, ids)
        self.assertNotIn(recent.id, ids)
        self.assertNotIn(staff.id, ids)  # admins are never anonymized

    def test_open_booking_excludes_but_finished_does_not(self):
        from lending.models import Booking

        open_user = self._inactive("hasopen")
        Booking.objects.create(borrower=open_user, status="confirmed")
        finished = self._inactive("finished")
        Booking.objects.create(borrower=finished, status="returned")
        ids = self._candidate_ids()
        self.assertNotIn(open_user.id, ids)
        self.assertIn(finished.id, ids)

    def test_inactive_lender_is_included(self):
        from accounts.testing import make_lender

        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        lender = self._inactive("oldlender")
        make_lender(lender, pool)
        self.assertIn(lender.id, self._candidate_ids())

    def test_anonymize_scrubs_pii_and_keeps_history(self):
        from accounts import retention
        from accounts.testing import make_lender
        from lending.models import Booking, BookingReminder

        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        user = self._inactive(
            "alice", email="alice@uni.de", first_name="Alice", last_name="Beispiel"
        )
        user.subject = "sub-1"
        user.claims = {"groups": ["x"]}
        user.save()
        make_lender(user, pool)
        booking = Booking.objects.create(borrower=user, status="returned")
        BookingReminder.objects.create(booking=booking, recipient="alice@uni.de")

        retention.anonymize_user(user)
        user.refresh_from_db()
        self.assertTrue(user.is_anonymized)
        self.assertEqual(user.email, "")
        self.assertIsNone(user.subject)
        self.assertEqual(user.claims, {})
        self.assertEqual(user.username, f"deleted-{user.pk}")
        self.assertEqual(user.get_full_name(), "Gelöschter Nutzer")
        self.assertFalse(user.is_active)
        self.assertFalse(user.access_groups.exists())
        # History survives, now under the placeholder; reminder e-mail scrubbed.
        self.assertEqual(Booking.objects.get(pk=booking.pk).borrower_id, user.pk)
        self.assertEqual(
            BookingReminder.objects.get(booking=booking).recipient, ""
        )

    def test_anonymize_scrubs_free_texts_of_the_person_only(self):
        # Free texts can name people, so they go with the account (#38).
        from accounts import retention
        from accounts.models import Strike
        from django.utils import timezone
        from datetime import timedelta
        from lending.models import Booking

        user = self._inactive("alice")
        other = self._inactive("bob")
        lender = self._inactive("lena")
        soon = timezone.now() + timedelta(days=30)
        mine = Booking.objects.create(
            borrower=user, status="returned",
            note="abgeholt von Carla", confirmation_message="Hallo Alice",
        )
        theirs = Booking.objects.create(
            borrower=other, status="returned",
            note="for Bob's seminar", confirmation_message="Hi Bob",
        )
        against_user = Strike.objects.create(
            user=user, reason="Alice kam zu spät", issued_by=lender, booking=mine,
            expires_at=soon,
        )
        issued_by_user = Strike.objects.create(
            user=other, reason="Bob war unhöflich", issued_by=user, booking=theirs,
            expires_at=soon,
        )

        retention.anonymize_user(user)

        mine.refresh_from_db()
        self.assertEqual(mine.note, "")
        self.assertEqual(mine.confirmation_message, "")
        against_user.refresh_from_db()
        self.assertEqual(against_user.reason, retention.REMOVED_TEXT)
        # Other people's data stays: their booking and a strike the anonymized
        # person issued (it's about someone else).
        theirs.refresh_from_db()
        self.assertEqual(theirs.note, "for Bob's seminar")
        self.assertEqual(theirs.confirmation_message, "Hi Bob")
        issued_by_user.refresh_from_db()
        self.assertEqual(issued_by_user.reason, "Bob war unhöflich")

    def test_run_respects_enabled_flag(self):
        from accounts import retention
        from accounts.models import RetentionSetting

        old = self._inactive("old")
        # Disabled by default -> no-op.
        result = retention.run()
        self.assertFalse(result["enabled"])
        old.refresh_from_db()
        self.assertFalse(old.is_anonymized)
        # --force runs even when disabled.
        retention.run(force=True)
        old.refresh_from_db()
        self.assertTrue(old.is_anonymized)

    def test_run_dry_run_changes_nothing(self):
        from accounts import retention

        old = self._inactive("old")
        result = retention.run(force=True, dry_run=True)
        self.assertEqual(result["candidates"], 1)
        self.assertEqual(result["anonymized"], 0)
        old.refresh_from_db()
        self.assertFalse(old.is_anonymized)

    def test_retention_setting_endpoint(self):
        # Non-admin is denied.
        borrower = User.objects.create_user(username="bob")
        self.client.force_login(borrower)
        self.assertEqual(
            self.client.get("/api/manage/retention-setting/").status_code, 403
        )
        # Admin can read (with the live affected count) and update.
        self.client.force_login(self.admin)
        self._inactive("old")
        res = self.client.get("/api/manage/retention-setting/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["enabled"])
        self.assertEqual(res.data["retention_days"], 1095)
        self.assertEqual(res.data["affected_now"], 1)
        upd = self.client.put(
            "/api/manage/retention-setting/",
            {"enabled": True, "retention_days": 1000},
            format="json",
        )
        self.assertEqual(upd.status_code, 200)
        self.assertTrue(upd.data["enabled"])
        # Below the floor is rejected.
        bad = self.client.put(
            "/api/manage/retention-setting/", {"retention_days": 5}, format="json"
        )
        self.assertEqual(bad.status_code, 400)


class WhoamiLendingScopeTests(APITestCase):
    """whoami.lending_scope_pool_ids drives the "My pools | All pools" switch."""

    def setUp(self):
        from .testing import make_lender

        self.pool_a = ResourcePool.objects.create(name="Scope A", pool_id="SA")
        self.pool_b = ResourcePool.objects.create(
            name="Scope B", pool_id="SB", is_active=False
        )
        self.scoped_admin = User.objects.create_user(
            username="scoped-admin", is_staff=True, is_superuser=True
        )
        self.plain_admin = User.objects.create_user(
            username="plain-admin", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="scope-lender")
        for pool in (self.pool_a, self.pool_b):
            make_lender(self.scoped_admin, pool)
        make_lender(self.lender, self.pool_a)

    def _scope(self, user):
        self.client.force_login(user)
        data = self.client.get("/api/whoami/").json()
        self.assertIn("lending_scope_pool_ids", data)
        return data["lending_scope_pool_ids"]

    def test_scoped_admin_gets_active_membership_pools(self):
        self.assertEqual(self._scope(self.scoped_admin), [self.pool_a.id])

    def test_plain_admin_and_lender_get_null(self):
        self.assertIsNone(self._scope(self.plain_admin))
        self.assertIsNone(self._scope(self.lender))

    def test_admin_with_only_inactive_memberships_gets_null(self):
        self.pool_a.lender_group.members.remove(self.scoped_admin)
        self.assertIsNone(self._scope(self.scoped_admin))

    def test_cors_preflight_allows_pool_scope_header(self):
        response = self.client.options(
            "/api/manage/bookings/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-pool-scope",
        )
        self.assertIn(
            "x-pool-scope", response.get("Access-Control-Allow-Headers", "")
        )


class GroupRightsModelTests(TestCase):
    """AccessGroup rights fields, system groups and the data migration (#80)."""

    def test_admin_group_with_claim_rule_is_invalid(self):
        from django.core.exceptions import ValidationError
        from accounts.models import AccessGroup

        group = AccessGroup(name="Bad", is_admin=True, claim_key="groups",
                            claim_values=["staff"])
        with self.assertRaises(ValidationError):
            group.full_clean()
        AccessGroup(name="Good", is_admin=True).full_clean()

    def test_admin_system_group_exists(self):
        from accounts import roles

        group = roles.admin_group()
        self.assertEqual(group.name, "Administratoren")
        self.assertTrue(group.is_admin)
        self.assertTrue(group.system_admin)
        self.assertEqual(group.claim_key, "")
        # Idempotent: always the same group.
        self.assertEqual(roles.admin_group().pk, group.pk)

    def test_only_one_system_admin_group(self):
        from django.db import IntegrityError, transaction
        from accounts import roles
        from accounts.models import AccessGroup

        roles.admin_group()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessGroup.objects.create(name="Other", is_admin=True, system_admin=True)

    def test_pool_create_creates_system_group(self):
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        group = pool.lender_group
        self.assertEqual(group.name, "Verleiher DigiLab")
        self.assertEqual(set(group.lender_pools.all()), {pool})
        self.assertEqual(group.claim_key, "")
        self.assertFalse(group.is_admin)

    def test_pool_rename_renames_system_group(self):
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        pool.name = "Medienlabor"
        pool.save()
        pool.lender_group.refresh_from_db()
        self.assertEqual(pool.lender_group.name, "Verleiher Medienlabor")

    def test_system_group_survives_trash_and_follows_hard_delete(self):
        from accounts.models import AccessGroup

        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        group_id = pool.lender_group.pk
        pool.soft_delete()
        self.assertTrue(AccessGroup.objects.filter(pk=group_id).exists())
        pool.delete()
        self.assertFalse(AccessGroup.objects.filter(pk=group_id).exists())

    def test_system_group_name_collision_gets_suffix(self):
        from accounts.models import AccessGroup

        AccessGroup.objects.create(name="Verleiher DigiLab")
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        self.assertNotEqual(pool.lender_group.name, "Verleiher DigiLab")
        self.assertTrue(pool.lender_group.name.startswith("Verleiher DigiLab"))

    def test_system_group_uses_default_language_name(self):
        from django.utils import translation

        with translation.override("de"):  # content default language
            pool = ResourcePool.objects.create(name="Medienlabor", pool_id="ML")
        with translation.override("en"):
            pool.name_en = "Media lab"
            pool.save()
        pool.lender_group.refresh_from_db()
        self.assertEqual(pool.lender_group.name, "Verleiher Medienlabor")

    def test_long_pool_name_fits_group_name(self):
        from accounts.models import AccessGroup

        long_name = "X" * 250
        AccessGroup.objects.create(name=("Verleiher " + long_name)[:255])
        pool = ResourcePool.objects.create(name=long_name, pool_id="LONG")
        name = pool.lender_group.name
        self.assertLessEqual(len(name), 255)
        self.assertTrue(name.endswith(" (2)"))

    def test_trashed_and_restored_pool_keeps_group(self):
        from accounts.models import AccessGroup

        apps, PoolMembership = self._pre_removal_state()
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        lender = User.objects.create_user(username="lena")
        PoolMembership.objects.create(user_id=lender.id, resource_pool_id=pool.id)
        pool.soft_delete()
        # The data migration also covers trashed pools.
        AccessGroup.objects.filter(system_pool__isnull=False).delete()
        self._migration().forward(apps, None)
        group = AccessGroup.objects.get(system_pool=pool)
        self.assertEqual(list(group.members.all()), [lender])
        pool.restore()
        self.assertEqual(ResourcePool.objects.get(pk=pool.pk).lender_group.pk, group.pk)
        self.assertEqual(list(group.members.all()), [lender])

    def _pre_removal_state(self):
        """Historical apps as of migration 0008 (before ``PoolMembership`` was
        dropped in 0009) plus its table, created inside the test transaction."""
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(connection)
        nodes = [n for n in loader.graph.leaf_nodes() if n[0] != "accounts"]
        nodes.append(("accounts", "0008_lender_groups_from_memberships"))
        apps = loader.project_state(nodes).apps
        model = apps.get_model("accounts", "PoolMembership")
        with connection.schema_editor() as editor:
            editor.create_model(model)
        return apps, model

    def _migration(self):
        import importlib

        return importlib.import_module(
            "accounts.migrations.0008_lender_groups_from_memberships"
        )

    def test_data_migration_moves_memberships_and_is_reversible(self):
        from accounts.models import AccessGroup

        apps, PoolMembership = self._pre_removal_state()
        mig = self._migration()
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        other = ResourcePool.objects.create(name="Podcast", pool_id="PC")
        lender = User.objects.create_user(username="lena")
        PoolMembership.objects.create(user_id=lender.id, resource_pool_id=pool.id)
        # Simulate the pre-migration state: no system groups yet.
        AccessGroup.objects.filter(system_pool__isnull=False).delete()
        AccessGroup.objects.filter(system_admin=True).delete()

        mig.forward(apps, None)
        group = AccessGroup.objects.get(system_pool=pool)
        self.assertEqual(group.name, "Verleiher DigiLab")
        self.assertEqual(list(group.members.all()), [lender])
        self.assertEqual(set(group.lender_pools.all()), {pool})
        self.assertFalse(AccessGroup.objects.get(system_pool=other).members.exists())
        admin = AccessGroup.objects.get(system_admin=True)
        self.assertEqual(admin.name, "Administratoren")
        self.assertTrue(admin.is_admin)
        # Re-running is harmless.
        mig.forward(apps, None)
        self.assertEqual(AccessGroup.objects.filter(system_pool=pool).count(), 1)

        PoolMembership.objects.all().delete()
        mig.backward(apps, None)
        self.assertFalse(AccessGroup.objects.filter(system_pool__isnull=False).exists())
        self.assertFalse(AccessGroup.objects.filter(system_admin=True).exists())
        self.assertEqual(
            list(PoolMembership.objects.values_list("user_id", "resource_pool_id")),
            [(lender.id, pool.id)],
        )


class RoleFunctionTests(TestCase):
    """accounts.roles: lender and admin rights derived from groups (#80)."""

    def setUp(self):
        from accounts.models import AccessGroup

        self.AccessGroup = AccessGroup
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        self.other_pool = ResourcePool.objects.create(name="Podcast", pool_id="PC")

    def _fresh(self, user):
        return User.objects.get(pk=user.pk)

    def test_lender_via_system_group(self):
        from accounts import roles
        from accounts.testing import make_lender

        user = User.objects.create_user(username="lena")
        make_lender(user, self.pool)
        user = self._fresh(user)
        self.assertEqual(roles.managed_pool_ids(user), {self.pool.id})
        self.assertTrue(roles.is_lender(user))
        self.assertFalse(roles.is_app_admin(user))
        self.assertIn(self.pool.lender_group.id, roles.group_ids(user))
        self.assertEqual(roles.pool_lender_ids(self.pool), {user.id})
        self.assertEqual(roles.pool_lender_ids(self.other_pool), set())

    def test_lender_via_other_group(self):
        from accounts import roles

        user = User.objects.create_user(username="lena")
        group = self.AccessGroup.objects.create(name="Medien-Team")
        group.lender_pools.add(self.pool, self.other_pool)
        group.members.add(user)
        user = self._fresh(user)
        self.assertEqual(roles.managed_pool_ids(user), {self.pool.id, self.other_pool.id})
        self.assertEqual(roles.pool_lender_ids(self.other_pool), {user.id})

    def test_lender_via_claim(self):
        from accounts import roles

        user = User.objects.create_user(
            username="lena", claims={"groups": ["medien", "x"]}
        )
        User.objects.create_user(username="nope", claims={"groups": ["y"]})
        User.objects.create_user(username="other-key", claims={"dept": ["medien"]})
        group = self.AccessGroup.objects.create(
            name="Medien", claim_key="groups", claim_values=["medien"]
        )
        group.lender_pools.add(self.pool)
        user = self._fresh(user)
        self.assertEqual(roles.managed_pool_ids(user), {self.pool.id})
        self.assertTrue(roles.is_lender(user))
        self.assertEqual(roles.pool_lender_ids(self.pool), {user.id})

    def test_borrower_has_no_rights(self):
        from django.contrib.auth.models import AnonymousUser
        from accounts import roles

        user = User.objects.create_user(username="bob")
        self.assertEqual(roles.managed_pool_ids(user), set())
        self.assertFalse(roles.is_lender(user))
        self.assertFalse(roles.is_app_admin(user))
        anon = AnonymousUser()
        self.assertEqual(roles.group_ids(anon), set())
        self.assertEqual(roles.managed_pool_ids(anon), set())
        self.assertFalse(roles.is_app_admin(anon))
        self.assertFalse(roles.is_lender(anon))

    def test_admin_via_manual_membership(self):
        from accounts import roles

        user = User.objects.create_user(username="ada")
        roles.admin_group().members.add(user)
        user = self._fresh(user)
        self.assertTrue(roles.is_app_admin(user))
        self.assertTrue(roles.is_lender(user))
        self.assertIn(user.id, roles.admin_user_ids())

    def test_admin_never_via_claim(self):
        from django.db import IntegrityError, transaction
        from accounts import roles

        user = User.objects.create_user(username="ada", claims={"groups": ["it"]})
        group = self.AccessGroup.objects.create(
            name="IT", claim_key="groups", claim_values=["it"]
        )
        user = self._fresh(user)
        self.assertIn(group.id, roles.group_ids(user))
        self.assertFalse(roles.is_app_admin(user))
        self.assertNotIn(user.id, roles.admin_user_ids())
        # The database refuses an admin group with a claim rule outright.
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.AccessGroup.objects.filter(pk=group.pk).update(is_admin=True)

    def test_staff_and_superuser_are_admins(self):
        from accounts import roles

        staff = User.objects.create_user(username="staff", is_staff=True)
        root = User.objects.create_user(username="root", is_superuser=True)
        self.assertTrue(roles.is_app_admin(staff))
        self.assertTrue(roles.is_app_admin(root))
        self.assertTrue(roles.is_lender(staff))
        self.assertTrue({staff.id, root.id} <= roles.admin_user_ids())

    def test_memoisation_is_per_user(self):
        from accounts import roles
        from accounts.testing import make_lender

        lena = User.objects.create_user(username="lena")
        bob = User.objects.create_user(username="bob")
        make_lender(lena, self.pool)
        lena, bob = self._fresh(lena), self._fresh(bob)
        self.assertEqual(roles.managed_pool_ids(lena), {self.pool.id})
        self.assertEqual(roles.managed_pool_ids(bob), set())
        self.assertFalse(roles.is_lender(bob))
        # Cached results are returned as copies callers can't corrupt.
        roles.managed_pool_ids(lena).add(999)
        self.assertEqual(roles.managed_pool_ids(lena), {self.pool.id})

    def test_cache_follows_membership_changes(self):
        from accounts import roles
        from accounts.testing import make_lender

        user = User.objects.create_user(username="lena")
        self.assertFalse(roles.is_lender(user))
        make_lender(user, self.pool)
        # Same instance (e.g. a test client's force_authenticate user): the
        # change is seen without re-fetching.
        self.assertTrue(roles.is_lender(user))
        self.pool.lender_group.members.remove(user)
        self.assertFalse(roles.is_lender(user))


class RoleCallersViaGroupsTests(APITestCase):
    """Callers use accounts.roles: rights granted by non-system groups (claim or
    manual) and by the "Administratoren" group count everywhere (#80)."""

    def setUp(self):
        from accounts import roles
        from accounts.models import AccessGroup

        self.roles = roles
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        self.other_pool = ResourcePool.objects.create(name="Podcast", pool_id="PC")
        self.root = User.objects.create_user(
            username="root", is_staff=True, is_superuser=True
        )
        self.group_admin = User.objects.create_user(username="ada")
        roles.admin_group().members.add(self.group_admin)
        self.claim_lender = User.objects.create_user(
            username="cleo", claims={"groups": ["medien"]}
        )
        group = AccessGroup.objects.create(
            name="Medien", claim_key="groups", claim_values=["medien"]
        )
        group.lender_pools.add(self.other_pool)
        self.borrower = User.objects.create_user(username="bob")

    def _usernames(self, role):
        self.client.force_login(self.root)
        res = self.client.get("/api/manage/users/", {"role": role})
        return {u["username"] for u in res.json()["results"]}

    def test_role_filters_and_list_fields(self):
        self.assertEqual(self._usernames("admin"), {"root", "ada"})
        self.assertEqual(self._usernames("lender"), {"cleo"})
        self.assertEqual(self._usernames("borrower"), {"bob"})
        res = self.client.get("/api/manage/users/")
        by_name = {u["username"]: u for u in res.json()["results"]}
        self.assertTrue(by_name["ada"]["is_admin"])
        self.assertFalse(by_name["ada"]["is_lender"])
        self.assertTrue(by_name["cleo"]["is_lender"])
        self.assertEqual(
            [p["pool"] for p in by_name["cleo"]["managed_pools"]],
            [self.other_pool.id],
        )
        self.assertEqual(by_name["cleo"]["managed_pools"][0]["pool_name"], "Podcast")
        # The detail view agrees with the batched list.
        detail = self.client.get(f"/api/manage/users/{self.claim_lender.id}/").json()
        self.assertEqual(detail["managed_pools"], by_name["cleo"]["managed_pools"])

    def test_group_admin_passes_admin_endpoints_and_whoami(self):
        self.client.force_login(self.group_admin)
        self.assertEqual(self.client.get("/api/manage/users/").status_code, 200)
        me = self.client.get("/api/whoami/").json()
        self.assertTrue(me["is_staff"])
        self.assertTrue(me["is_lender"])

    def test_claim_lender_is_lender_of_its_pool_only(self):
        self.client.force_login(self.claim_lender)
        me = self.client.get("/api/whoami/").json()
        self.assertFalse(me["is_staff"])
        self.assertTrue(me["is_lender"])
        self.assertEqual(self.client.get("/api/manage/users/").status_code, 403)
        res = self.client.get("/api/manage/pools/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        rows = body["results"] if isinstance(body, dict) else body
        self.assertEqual([p["id"] for p in rows], [self.other_pool.id])

    def test_set_pools_toggles_only_system_groups(self):
        self.client.force_login(self.root)
        res = self.client.put(
            f"/api/manage/users/{self.claim_lender.id}/pools/",
            {"pool_ids": [self.pool.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            {p["pool"] for p in res.json()["managed_pools"]},
            {self.pool.id, self.other_pool.id},
        )
        res = self.client.put(
            f"/api/manage/users/{self.claim_lender.id}/pools/",
            {"pool_ids": []},
            format="json",
        )
        # The claim group's pool stays; only the system group was left.
        self.assertEqual(
            [p["pool"] for p in res.json()["managed_pools"]],
            [self.other_pool.id],
        )
        self.assertFalse(self.pool.lender_group.members.exists())

    def test_retention_never_selects_group_admins(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts import retention

        past = timezone.now() - timedelta(days=2000)
        User.objects.update(last_login=past, date_joined=past)
        ids = set(retention.inactive_candidates(1095).values_list("id", flat=True))
        self.assertNotIn(self.group_admin.id, ids)
        self.assertNotIn(self.root.id, ids)
        self.assertIn(self.claim_lender.id, ids)
        self.assertIn(self.borrower.id, ids)

    def test_bulk_managed_pools_match_single(self):
        users = list(User.objects.all())
        bulk = self.roles.managed_pool_ids_by_user(users)
        for user in users:
            fresh = User.objects.get(pk=user.pk)
            self.assertEqual(bulk[user.pk], self.roles.managed_pool_ids(fresh))
        self.assertEqual(self.roles.lender_user_ids(), {self.claim_lender.id})

    def test_review_defects_mails_claim_lenders_and_group_admin_fallback(self):
        from datetime import timedelta
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        from catalog.models import Product, ProductType, ResourceDefect

        self.claim_lender.email = "cleo@uni.de"
        self.claim_lender.save()
        self.group_admin.email = "ada@uni.de"
        self.group_admin.save()
        ptype = ProductType.objects.create(name="Cam")
        product = Product.objects.create(title="Cam", product_type=ptype)
        rows = []
        for i, pool in enumerate((self.pool, self.other_pool)):
            res = Resource.objects.create(
                product=product, resource_pool=pool, inventory_number=f"R{i}",
                qr_code_id=f"QR{i}", status=Resource.Status.DEFECTIVE,
            )
            defect = ResourceDefect.objects.create(resource=res, note="x")
            rows.append(defect)
        ResourceDefect.objects.update(
            created_at=rows[0].created_at - timedelta(days=30)
        )
        with patch(
            "lending.management.commands.review_defects.send_defect_review",
            return_value=True,
        ) as send:
            call_command("review_defects", stdout=StringIO())
        sent = {(call.args[0], call.args[1].pk) for call in send.call_args_list}
        self.assertEqual(
            sent,
            {("ada@uni.de", self.pool.pk), ("cleo@uni.de", self.other_pool.pk)},
        )

    def test_groups_put_leaves_pool_lender_groups_alone(self):
        from accounts.models import AccessGroup

        regular = AccessGroup.objects.create(name="Musik")
        self.client.force_login(self.root)
        url = f"/api/manage/users/{self.borrower.id}/"
        # The user page saves pools, then groups with the ids it loaded before.
        self.client.put(url + "pools/", {"pool_ids": [self.pool.id]}, format="json")
        res = self.client.put(
            url + "groups/", {"group_ids": [regular.id]}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([g["id"] for g in body["groups"]], [regular.id])
        self.assertEqual(
            [p["pool"] for p in body["managed_pools"]], [self.pool.id]
        )
        # Sending a system lender group's id doesn't add it either.
        self.client.put(url + "pools/", {"pool_ids": []}, format="json")
        res = self.client.put(
            url + "groups/",
            {"group_ids": [regular.id, self.pool.lender_group.id]},
            format="json",
        )
        self.assertEqual(res.json()["managed_pools"], [])

    def test_group_admin_cannot_drop_own_admin_group(self):
        from accounts.models import AccessGroup

        regular = AccessGroup.objects.create(name="Musik")
        self.client.force_login(self.group_admin)
        url = f"/api/manage/users/{self.group_admin.id}/groups/"
        res = self.client.put(url, {"group_ids": [regular.id]}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("own admin rights", res.json()["detail"])
        self.assertTrue(self.roles.admin_group().members.filter(pk=self.group_admin.pk).exists())
        # Keeping the admin group while changing others is fine.
        res = self.client.put(
            url, {"group_ids": [regular.id, self.roles.admin_group().id]}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        # Another admin may remove them.
        self.client.force_login(self.root)
        res = self.client.put(url, {"group_ids": []}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(self.roles.is_app_admin(User.objects.get(pk=self.group_admin.pk)))

    def test_would_be_admin(self):
        admin_group = self.roles.admin_group()
        self.assertTrue(self.roles.would_be_admin(self.root, []))
        self.assertTrue(self.roles.would_be_admin(self.group_admin, [admin_group.id]))
        self.assertFalse(self.roles.would_be_admin(self.group_admin, []))

    def test_whoami_is_admin(self):
        self.client.force_login(self.group_admin)
        me = self.client.get("/api/whoami/").json()
        self.assertTrue(me["is_admin"])
        self.client.force_login(self.claim_lender)
        self.assertFalse(self.client.get("/api/whoami/").json()["is_admin"])

    def test_pool_lenders_get_does_not_write(self):
        from accounts.models import AccessGroup

        AccessGroup.objects.filter(system_pool=self.pool).delete()
        self.client.force_login(self.root)
        res = self.client.get(f"/api/manage/pools/{self.pool.id}/lenders/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])
        self.assertFalse(AccessGroup.objects.filter(system_pool=self.pool).exists())
        # PUT still (re)creates the system group.
        res = self.client.put(
            f"/api/manage/pools/{self.pool.id}/lenders/",
            {"user_ids": [self.borrower.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            list(AccessGroup.objects.get(system_pool=self.pool).members.all()),
            [self.borrower],
        )


class AccessGroupRightsApiTests(APITestCase):
    """Groups API: rights fields, system-group locks, self-lockout guard and
    the members endpoint (#80)."""

    URL = "/api/manage/access-groups/"

    def setUp(self):
        from accounts import roles
        from accounts.models import AccessGroup

        self.roles = roles
        self.AccessGroup = AccessGroup
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        self.other_pool = ResourcePool.objects.create(name="Podcast", pool_id="PC")
        self.root = User.objects.create_user(
            username="root", first_name="Rita", last_name="Root",
            is_staff=True, is_superuser=True,
        )
        self.group_admin = User.objects.create_user(username="ada", first_name="Ada")
        roles.admin_group().members.add(self.group_admin)
        self.client.force_login(self.root)

    def _detail(self, group):
        return f"{self.URL}{group.id}/"

    # --- fields -----------------------------------------------------------
    def test_create_with_rights_and_read_only_system_fields(self):
        res = self.client.post(
            self.URL,
            {
                "name": "Medien", "lender_pools": [self.pool.id], "is_admin": False,
                "system_pool": self.other_pool.id, "system_admin": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["lender_pools"], [self.pool.id])
        self.assertEqual(body["lender_pool_names"], ["DigiLab"])
        self.assertFalse(body["is_admin"])
        self.assertIsNone(body["system_pool"])
        self.assertFalse(body["system_admin"])
        self.assertEqual(body["member_count"], 0)
        group = self.AccessGroup.objects.get(pk=body["id"])
        self.assertIsNone(group.system_pool_id)
        self.assertFalse(group.system_admin)

    def test_list_exposes_system_flags(self):
        res = self.client.get(self.URL, {"page_size": 100})
        body = res.json()
        rows = body["results"] if isinstance(body, dict) else body
        by_name = {g["name"]: g for g in rows}
        self.assertEqual(by_name["Verleiher DigiLab"]["system_pool"], self.pool.id)
        self.assertEqual(by_name["Verleiher DigiLab"]["lender_pools"], [self.pool.id])
        self.assertTrue(by_name["Administratoren"]["system_admin"])
        self.assertTrue(by_name["Administratoren"]["is_admin"])
        self.assertEqual(by_name["Administratoren"]["member_count"], 1)

    def test_admin_with_claim_rule_rejected(self):
        res = self.client.post(
            self.URL,
            {"name": "X", "is_admin": True, "claim_key": "groups", "claim_values": ["a"]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("is_admin", res.json())
        # Also when only one of the two is sent on update.
        group = self.AccessGroup.objects.create(
            name="Y", claim_key="groups", claim_values=["a"]
        )
        res = self.client.patch(self._detail(group), {"is_admin": True}, format="json")
        self.assertEqual(res.status_code, 400)
        admin = self.AccessGroup.objects.create(name="Z", is_admin=True)
        res = self.client.patch(
            self._detail(admin), {"claim_key": "groups", "claim_values": ["a"]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    # --- system-group locks ----------------------------------------------
    def test_system_groups_not_deletable(self):
        for group in (self.pool.lender_group, self.roles.admin_group()):
            res = self.client.delete(self._detail(group))
            self.assertEqual(res.status_code, 400)
            self.assertTrue(self.AccessGroup.objects.filter(pk=group.pk).exists())

    def test_system_lender_group_locked_fields(self):
        group = self.pool.lender_group
        for payload in (
            {"name": "Other"},
            {"claim_key": "groups", "claim_values": ["x"]},
            {"lender_pools": [self.pool.id, self.other_pool.id]},
            {"is_admin": True},
        ):
            res = self.client.patch(self._detail(group), payload, format="json")
            self.assertEqual(res.status_code, 400, payload)
        group.refresh_from_db()
        self.assertEqual(group.name, "Verleiher DigiLab")
        self.assertEqual(list(group.lender_pools.all()), [self.pool])
        # Unchanged values of locked fields (a full form save) are fine, and
        # members / description / access pools are editable.
        borrower = User.objects.create_user(username="bob")
        res = self.client.put(
            self._detail(group),
            {
                "name": "Verleiher DigiLab", "description": "Desk team",
                "claim_key": "", "claim_values": [], "pools": [self.other_pool.id],
                "lender_pools": [self.pool.id], "is_admin": False,
                "members": [borrower.id],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        group.refresh_from_db()
        self.assertEqual(group.description, "Desk team")
        self.assertEqual(list(group.pools.all()), [self.other_pool])
        self.assertEqual(list(group.members.all()), [borrower])

    def test_system_admin_group_locked_fields(self):
        group = self.roles.admin_group()
        for payload in (
            {"name": "Admins"},
            {"is_admin": False},
            {"claim_key": "groups", "claim_values": ["x"]},
            {"lender_pools": [self.pool.id]},
        ):
            res = self.client.patch(self._detail(group), payload, format="json")
            self.assertEqual(res.status_code, 400, payload)
        res = self.client.patch(self._detail(group), {"description": "All admins"}, format="json")
        self.assertEqual(res.status_code, 200)

    # --- self-lockout -----------------------------------------------------
    def test_group_admin_cannot_remove_self_from_admin_group(self):
        group = self.roles.admin_group()
        self.client.force_login(self.group_admin)
        res = self.client.patch(self._detail(group), {"members": []}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("own admin rights", res.json()["detail"])
        self.assertTrue(group.members.filter(pk=self.group_admin.pk).exists())
        # Another admin may.
        self.client.force_login(self.root)
        res = self.client.patch(self._detail(group), {"members": []}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_group_admin_cannot_clear_is_admin_or_delete_own_group(self):
        group = self.AccessGroup.objects.create(name="Leitung", is_admin=True)
        solo = User.objects.create_user(username="solo")
        group.members.add(solo)
        self.client.force_login(solo)
        res = self.client.patch(self._detail(group), {"is_admin": False}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.delete(self._detail(group))
        self.assertEqual(res.status_code, 400)
        self.assertTrue(self.AccessGroup.objects.filter(pk=group.pk).exists())
        # With admin rights from another group, both are fine.
        self.roles.admin_group().members.add(solo)
        res = self.client.patch(self._detail(group), {"is_admin": False}, format="json")
        self.assertEqual(res.status_code, 200)
        group.is_admin = True
        group.save()
        res = self.client.delete(self._detail(group))
        self.assertEqual(res.status_code, 204)

    def test_staff_admin_may_edit_admin_groups_freely(self):
        group = self.roles.admin_group()
        group.members.add(self.root)
        res = self.client.patch(self._detail(group), {"members": []}, format="json")
        self.assertEqual(res.status_code, 200)

    # --- members endpoint -------------------------------------------------
    def test_members_sources(self):
        group = self.AccessGroup.objects.create(
            name="Medien", claim_key="groups", claim_values=["medien"]
        )
        manual = User.objects.create_user(username="zoe", first_name="Zoe")
        both = User.objects.create_user(
            username="ben", first_name="Ben", claims={"groups": ["medien"]}
        )
        claimed = User.objects.create_user(
            username="carl", first_name="Carl", email="carl@x.de",
            claims={"groups": "medien"},
        )
        User.objects.create_user(username="other", claims={"groups": ["musik"]})
        group.members.add(manual, both)
        res = self.client.get(f"{self._detail(group)}members/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            [(m["username"], m["source"]) for m in res.json()],
            [("ben", "manual"), ("carl", "claim"), ("zoe", "manual")],
        )
        row = res.json()[1]
        self.assertEqual(row["id"], claimed.id)
        self.assertEqual(row["name"], "Carl")
        self.assertEqual(row["email"], "carl@x.de")

    def test_members_of_admin_group_include_system_admins(self):
        res = self.client.get(f"{self._detail(self.roles.admin_group())}members/")
        self.assertEqual(
            [(m["username"], m["source"]) for m in res.json()],
            [("ada", "manual"), ("root", "system_admin")],
        )
        # A staff user who is also a manual member counts as manual.
        self.roles.admin_group().members.add(self.root)
        res = self.client.get(f"{self._detail(self.roles.admin_group())}members/")
        self.assertEqual(
            [(m["username"], m["source"]) for m in res.json()],
            [("ada", "manual"), ("root", "manual")],
        )
        # Other groups never list system admins.
        res = self.client.get(f"{self._detail(self.pool.lender_group)}members/")
        self.assertEqual(res.json(), [])

    def test_member_count_is_manual_and_current_after_update(self):
        group = self.AccessGroup.objects.create(
            name="Medien", claim_key="groups", claim_values=["medien"]
        )
        User.objects.create_user(username="carl", claims={"groups": ["medien"]})
        a = User.objects.create_user(username="a1")
        b = User.objects.create_user(username="b1")
        res = self.client.patch(self._detail(group), {"members": [a.id, b.id]}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["member_count"], 2)
        res = self.client.post(self.URL, {"name": "Neu", "members": [a.id]}, format="json")
        self.assertEqual(res.json()["member_count"], 1)
        rows = self.client.get(self.URL, {"page_size": 100}).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual({g["name"]: g["member_count"] for g in rows}["Medien"], 2)

    def test_member_preview_lists_first_three_manual_members(self):
        group = self.AccessGroup.objects.create(
            name="Vorschau", claim_key="groups", claim_values=["medien"]
        )
        User.objects.create_user(username="claimed", claims={"groups": ["medien"]})
        people = [
            User.objects.create_user(username="zed", first_name="Zoe", last_name="Zett"),
            User.objects.create_user(username="bea"),
            User.objects.create_user(username="ann", first_name="Anna", last_name="Alt"),
            User.objects.create_user(username="carl"),
        ]
        group.members.add(*people)
        rows = self.client.get(self.URL, {"page_size": 100}).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        row = {g["name"]: g for g in rows}["Vorschau"]
        self.assertEqual(row["member_count"], 4)
        self.assertEqual(
            row["member_preview"],
            [
                {"id": people[2].id, "name": "Anna Alt"},
                {"id": people[1].id, "name": "bea"},
                {"id": people[3].id, "name": "carl"},
            ],
        )
        # The detail/update response carries it too.
        res = self.client.patch(
            self._detail(group), {"members": [people[0].id]}, format="json"
        )
        self.assertEqual(res.json()["member_preview"], [{"id": people[0].id, "name": "Zoe Zett"}])

    def test_members_flag_inactive_and_odd_claim_keys(self):
        group = self.AccessGroup.objects.create(
            name="Odd", claim_key="x__y", claim_values=["1", "v"]
        )
        gone = User.objects.create_user(username="gone", is_active=False)
        group.members.add(gone)
        User.objects.create_user(username="lst", claims={"x__y": ["v", "w"]})
        User.objects.create_user(username="num", claims={"x__y": 1})
        User.objects.create_user(username="no", claims={"x__y": ["w"]})
        rows = self.client.get(f"{self._detail(group)}members/").json()
        self.assertEqual(
            [(m["username"], m["source"], m["is_active"]) for m in rows],
            [("gone", "manual", False), ("lst", "claim", True), ("num", "claim", True)],
        )

    def test_members_requires_admin(self):
        lender = User.objects.create_user(username="lena")
        self.pool.lender_group.members.add(lender)
        self.client.force_login(lender)
        res = self.client.get(f"{self._detail(self.pool.lender_group)}members/")
        self.assertEqual(res.status_code, 403)


class UserManagedPoolsShapeTests(APITestCase):
    """Users API: ``managed_pools`` lists each pool once with every group that
    grants it (#80)."""

    def setUp(self):
        from accounts.models import AccessGroup

        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        self.other_pool = ResourcePool.objects.create(name="Podcast", pool_id="PC")
        self.root = User.objects.create_user(
            username="root", is_staff=True, is_superuser=True
        )
        self.user = User.objects.create_user(
            username="lena", claims={"groups": ["medien"]}
        )
        self.pool.lender_group.members.add(self.user)
        self.manual_group = AccessGroup.objects.create(name="Technik")
        self.manual_group.lender_pools.add(self.pool, self.other_pool)
        self.manual_group.members.add(self.user)
        self.claim_group = AccessGroup.objects.create(
            name="Medien", claim_key="groups", claim_values=["medien"]
        )
        self.claim_group.lender_pools.add(self.other_pool)
        self.client.force_login(self.root)

    def _expected(self):
        return [
            {
                "pool": self.pool.id, "pool_name": "DigiLab",
                "via": [
                    {"group_id": self.pool.lender_group.id,
                     "group_name": "Verleiher DigiLab", "system": True},
                    {"group_id": self.manual_group.id,
                     "group_name": "Technik", "system": False},
                ],
            },
            {
                "pool": self.other_pool.id, "pool_name": "Podcast",
                "via": [
                    {"group_id": self.claim_group.id,
                     "group_name": "Medien", "system": False},
                    {"group_id": self.manual_group.id,
                     "group_name": "Technik", "system": False},
                ],
            },
        ]

    def test_list_and_detail_shape(self):
        res = self.client.get("/api/manage/users/", {"search": "lena"})
        row = res.json()["results"][0]
        self.assertEqual(row["managed_pools"], self._expected())
        detail = self.client.get(f"/api/manage/users/{self.user.id}/").json()
        self.assertEqual(detail["managed_pools"], self._expected())

    def test_put_pools_only_touches_system_groups(self):
        res = self.client.put(
            f"/api/manage/users/{self.user.id}/pools/",
            {"pool_ids": [self.other_pool.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(self.pool.lender_group.members.filter(pk=self.user.pk).exists())
        self.assertTrue(
            self.other_pool.lender_group.members.filter(pk=self.user.pk).exists()
        )
        self.assertTrue(self.manual_group.members.filter(pk=self.user.pk).exists())
        by_pool = {m["pool"]: m for m in res.json()["managed_pools"]}
        self.assertEqual(
            [v["group_name"] for v in by_pool[self.pool.id]["via"]], ["Technik"]
        )
        self.assertEqual(
            [v["system"] for v in by_pool[self.other_pool.id]["via"]],
            [True, False, False],
        )


class AdminFlagEditingTests(APITestCase):
    """The user form's admin toggle edits only the Django flags, and only
    staff/superusers may change it (#80 final review: C1, I1)."""

    def setUp(self):
        from accounts import roles
        from accounts.models import AccessGroup

        self.root = User.objects.create_user(
            username="root", is_staff=True, is_superuser=True
        )
        self.group_admin = User.objects.create_user(username="ada")
        roles.admin_group().members.add(self.group_admin)
        extra = AccessGroup.objects.create(name="Leitung", is_admin=True)
        extra.members.add(self.group_admin)
        AccessGroup.objects.create(name="Medien").members.add(self.group_admin)
        self.bob = User.objects.create_user(username="bob")

    def _url(self, user):
        return f"/api/manage/users/{user.id}/"

    def test_serializer_reports_flag_and_admin_groups(self):
        self.client.force_login(self.root)
        rows = {
            u["username"]: u
            for u in self.client.get("/api/manage/users/").json()["results"]
        }
        self.assertTrue(rows["ada"]["is_admin"])
        self.assertFalse(rows["ada"]["admin_via_flag"])
        self.assertEqual(rows["ada"]["admin_groups"], ["Administratoren", "Leitung"])
        self.assertTrue(rows["root"]["admin_via_flag"])
        self.assertEqual(rows["root"]["admin_groups"], [])
        detail = self.client.get(self._url(self.group_admin)).json()
        self.assertFalse(detail["admin_via_flag"])
        self.assertEqual(detail["admin_groups"], ["Administratoren", "Leitung"])

    def test_deactivating_group_admin_keeps_django_flags(self):
        self.client.force_login(self.root)
        res = self.client.patch(
            self._url(self.group_admin), {"is_active": False}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.group_admin.refresh_from_db()
        self.assertFalse(self.group_admin.is_active)
        self.assertFalse(self.group_admin.is_staff)
        self.assertFalse(self.group_admin.is_superuser)

    def test_group_admin_cannot_promote_self(self):
        self.client.force_login(self.group_admin)
        res = self.client.patch(
            self._url(self.group_admin), {"is_admin": True}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.group_admin.refresh_from_db()
        self.assertFalse(self.group_admin.is_superuser)

    def test_group_admin_cannot_promote_others(self):
        self.client.force_login(self.group_admin)
        res = self.client.patch(self._url(self.bob), {"is_admin": True}, format="json")
        self.assertEqual(res.status_code, 403)
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_staff)

    def test_group_admin_may_still_change_is_active(self):
        self.client.force_login(self.group_admin)
        res = self.client.patch(self._url(self.bob), {"is_active": False}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_staff_admin_may_promote(self):
        self.client.force_login(self.root)
        res = self.client.patch(self._url(self.bob), {"is_admin": True}, format="json")
        self.assertEqual(res.status_code, 200)
        self.bob.refresh_from_db()
        self.assertTrue(self.bob.is_staff and self.bob.is_superuser)
        self.assertTrue(res.json()["admin_via_flag"])

    def test_whoami_reports_admin_via_flag(self):
        self.client.force_login(self.group_admin)
        me = self.client.get("/api/whoami/").json()
        self.assertTrue(me["is_admin"])
        self.assertFalse(me["admin_via_flag"])
        self.client.force_login(self.root)
        self.assertTrue(self.client.get("/api/whoami/").json()["admin_via_flag"])


class TrashedPoolRightsTests(APITestCase):
    """Saving with a trashed pool id in the state must not 400 (#80)."""

    def setUp(self):
        from accounts.models import AccessGroup

        self.root = User.objects.create_user(
            username="root", is_staff=True, is_superuser=True
        )
        self.user = User.objects.create_user(username="lena")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        self.trashed = ResourcePool.objects.create(name="Alt", pool_id="ALT")
        self.trashed.lender_group.members.add(self.user)
        self.group = AccessGroup.objects.create(name="Technik")
        self.group.lender_pools.add(self.pool, self.trashed)
        self.trashed.soft_delete()
        self.client.force_login(self.root)

    def test_put_pools_accepts_trashed_pool(self):
        res = self.client.put(
            f"/api/manage/users/{self.user.id}/pools/",
            {"pool_ids": [self.pool.id, self.trashed.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(
            self.trashed.lender_group.members.filter(pk=self.user.pk).exists()
        )

    def test_group_lender_pools_accepts_trashed_pool(self):
        res = self.client.patch(
            f"/api/manage/access-groups/{self.group.id}/",
            {"lender_pools": [self.pool.id, self.trashed.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
