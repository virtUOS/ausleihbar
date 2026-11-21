# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for LTI course links, their system access groups and the guards
that keep those groups visibility-only."""
from basicbar_lti.models import LtiPlatform
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from accounts import roles
from accounts.eligibility import eligible_pool_ids
from accounts.models import AccessGroup
from catalog.models import ResourcePool

from .models import LtiCourseLink, LtiSetting
from .services import create_link, set_link_active

User = get_user_model()


def make_platform(name="Moodle"):
    return LtiPlatform.objects.create(
        name=name,
        issuer=f"https://{name.lower()}.example.org",
        client_id="client-1",
        auth_login_url="https://lms.example.org/auth",
        auth_token_url="https://lms.example.org/token",
    )


class CourseLinkModelTests(TestCase):
    def setUp(self):
        self.platform = make_platform()
        self.pool = ResourcePool.objects.create(name="Physik", pool_id="PHY")
        self.lecturer = User.objects.create_user(username="lecturer")

    def _link(self, **kwargs):
        link, created = create_link(
            platform=self.platform,
            context_id=kwargs.pop("context_id", "course-1"),
            pool=kwargs.pop("pool", self.pool),
            title=kwargs.pop("title", "Experimentalphysik WS"),
            created_by=self.lecturer,
        )
        self.assertTrue(created)
        return link

    def test_create_link_creates_group_attached_to_pool(self):
        link = self._link()
        group = link.access_group
        self.assertEqual(group.name, "Kurs Experimentalphysik WS · Physik")
        self.assertTrue(group.is_system)
        self.assertTrue(group.is_course_group)
        self.assertEqual(list(group.pools.all()), [self.pool])
        self.assertFalse(group.lender_pools.exists())
        self.assertFalse(group.is_admin)

    def test_create_link_is_idempotent_and_refreshes_title(self):
        link = self._link()
        again, created = create_link(
            platform=self.platform, context_id="course-1", pool=self.pool,
            title="Experimentalphysik SoSe",
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, link.pk)
        again.refresh_from_db()
        self.assertEqual(again.title, "Experimentalphysik SoSe")
        self.assertEqual(
            AccessGroup.objects.get(system_course=link).name,
            "Kurs Experimentalphysik SoSe · Physik",
        )

    def test_one_link_per_course_and_pool(self):
        self._link()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LtiCourseLink.objects.create(
                platform=self.platform, context_id="course-1", pool=self.pool
            )

    def test_course_may_link_several_pools(self):
        other = ResourcePool.objects.create(name="Chemie", pool_id="CHE")
        self._link()
        self._link(pool=other)
        self.assertEqual(
            AccessGroup.objects.filter(system_course__context_id="course-1").count(), 2
        )

    def test_group_names_are_unique(self):
        AccessGroup.objects.create(name="Kurs Experimentalphysik WS · Physik")
        link = self._link()
        self.assertEqual(link.access_group.name, "Kurs Experimentalphysik WS · Physik (2)")

    def test_toggle_detaches_and_reattaches_keeping_members(self):
        link = self._link()
        student = User.objects.create_user(username="student")
        group = link.access_group
        group.members.add(student)
        self.assertIn(self.pool.pk, eligible_pool_ids(student))

        set_link_active(link, False)
        self.assertFalse(group.pools.exists())
        self.assertIn(student, group.members.all())

        set_link_active(link, True)
        self.assertEqual(list(group.pools.all()), [self.pool])
        self.assertIn(self.pool.pk, eligible_pool_ids(student))

    def test_switch_off_hides_pool_only_for_course_only_members(self):
        """With a second gate in place, switching one course off hides the
        pool from its course-only members but not from members of another
        active link or of another group."""
        link = self._link()
        other_link = self._link(context_id="course-2", title="Praktikum")
        staff_group = AccessGroup.objects.create(name="Physik-Personal")
        staff_group.pools.add(self.pool)
        only_course, both, staff = (
            User.objects.create_user(username=n) for n in ("only", "both", "staff")
        )
        link.access_group.members.add(only_course, both)
        other_link.access_group.members.add(both)
        staff_group.members.add(staff)

        set_link_active(link, False)
        self.assertNotIn(self.pool.pk, eligible_pool_ids(only_course))
        self.assertIn(self.pool.pk, eligible_pool_ids(both))
        self.assertIn(self.pool.pk, eligible_pool_ids(staff))

    def test_delete_link_deletes_group(self):
        link = self._link()
        group_id = link.access_group.pk
        link.delete()
        self.assertFalse(AccessGroup.objects.filter(pk=group_id).exists())

    def test_hard_pool_delete_cascades_links_and_groups(self):
        link = self._link()
        group_id = link.access_group.pk
        self.pool.delete()
        self.assertFalse(LtiCourseLink.objects.filter(pk=link.pk).exists())
        self.assertFalse(AccessGroup.objects.filter(pk=group_id).exists())

    def test_platform_delete_cascades_links_and_groups(self):
        link = self._link()
        group_id = link.access_group.pk
        self.platform.delete()
        self.assertFalse(LtiCourseLink.objects.filter(pk=link.pk).exists())
        self.assertFalse(AccessGroup.objects.filter(pk=group_id).exists())

    def test_trashed_pool_keeps_link_and_toggle_still_works(self):
        link = self._link()
        self.pool.soft_delete()
        set_link_active(link, False)
        self.assertFalse(link.access_group.pools(manager="all_objects").exists())
        set_link_active(link, True)
        self.assertEqual(
            list(link.access_group.pools(manager="all_objects").values_list("pk", flat=True)),
            [self.pool.pk],
        )

    def test_pool_rename_renames_course_group(self):
        link = self._link()
        self.pool.name = "Physik II"
        self.pool.name_de = "Physik II"
        self.pool.save()
        self.assertEqual(
            AccessGroup.objects.get(system_course=link).name,
            "Kurs Experimentalphysik WS · Physik II",
        )

    def test_course_group_never_grants_lender_rights(self):
        link = self._link()
        group = link.access_group
        with self.assertRaises(ValidationError), transaction.atomic():
            group.lender_pools.add(self.pool)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.pool.lender_groups.add(group)
        self.assertFalse(group.lender_pools.exists())

    def test_course_group_never_admin_or_claim_rule(self):
        group = self._link().access_group
        group.is_admin = True
        with self.assertRaises(ValidationError):
            group.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            group.save()
        group.refresh_from_db()
        group.claim_key, group.claim_values = "groups", ["x"]
        with self.assertRaises(IntegrityError), transaction.atomic():
            group.save()

    def test_owner_field(self):
        self.pool.owner = self.lecturer
        self.pool.save()
        self.assertEqual(list(self.lecturer.owned_pools.all()), [self.pool])
        self.lecturer.delete()
        self.pool.refresh_from_db()
        self.assertIsNone(self.pool.owner)


class ToolEndpointTests(TestCase):
    def test_jwks_endpoint_wired(self):
        res = self.client.get("/lti/jwks/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("keys", res.json())

    def test_login_without_params_is_a_400(self):
        self.assertEqual(self.client.get("/lti/login/").status_code, 400)


class LtiSettingTests(TestCase):
    def test_singleton_defaults_off(self):
        setting = LtiSetting.load()
        self.assertEqual(setting.pk, 1)
        self.assertFalse(setting.instructors_create_pools)
        LtiSetting(instructors_create_pools=True).save()
        self.assertEqual(LtiSetting.objects.count(), 1)
        self.assertTrue(LtiSetting.load().instructors_create_pools)


class AdminRegistrationTests(TestCase):
    def test_models_registered(self):
        for model in (LtiCourseLink, LtiSetting, LtiPlatform):
            self.assertIn(model, admin.site._registry)

    def test_admin_pages_load(self):
        root = User.objects.create_user(
            username="root", is_staff=True, is_superuser=True
        )
        self.client.force_login(root)
        link, _ = create_link(
            platform=make_platform(),
            context_id="c1",
            pool=ResourcePool.objects.create(name="Physik", pool_id="PHY"),
        )
        for url in (
            "/django-admin/lti/ltisetting/",
            "/django-admin/lti/ltisetting/add/",
            "/django-admin/lti/lticourselink/",
            f"/django-admin/lti/lticourselink/{link.pk}/change/",
            f"/django-admin/accounts/accessgroup/{link.access_group.pk}/change/",
            f"/django-admin/catalog/resourcepool/{link.pool_id}/change/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class CourseGroupApiTests(APITestCase):
    """Groups, users and pool APIs treat course groups as locked system groups."""

    URL = "/api/manage/access-groups/"

    def setUp(self):
        self.root = User.objects.create_user(
            username="root", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.root)
        self.pool = ResourcePool.objects.create(name="Physik", pool_id="PHY")
        self.other_pool = ResourcePool.objects.create(name="Chemie", pool_id="CHE")
        self.link, _ = create_link(
            platform=make_platform(), context_id="c1", pool=self.pool, title="Optik"
        )
        self.group = self.link.access_group
        self.student = User.objects.create_user(username="student")
        self.group.members.add(self.student)

    def _detail(self):
        return f"{self.URL}{self.group.pk}/"

    def test_listed_with_course_info(self):
        res = self.client.get(self._detail())
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(
            body["system_course"],
            {
                "id": self.link.pk, "title": "Optik", "context_id": "c1",
                "platform": "Moodle", "pool": self.pool.pk, "is_active": True,
            },
        )
        other = AccessGroup.objects.create(name="Plain")
        self.assertIsNone(self.client.get(f"{self.URL}{other.pk}/").json()["system_course"])

    def test_undeletable(self):
        res = self.client.delete(self._detail())
        self.assertEqual(res.status_code, 400)
        self.assertTrue(AccessGroup.objects.filter(pk=self.group.pk).exists())

    def test_only_description_editable(self):
        for payload in (
            {"name": "Umbenannt"},
            {"pools": [self.other_pool.pk]},
            {"pools": []},
            {"members": []},
            {"lender_pools": [self.pool.pk]},
            {"is_admin": True},
            {"claim_key": "groups", "claim_values": ["x"]},
        ):
            res = self.client.patch(self._detail(), payload, format="json")
            self.assertEqual(res.status_code, 400, payload)
        res = self.client.patch(self._detail(), {"description": "Kursgruppe"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.description, "Kursgruppe")
        self.assertEqual(list(self.group.pools.all()), [self.pool])
        self.assertIn(self.student, self.group.members.all())

    def test_full_form_save_with_current_values_is_fine(self):
        res = self.client.patch(
            self._detail(),
            {
                "name": self.group.name, "pools": [self.pool.pk],
                "members": [self.student.pk], "lender_pools": [],
                "description": "x",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_full_form_save_with_trashed_pool(self):
        self.pool.soft_delete()
        res = self.client.patch(
            self._detail(), {"pools": [], "description": "x"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_not_maintainable_by_lenders(self):
        lender = User.objects.create_user(username="lender")
        roles.ensure_pool_lender_group(self.pool).members.add(lender)
        self.assertNotIn(self.group.pk, roles.maintainable_group_ids(lender))
        self.assertNotIn(self.group.pk, roles.maintainable_group_ids(self.root))

    def test_user_groups_put_keeps_course_membership(self):
        plain = AccessGroup.objects.create(name="Plain")
        url = f"/api/manage/users/{self.student.pk}/groups/"
        res = self.client.put(url, {"group_ids": [plain.pk]}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn(self.student, self.group.members.all())
        # Sending a course group doesn't add anyone either.
        outsider = User.objects.create_user(username="outsider")
        url = f"/api/manage/users/{outsider.pk}/groups/"
        self.client.put(url, {"group_ids": [self.group.pk]}, format="json")
        self.assertNotIn(outsider, self.group.members.all())

    def test_pool_form_save_keeps_course_group(self):
        plain = AccessGroup.objects.create(name="Plain")
        url = f"/api/manage/pools/{self.pool.pk}/"
        body = self.client.get(url).json()
        self.assertEqual(body["access_groups"], [])
        res = self.client.patch(url, {"access_group_ids": [plain.pk]}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            set(self.pool.access_groups.values_list("pk", flat=True)),
            {plain.pk, self.group.pk},
        )
        res = self.client.patch(url, {"access_group_ids": []}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            list(self.pool.access_groups.values_list("pk", flat=True)), [self.group.pk]
        )

    def test_pool_form_cannot_attach_course_group_elsewhere(self):
        url = f"/api/manage/pools/{self.other_pool.pk}/"
        res = self.client.patch(url, {"access_group_ids": [self.group.pk]}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(self.other_pool.access_groups.exists())
