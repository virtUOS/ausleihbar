# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import AccessGroup
from catalog.models import ResourcePool
from desksharing import rights
from desksharing.models import Building, DeskSettings, Floor, Place, Room

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


class GuestAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("guest", password="x")
        self.dept = AccessGroup.objects.create(name="Dept")
        self.guests = AccessGroup.objects.create(name="Guests")
        self.guests.members.add(self.user)
        self.pool = make_pool("P", self.dept)
        self.floor = Floor.objects.create(building=Building.objects.create(code="15"), name="EG")
        self.room = Room.objects.create(floor=self.floor, pool=self.pool, name="R")

    def place(self, name, *groups, **kw):
        p = Place.objects.create(room=self.room, pool=self.pool, name=name, **kw)
        p.access_groups.set(groups)
        return p

    def test_guest_may_book_grouped_place_without_membership(self):
        place = self.place("A", self.guests)
        self.assertNotIn(self.pool.id, rights.member_pool_ids(self.user))
        self.assertTrue(rights.can_book_place(self.user, place))
        self.assertIn(self.pool.id, rights.guest_pool_ids(self.user))
        self.assertIn(self.pool.id, rights.visible_pool_ids(self.user))
        self.assertEqual(rights.guest_place_ids(self.user, self.pool.id), {place.pk})

    def test_guest_may_not_book_ungrouped_place(self):
        place = self.place("A")
        self.assertFalse(rights.can_book_place(self.user, place))
        self.assertNotIn(self.pool.id, rights.guest_pool_ids(self.user))

    def test_member_outside_place_group_still_refused(self):
        self.dept.members.add(self.user)
        other = AccessGroup.objects.create(name="Other")
        place = self.place("A", other)
        self.assertFalse(rights.can_book_place(self.user, place))
        self.assertTrue(rights.can_book_place(self.user, self.place("B")))

    def test_guest_disabled_pool_refused(self):
        place = self.place("A", self.guests)
        DeskSettings.objects.filter(pool=self.pool).update(enabled=False)
        self.assertFalse(rights.can_book_place(self.user, place))
        self.assertEqual(rights.guest_pool_ids(self.user), set())

    def test_guest_pool_ids_excludes_member_pools_and_inactive_places(self):
        self.place("Off", self.guests, is_active=False)
        self.assertEqual(rights.guest_pool_ids(self.user), set())
        user2 = User.objects.create_user("g2", password="x")
        self.guests.members.add(user2)
        self.dept.members.add(user2)
        self.place("On", self.guests)
        self.assertEqual(rights.guest_pool_ids(user2), set())
        self.assertEqual(rights.guest_pool_ids(self.user), {self.pool.id})
        self.room.is_active = False
        self.room.save()
        user3 = User.objects.create_user("g3", password="x")
        self.guests.members.add(user3)
        self.assertEqual(rights.guest_pool_ids(user3), set())

    def test_guest_place_ids_none_for_member(self):
        self.dept.members.add(self.user)
        self.place("A", self.guests)
        self.assertIsNone(rights.guest_place_ids(self.user, self.pool.id))

    def test_may_keep_booking_false_after_group_removed(self):
        place = self.place("A", self.guests)
        self.assertTrue(rights.may_keep_booking(self.user, place, self.pool.id))
        self.guests.members.remove(self.user)
        user = User.objects.get(pk=self.user.pk)
        self.assertFalse(rights.may_keep_booking(user, place, self.pool.id))

    def test_guest_keeps_booking_when_place_moves(self):
        place = self.place("A", self.guests)
        other = make_pool("Q", AccessGroup.objects.create(name="Q"))
        place.pool = other
        place.save()
        self.assertTrue(rights.may_keep_booking(self.user, place, self.pool.id))
        self.guests.members.remove(self.user)
        user = User.objects.get(pk=self.user.pk)
        self.assertFalse(rights.may_keep_booking(user, place, self.pool.id))


class FirstDepartmentSetupTests(TestCase):
    """An app admin reaches the settings of a pool before any department is
    enabled (whoami ``desk_setup_pools``, settings and groups endpoints)."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.group = AccessGroup.objects.create(name="Setup Dept")
        self.pool = new_pool("Setup")
        self.group.pools.add(self.pool)
        self.admin = User.objects.create_user("setup_admin", password="x", is_staff=True)
        self.client = APIClient()
        self.client.force_login(self.admin)

    def test_admin_without_departments_sees_setup_pools(self):
        data = self.client.get("/api/whoami/").json()
        self.assertEqual(data["desk_pool_ids"], [])
        self.assertIn({"id": self.pool.id, "name": "Setup"}, data["desk_setup_pools"])

    def test_admin_enables_first_department(self):
        groups = self.client.get(f"/api/desks/manage/access-groups/?pool={self.pool.id}")
        self.assertEqual(groups.status_code, 200)
        self.assertTrue(
            next(g for g in groups.json() if g["id"] == self.group.id)["in_pool"]
        )
        url = f"/api/desks/manage/settings/{self.pool.id}/"
        self.assertEqual(self.client.get(url).status_code, 200)
        res = self.client.put(url, {"enabled": True}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        data = self.client.get("/api/whoami/").json()
        self.assertIn(self.pool.id, data["desk_pool_ids"])
        self.assertNotIn(self.pool.id, [p["id"] for p in data["desk_setup_pools"]])

    def test_others_get_no_setup(self):
        from rest_framework.test import APIClient

        lender = User.objects.create_user("setup_lender", password="x")
        lenders = AccessGroup.objects.create(name="Setup lenders")
        lenders.lender_pools.add(self.pool)
        lenders.members.add(lender)
        plain = User.objects.create_user("setup_plain", password="x")
        for user in (lender, plain):
            client = APIClient()
            client.force_login(user)
            self.assertEqual(client.get("/api/whoami/").json()["desk_setup_pools"], [])
        client = APIClient()
        client.force_login(plain)
        self.assertEqual(
            client.get(f"/api/desks/manage/settings/{self.pool.id}/").status_code, 404
        )
        self.assertEqual(
            client.get(f"/api/desks/manage/access-groups/?pool={self.pool.id}").status_code,
            403,
        )
