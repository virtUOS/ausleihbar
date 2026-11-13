# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing.models import DeskSettings
from desksharing.tests.test_places import BASE, PlaceTestBase

User = get_user_model()


class PeopleSearchTests(PlaceTestBase):
    def setUp(self):
        super().setUp()
        self.max = User.objects.create_user("mm", password="x", first_name="Max", last_name="Muster")
        self.group.members.add(self.max)
        self.outsider = User.objects.create_user("oo", password="x", first_name="Maxine", last_name="Fremd")
        self.assistant = User.objects.create_user("asst", password="x", first_name="Ann", last_name="Assist")
        agroup = AccessGroup.objects.create(name="Assistants")
        agroup.members.add(self.assistant)
        self.group.members.add(self.assistant)
        s = DeskSettings.for_pool(self.pool)
        s.assistant_group = agroup
        s.save()

    def search(self, q, pool=None):
        return self.client.get(f"{BASE}/people/", {"pool": pool or self.pool.pk, "q": q})

    def test_finds_department_members_by_name_only(self):
        r = self.search("max")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["name"] for p in r.json()], ["Max Muster"])
        self.assertEqual(set(r.json()[0]), {"id", "name"})
        # Not found by username or by e-mail.
        self.assertEqual(self.search("asst").json(), [])

    def test_min_length(self):
        self.assertEqual(self.search("ma").status_code, 400)

    def test_assistant_allowed_member_and_other_pool_not(self):
        self.client.force_authenticate(self.assistant)
        self.assertEqual(self.search("max").status_code, 200)
        self.client.force_authenticate(self.max)
        self.assertEqual(self.search("max").status_code, 403)
        self.client.force_authenticate(self.lender)
        self.assertEqual(self.search("max", pool=self.other_pool.pk).status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.search("max").status_code, (401, 403))

    def test_whoami_assistant_pools(self):
        self.client.force_login(self.assistant)
        data = self.client.get("/api/whoami/").json()
        self.assertEqual(data["desk_assistant_pool_ids"], [self.pool.pk])
        self.assertEqual(data["desk_admin_pool_ids"], [])


class AccessGroupListTests(PlaceTestBase):
    def test_lists_pool_and_ordinary_groups_not_system(self):
        AccessGroup.objects.create(name="Ordinary")
        AccessGroup.objects.create(name="Admins2", is_admin=True)
        r = self.client.get(f"{BASE}/access-groups/", {"pool": self.pool.pk})
        self.assertEqual(r.status_code, 200)
        names = {g["name"]: g["in_pool"] for g in r.json()}
        self.assertTrue(names["Dept A"])
        self.assertFalse(names["Ordinary"])
        self.assertNotIn("Admins2", names)
        self.assertFalse(any(n.startswith("Verleiher") for n in names))

    def test_permissions(self):
        self.assertEqual(
            self.client.get(f"{BASE}/access-groups/", {"pool": self.other_pool.pk}).status_code, 404
        )
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.get(f"{BASE}/access-groups/", {"pool": self.pool.pk}).status_code, 403
        )


class PlaceQrAndOwnerNameTests(PlaceTestBase):
    def test_qr_png_and_owner_name(self):
        place = self.desk(fixed_owner=self.member)
        r = self.client.get(f"{BASE}/places/{place.pk}/qr/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertTrue(r.content.startswith(b"\x89PNG"))
        data = self.client.get(f"{BASE}/places/{place.pk}/").json()
        self.assertEqual(data["fixed_owner_name"], "member")
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(f"{BASE}/places/{place.pk}/qr/").status_code, 403)

