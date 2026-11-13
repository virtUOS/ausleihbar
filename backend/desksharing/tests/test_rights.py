# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import AccessGroup
from catalog.models import ResourcePool
from desksharing import rights
from desksharing.models import DeskSettings

User = get_user_model()


def new_pool(name):
    return ResourcePool.objects.create(name=name, pool_id=name.lower())


def make_pool(name, *groups, enabled=True, assistant=None):
    pool = new_pool(name)
    for g in groups:
        g.pools.add(pool)
    settings_ = DeskSettings.for_pool(pool)
    settings_.enabled = enabled
    settings_.assistant_group = assistant
    settings_.save()
    return pool


class RightsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="x")
        self.group = AccessGroup.objects.create(name="Dept A")

    def test_enable_requires_access_group(self):
        pool = new_pool("P")
        s = DeskSettings.for_pool(pool)
        s.enabled = True
        with self.assertRaises(ValidationError) as cm:
            s.full_clean()
        self.assertIn("enabled", cm.exception.message_dict)
        self.group.pools.add(pool)
        s.full_clean()

    def test_for_pool_is_get_or_create(self):
        pool = new_pool("P")
        self.assertEqual(DeskSettings.for_pool(pool).pk, DeskSettings.for_pool(pool).pk)

    def test_member_pool_ids_open_pool_excluded(self):
        pool = make_pool("Open", enabled=False)
        DeskSettings.objects.filter(pool=pool).update(enabled=True)
        self.assertNotIn(pool.id, rights.member_pool_ids(self.user))

    def test_member_pool_ids_via_group(self):
        pool = make_pool("A", self.group)
        other = make_pool("B", AccessGroup.objects.create(name="Dept B"))
        self.user.access_groups.add(self.group)
        ids = rights.member_pool_ids(self.user)
        self.assertIn(pool.id, ids)
        self.assertNotIn(other.id, ids)

    def test_member_pool_ids_disabled_excluded(self):
        pool = new_pool("A")
        self.group.pools.add(pool)
        DeskSettings.for_pool(pool)
        self.user.access_groups.add(self.group)
        self.assertNotIn(pool.id, rights.member_pool_ids(self.user))

    def test_assistant_via_group(self):
        helpers = AccessGroup.objects.create(name="Helpers")
        pool = make_pool("A", self.group, assistant=helpers)
        helpers.members.add(self.user)
        self.assertIn(pool.id, rights.assistant_pool_ids(self.user))
        self.assertNotIn(pool.id, rights.admin_pool_ids(self.user))

    def test_lender_is_admin_pool(self):
        pool = make_pool("A", self.group)
        lenders = AccessGroup.objects.create(name="L")
        lenders.lender_pools.add(pool)
        lenders.members.add(self.user)
        self.assertIn(pool.id, rights.admin_pool_ids(self.user))
        self.assertIn(pool.id, rights.assistant_pool_ids(self.user))
        self.assertIn(pool.id, rights.member_pool_ids(self.user))

    def test_app_admin_gets_all_enabled_pools(self):
        pool = make_pool("A", self.group)
        off = new_pool("Off")
        self.user.is_staff = True
        self.user.save()
        ids = rights.admin_pool_ids(self.user)
        self.assertIn(pool.id, ids)
        self.assertNotIn(off.id, ids)

    def test_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        anon = AnonymousUser()
        self.assertEqual(rights.admin_pool_ids(anon), set())
        self.assertEqual(rights.assistant_pool_ids(anon), set())
        self.assertEqual(rights.member_pool_ids(anon), set())


class WhoamiDeskFieldsTests(TestCase):
    def test_whoami_desk_fields(self):
        from rest_framework.test import APIClient

        group = AccessGroup.objects.create(name="Dept W")
        member_pool = make_pool("WA", group)
        admin_pool = make_pool("WB", AccessGroup.objects.create(name="Dept W2"))
        off_pool = make_pool("WC", group, enabled=False)
        user = User.objects.create_user("whoami_desk", password="x")
        group.members.add(user)
        lenders = AccessGroup.objects.create(name="WL")
        lenders.lender_pools.add(admin_pool)
        lenders.members.add(user)
        client = APIClient()
        client.force_login(user)
        data = client.get("/api/whoami/").json()
        self.assertEqual(data["desk_pool_ids"], sorted([member_pool.id, admin_pool.id]))
        self.assertEqual(data["desk_admin_pool_ids"], [admin_pool.id])
        self.assertEqual(data["desk_assistant_pool_ids"], [admin_pool.id])
        self.assertNotIn(off_pool.id, data["desk_pool_ids"])
        self.assertEqual(
            sorted(p["id"] for p in data["desk_pools"]), sorted([member_pool.id, admin_pool.id])
        )
        self.assertEqual(
            {p["id"]: p["name"] for p in data["desk_pools"]}[member_pool.id], "WA"
        )
        plain = User.objects.create_user("whoami_plain", password="x")
        client.force_login(plain)
        data = client.get("/api/whoami/").json()
        self.assertEqual(data["desk_pool_ids"], [])
        self.assertEqual(data["desk_admin_pool_ids"], [])
        self.assertEqual(data["desk_assistant_pool_ids"], [])
        self.assertEqual(data["desk_pools"], [])
