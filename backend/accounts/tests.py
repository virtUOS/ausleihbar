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
        pools = [m["resource_pool"] for m in res.json()["managed_pools"]]
        self.assertEqual(pools, [self.pool_a.id])

        # Empty list removes all memberships -> no longer a lender.
        res = self.client.put(
            f"/api/manage/users/{self.borrower.id}/pools/",
            {"pool_ids": []},
            format="json",
        )
        self.assertFalse(res.json()["is_lender"])
        self.assertEqual(self.borrower.pool_memberships.count(), 0)

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
        from accounts.models import PoolMembership

        lender = User.objects.create_user(username="lender")
        PoolMembership.objects.create(user=lender, resource_pool=self.restricted_pool)
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


class StrikeTests(APITestCase):
    """Issuing strikes, escalation to a block, enforcement and admin controls."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import PoolMembership, StrikeSetting
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
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
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


class UserRoleFilterTests(APITestCase):
    """The ?role= filter on the user list (for the clickable role badges)."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import PoolMembership

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.lender = User.objects.create_user(username="len")
        pool = ResourcePool.objects.create(name="A", pool_id="A")
        PoolMembership.objects.create(user=self.lender, resource_pool=pool)
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

        from accounts.models import PoolMembership
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
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
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
        from accounts.models import PoolMembership

        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        lender = self._inactive("oldlender")
        PoolMembership.objects.create(user=lender, resource_pool=pool)
        self.assertIn(lender.id, self._candidate_ids())

    def test_anonymize_scrubs_pii_and_keeps_history(self):
        from accounts import retention
        from accounts.models import PoolMembership
        from lending.models import Booking, BookingReminder

        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        user = self._inactive(
            "alice", email="alice@uni.de", first_name="Alice", last_name="Beispiel"
        )
        user.subject = "sub-1"
        user.claims = {"groups": ["x"]}
        user.save()
        PoolMembership.objects.create(user=user, resource_pool=pool)
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
        self.assertFalse(PoolMembership.objects.filter(user=user).exists())
        # History survives, now under the placeholder; reminder e-mail scrubbed.
        self.assertEqual(Booking.objects.get(pk=booking.pk).borrower_id, user.pk)
        self.assertEqual(
            BookingReminder.objects.get(booking=booking).recipient, ""
        )

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
