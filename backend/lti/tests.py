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


class CourseGroupEligibilityTests(APITestCase):
    """Course groups never decide whether a pool is open: a pool is open iff
    it has no ordinary access group and no owner; course groups only add
    eligibility for their members (``accounts.eligibility``)."""

    def setUp(self):
        from accounts.testing import make_lender
        from catalog.models import Product, ProductType, Resource

        self.platform = make_platform()
        self.lecturer = User.objects.create_user(username="lecturer")
        self.member = User.objects.create_user(username="member")
        self.stranger = User.objects.create_user(username="stranger")
        self.open_pool = ResourcePool.objects.create(name="Offen", pool_id="OPEN")
        self.personal = ResourcePool.objects.create(
            name="Lehrstuhl", pool_id="CHAIR", owner=self.lecturer
        )
        make_lender(self.lecturer, self.personal)
        product_type = ProductType.objects.create(name="Kamera")
        self.product = Product.objects.create(product_type=product_type, title="Cam")
        Resource.objects.create(
            product=self.product, resource_pool=self.personal,
            inventory_number="CHAIR-1", qr_code_id="QR-CHAIR-1",
        )

    def _link(self, pool, context_id="course-1"):
        link, _ = create_link(
            platform=self.platform, context_id=context_id, pool=pool, title="Kurs"
        )
        return link

    def _shop_pool_ids(self, user):
        if user is None:
            self.client.logout()
        else:
            self.client.force_authenticate(user)
        response = self.client.get("/api/pools/")
        self.assertEqual(response.status_code, 200)
        return {p["id"] for p in response.data}

    def _sees_product(self, user):
        from accounts.eligibility import visible_products
        from catalog.models import Product

        return visible_products(Product.objects.all(), user).filter(
            pk=self.product.pk
        ).exists()

    def test_linking_a_course_does_not_close_an_open_pool(self):
        link = self._link(self.open_pool)
        link.access_group.members.add(self.member)
        for user in (self.member, self.stranger, None):
            self.assertIn(self.open_pool.pk, self._shop_pool_ids(user))
        from django.contrib.auth.models import AnonymousUser

        self.assertIn(self.open_pool.pk, eligible_pool_ids(AnonymousUser()))

    def test_personal_pool_without_links_is_restricted(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertNotIn(self.personal.pk, eligible_pool_ids(self.stranger))
        self.assertNotIn(self.personal.pk, eligible_pool_ids(AnonymousUser()))
        self.assertNotIn(self.personal.pk, self._shop_pool_ids(None))
        # The owner reaches it as its lender.
        self.assertIn(self.personal.pk, eligible_pool_ids(self.lecturer))

    def test_active_link_opens_personal_pool_to_course_members_only(self):
        link = self._link(self.personal)
        link.access_group.members.add(self.member)
        self.assertIn(self.personal.pk, self._shop_pool_ids(self.member))
        self.assertTrue(self._sees_product(self.member))
        self.assertNotIn(self.personal.pk, self._shop_pool_ids(self.stranger))
        self.assertFalse(self._sees_product(self.stranger))
        self.assertNotIn(self.personal.pk, self._shop_pool_ids(None))

    def test_switching_off_last_link_keeps_personal_pool_restricted(self):
        link = self._link(self.personal)
        link.access_group.members.add(self.member)
        set_link_active(link, False)
        for user in (self.member, self.stranger, None):
            self.assertNotIn(self.personal.pk, self._shop_pool_ids(user))
        self.assertFalse(self._sees_product(self.member))
        self.assertFalse(self._sees_product(self.stranger))

    def test_ordinary_group_plus_course_group_stays_restricted(self):
        staff_group = AccessGroup.objects.create(name="Personal")
        staff_group.pools.add(self.open_pool)
        staff = User.objects.create_user(username="staff")
        staff_group.members.add(staff)
        link = self._link(self.open_pool)
        link.access_group.members.add(self.member)

        self.assertIn(self.open_pool.pk, eligible_pool_ids(self.member))
        self.assertIn(self.open_pool.pk, eligible_pool_ids(staff))
        self.assertNotIn(self.open_pool.pk, eligible_pool_ids(self.stranger))
        self.assertNotIn(self.open_pool.pk, self._shop_pool_ids(None))

        set_link_active(link, False)
        self.assertNotIn(self.open_pool.pk, eligible_pool_ids(self.member))
        self.assertIn(self.open_pool.pk, eligible_pool_ids(staff))


class CourseGroupDeskRightsTests(TestCase):
    """Course groups open a pool's lending only — never desksharing."""

    def test_course_group_neither_enables_desks_nor_grants_membership(self):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from desksharing import rights
        from desksharing.assignment import ensure_desksharing_enabled
        from desksharing.models import DeskSettings

        platform = make_platform()
        pool = ResourcePool.objects.create(name="Abteilung", pool_id="DEPT")
        link, _ = create_link(platform=platform, context_id="c", pool=pool)
        student = User.objects.create_user(username="student")
        link.access_group.members.add(student)

        with self.assertRaises(DjangoValidationError):
            ensure_desksharing_enabled(pool)

        # With an ordinary group the department runs; course members still
        # aren't desk members.
        AccessGroup.objects.create(name="Abteilungsteam").pools.add(pool)
        ensure_desksharing_enabled(pool)
        self.assertTrue(DeskSettings.for_pool(pool).enabled)
        self.assertNotIn(pool.pk, rights.member_pool_ids(student))


# --- Launch flow (simulated platform) ----------------------------------------
#
# The tests act as the LMS: they hold a platform RSA keypair (published to the
# tool as an inline ``key_set``), run the OIDC initiation to obtain state and
# nonce, then POST a signed ``id_token`` to the launch endpoint — the same
# handshake Moodle or Stud.IP performs.

CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
ISSUER = "https://lms.example.edu"
CLIENT_ID = "ausleihbar-client"
DEPLOYMENT = "deployment-1"
TOOL_LAUNCH = "http://testserver/lti/launch/"
INSTRUCTOR = ["http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"]
LEARNER = ["http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"]


class LaunchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        import json

        from jwcrypto import jwk

        cls.platform_jwk = jwk.JWK.generate(kty="RSA", size=2048, kid="platform-key")
        cls.platform_private_pem = cls.platform_jwk.export_to_pem(
            private_key=True, password=None
        )
        public_jwk = json.loads(cls.platform_jwk.export_public())
        public_jwk.update({"alg": "RS256", "use": "sig"})
        cls.platform = LtiPlatform.objects.create(
            name="Test-LMS",
            issuer=ISSUER,
            client_id=CLIENT_ID,
            auth_login_url=f"{ISSUER}/auth",
            auth_token_url=f"{ISSUER}/token",
            key_set={"keys": [public_jwk]},
            deployment_ids=[DEPLOYMENT],
        )

    def setUp(self):
        self.pool = ResourcePool.objects.create(name="Physik", pool_id="PHY")
        self.other_pool = ResourcePool.objects.create(name="Chemie", pool_id="CHE")

    # -- the platform side of the handshake --------------------------------

    def start_login(self):
        from urllib.parse import parse_qs, urlparse

        response = self.client.post(
            "/lti/login/",
            {
                "iss": ISSUER,
                "client_id": CLIENT_ID,
                "login_hint": "user-1",
                "target_link_uri": TOOL_LAUNCH,
                "lti_message_hint": "hint",
            },
        )
        self.assertEqual(response.status_code, 302, response.content)
        query = parse_qs(urlparse(response["Location"]).query)
        return query["state"][0], query["nonce"][0], query["redirect_uri"][0]

    def make_id_token(self, nonce, roles=INSTRUCTOR, sub="user-1",
                      context=None, extra=None, key_pem=None):
        import time

        import jwt

        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": sub,
            "iat": now,
            "exp": now + 300,
            "nonce": nonce,
            "given_name": "Frida",
            "family_name": "Lehrend",
            "email": f"{sub}@lms.example.edu",
            f"{CLAIM}message_type": "LtiResourceLinkRequest",
            f"{CLAIM}version": "1.3.0",
            f"{CLAIM}deployment_id": DEPLOYMENT,
            f"{CLAIM}target_link_uri": TOOL_LAUNCH,
            f"{CLAIM}roles": roles,
            f"{CLAIM}resource_link": {"id": "link-1"},
            f"{CLAIM}context": (
                context if context is not None
                else {"id": "course-42", "title": "Biologie 101"}
            ),
        }
        if extra:
            payload.update(extra)
        return jwt.encode(
            payload, key_pem or self.platform_private_pem, algorithm="RS256",
            headers={"kid": "platform-key"},
        )

    def launch(self, framed=False, **token_kwargs):
        state, nonce, redirect_uri = self.start_login()
        headers = {"HTTP_ACCEPT_LANGUAGE": "de"}
        if framed:
            headers["HTTP_SEC_FETCH_DEST"] = "iframe"
        return self.client.post(
            redirect_uri,
            {"state": state, "id_token": self.make_id_token(nonce, **token_kwargs)},
            **headers,
        )

    def lti_user(self, sub="user-1"):
        return User.objects.get(subject=f"lti:{self.platform.pk}:{sub}")

    def get_de(self, url):
        return self.client.get(url, HTTP_ACCEPT_LANGUAGE="de")

    def post_de(self, url, data):
        return self.client.post(url, data, HTTP_ACCEPT_LANGUAGE="de")


class InstructorLaunchTests(LaunchTestCase):
    def _instructor_with_pool(self):
        from accounts.testing import make_lender

        response = self.launch()
        user = self.lti_user()
        make_lender(user, self.pool)
        return response, user

    def test_launch_logs_in_and_redirects_to_course_page(self):
        response, user = self._instructor_with_pool()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://testserver/lti/course/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(user.first_name, "Frida")

    def test_course_page_lists_managed_pools_only(self):
        self._instructor_with_pool()
        response = self.get_de("/lti/course/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kurs verknüpfen")
        self.assertContains(response, "Biologie 101")
        self.assertContains(response, "Physik")
        self.assertNotContains(response, "Chemie")
        # Switch off: no "create pool" form.
        self.assertNotContains(response, 'action="/lti/course/pool/"')

    def test_link_pool(self):
        _, user = self._instructor_with_pool()
        response = self.post_de("/lti/course/link/", {"pool": self.pool.pk})
        self.assertRedirects(response, "/lti/course/", fetch_redirect_response=False)
        link = LtiCourseLink.objects.get(platform=self.platform, context_id="course-42")
        self.assertEqual(link.pool, self.pool)
        self.assertTrue(link.is_active)
        self.assertEqual(link.title, "Biologie 101")
        self.assertEqual(link.created_by, user)
        self.assertEqual(list(link.access_group.pools.all()), [self.pool])
        # Instructors are lenders; they never join the course group.
        self.assertFalse(link.access_group.members.exists())
        page = self.get_de("/lti/course/")
        self.assertContains(page, f"/pools/{self.pool.pk}")
        self.assertContains(page, "aktiv")

    def test_link_switches_an_inactive_link_back_on(self):
        _, user = self._instructor_with_pool()
        link, _ = create_link(
            platform=self.platform, context_id="course-42", pool=self.pool
        )
        set_link_active(link, False)
        self.assertContains(self.get_de("/lti/course/"), "Wieder einschalten")
        self.post_de("/lti/course/link/", {"pool": self.pool.pk})
        link.refresh_from_db()
        self.assertTrue(link.is_active)

    def test_link_foreign_pool_refused(self):
        self._instructor_with_pool()
        response = self.post_de("/lti/course/link/", {"pool": self.other_pool.pk})
        self.assertEqual(response.status_code, 403)
        response = self.post_de("/lti/course/link/", {"pool": "nope"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LtiCourseLink.objects.exists())

    def test_course_pages_need_the_launch_session(self):
        self.assertEqual(self.get_de("/lti/course/").status_code, 403)
        self.assertEqual(
            self.post_de("/lti/course/link/", {"pool": self.pool.pk}).status_code, 403
        )
        # A plain (non-LTI) login is not enough either.
        user = User.objects.create_user(username="someone")
        self.client.force_login(user)
        response = self.get_de("/lti/course/")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Sitzung", status_code=403)

    def test_create_pool_refused_while_switch_off(self):
        self._instructor_with_pool()
        response = self.post_de("/lti/course/pool/", {"name": "Mein Pool"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ResourcePool.all_objects.filter(owner__isnull=False).exists())

    def test_create_personal_pool_with_switch_on(self):
        LtiSetting.objects.update_or_create(
            pk=1, defaults={"instructors_create_pools": True}
        )
        _, user = self._instructor_with_pool()
        page = self.get_de("/lti/course/")
        self.assertContains(page, "Eigenen Pool anlegen")
        response = self.post_de("/lti/course/pool/", {"name": "  Labor Frida  "})
        self.assertRedirects(response, "/lti/course/", fetch_redirect_response=False)
        pool = ResourcePool.objects.get(owner=user)
        self.assertEqual(roles._pool_name(pool), "Labor Frida")  # trimmed
        self.assertTrue(pool.is_active)
        self.assertEqual(pool.opening_hours, {})
        self.assertTrue(pool.pool_id)
        group = AccessGroup.objects.get(system_pool=pool)
        self.assertIn(user, group.members.all())
        user = User.objects.get(pk=user.pk)  # fresh role cache
        self.assertIn(pool.pk, roles.managed_pool_ids(user))
        link = LtiCourseLink.objects.get(pool=pool)
        self.assertEqual(link.context_id, "course-42")
        self.assertTrue(link.is_active)
        # Personal pools stay restricted: strangers don't see them.
        stranger = User.objects.create_user(username="stranger")
        self.assertNotIn(pool.pk, eligible_pool_ids(stranger))

    def test_create_pool_with_taken_or_empty_name_shows_error(self):
        LtiSetting.objects.update_or_create(
            pk=1, defaults={"instructors_create_pools": True}
        )
        self._instructor_with_pool()
        response = self.post_de("/lti/course/pool/", {"name": "physik"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response, "Es gibt schon einen Pool mit diesem Namen.", status_code=400
        )
        response = self.post_de("/lti/course/pool/", {"name": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ResourcePool.all_objects.count(), 2)

    def test_create_pool_needs_csrf(self):
        from django.test import Client

        LtiSetting.objects.update_or_create(
            pk=1, defaults={"instructors_create_pools": True}
        )
        self._instructor_with_pool()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.cookies = self.client.cookies
        response = csrf_client.post("/lti/course/pool/", {"name": "Ohne Token"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ResourcePool.all_objects.filter(name_de="Ohne Token").exists())
        # With the token from the page it works.
        page = csrf_client.get("/lti/course/")
        token = page.context["csrf_token"]
        response = csrf_client.post(
            "/lti/course/pool/", {"name": "Mit Token", "csrfmiddlewaretoken": token}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ResourcePool.objects.filter(name_de="Mit Token").exists())

    def test_framed_launch_opens_course_page_in_new_tab(self):
        response = self.launch(framed=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "In Ausleihbar öffnen")
        # A one-time hand-off link, not the course page itself.
        self.assertContains(response, 'href="http://testserver/lti/continue/')
        self.assertNotContains(response, 'href="http://testserver/lti/course/"')
        self.assertContains(response, 'target="_blank"')
        # Allowed in the LMS frame, no inline script/style.
        self.assertIn("frame-ancestors", response["Content-Security-Policy"])
        self.assertNotIn("<script", response.content.decode())
        self.assertNotIn("<style", response.content.decode())

    def test_launch_refreshes_course_title_on_all_links(self):
        link, _ = create_link(
            platform=self.platform, context_id="course-42", pool=self.pool,
            title="Alter Titel",
        )
        inactive, _ = create_link(
            platform=self.platform, context_id="course-42", pool=self.other_pool,
            title="Alter Titel",
        )
        set_link_active(inactive, False)
        self.launch()
        for item in (link, inactive):
            item.refresh_from_db()
            self.assertEqual(item.title, "Biologie 101")
        self.assertTrue(
            AccessGroup.objects.get(system_course=link).name.startswith(
                "Kurs Biologie 101"
            )
        )


class LearnerLaunchTests(LaunchTestCase):
    def _launch_learner(self, **kwargs):
        return self.launch(roles=LEARNER, sub="student-1", **kwargs)

    def test_single_active_link_redirects_to_pool_page(self):
        from django.conf import settings

        link, _ = create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        response = self._launch_learner()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{settings.SHOP_BASE_URL.rstrip('/')}/pools/{self.pool.pk}",
        )
        student = self.lti_user("student-1")
        self.assertIn(student, link.access_group.members.all())
        self.assertEqual(int(self.client.session["_auth_user_id"]), student.pk)
        self.assertFalse(roles.managed_pool_ids(student))
        self.assertFalse(roles.is_app_admin(student))

    def test_several_links_show_chooser(self):
        for pool in (self.pool, self.other_pool):
            create_link(platform=self.platform, context_id="course-42", pool=pool)
        response = self._launch_learner()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pool auswählen")
        self.assertContains(response, f"/pools/{self.pool.pk}")
        self.assertContains(response, f"/pools/{self.other_pool.pk}")
        student = self.lti_user("student-1")
        self.assertEqual(student.access_groups.count(), 2)

    def test_only_active_links_of_active_pools_are_joined(self):
        active, _ = create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        off, _ = create_link(
            platform=self.platform, context_id="course-42", pool=self.other_pool
        )
        set_link_active(off, False)
        inactive_pool = ResourcePool.objects.create(
            name="Zu", pool_id="ZU", is_active=False
        )
        create_link(platform=self.platform, context_id="course-42", pool=inactive_pool)
        other_course, _ = create_link(
            platform=self.platform, context_id="course-43", pool=self.other_pool
        )
        response = self._launch_learner()
        self.assertEqual(response.status_code, 302)
        student = self.lti_user("student-1")
        self.assertEqual(
            set(student.access_groups.all()), {active.access_group}
        )

    def test_inactive_only_course_shows_friendly_page(self):
        link, _ = create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        set_link_active(link, False)
        response = self._launch_learner()
        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response, "noch nicht mit Ausleihbar verknüpft", status_code=404
        )
        self.assertFalse(link.access_group.members.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unlinked_course_shows_friendly_page(self):
        response = self._launch_learner()
        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response, "Dieser Kurs ist noch nicht mit Ausleihbar verknüpft",
            status_code=404,
        )
        self.assertFalse(AccessGroup.objects.filter(members__isnull=False).exists())
        self.assertFalse(User.objects.filter(subject__startswith="lti:").exists())

    def test_framed_launch_offers_new_tab(self):
        create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        response = self._launch_learner(framed=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "In Ausleihbar öffnen")
        self.assertContains(response, 'href="http://testserver/lti/continue/')
        self.assertNotContains(response, f"/pools/{self.pool.pk}")
        self.assertContains(response, 'target="_blank"')

    def test_learner_session_cannot_use_instructor_pages(self):
        from accounts.testing import make_lender

        create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        self._launch_learner()
        student = self.lti_user("student-1")
        make_lender(student, self.other_pool)  # lender elsewhere
        self.assertEqual(self.get_de("/lti/course/").status_code, 403)
        response = self.post_de("/lti/course/link/", {"pool": self.other_pool.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LtiCourseLink.objects.filter(pool=self.other_pool).exists())


class LaunchGrantsTests(LaunchTestCase):
    def test_launch_opens_personal_pool_until_link_is_switched_off(self):
        owner = User.objects.create_user(username="owner")
        personal = ResourcePool.objects.create(
            name="Lehrstuhl", pool_id="CHAIR", owner=owner
        )
        link, _ = create_link(platform=self.platform, context_id="course-42", pool=personal)
        self.assertEqual(self.client.get(f"/api/pools/{personal.pk}/").status_code, 404)
        response = self.launch(roles=LEARNER, sub="student-1")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(f"/api/pools/{personal.pk}/").status_code, 200)
        set_link_active(link, False)
        self.assertEqual(self.client.get(f"/api/pools/{personal.pk}/").status_code, 404)

    def test_launch_claims_never_match_claim_groups(self):
        """The LMS controls the launch payload stored in ``claims``; claim rules
        (which may grant lender rights) apply to IdP claims only."""
        group = AccessGroup.objects.create(
            name="Claim-Verleiher", claim_key="email",
            claim_values=["student-1@lms.example.edu"],
        )
        group.lender_pools.add(self.other_pool)
        group.pools.add(self.other_pool)
        create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        self.launch(roles=LEARNER, sub="student-1")
        student = self.lti_user("student-1")
        self.assertEqual(student.claims.get("email"), "student-1@lms.example.edu")
        self.assertFalse(roles.managed_pool_ids(student))
        self.assertNotIn(group.pk, roles.group_ids(student))
        self.assertNotIn(student.pk, roles.pool_lender_ids(self.other_pool))
        self.assertNotIn(student, [u for u, _ in roles.effective_members(group)])
        # An OIDC account with the same claim still matches.
        oidc_user = User.objects.create_user(
            username="oidc", subject="oidc-sub",
            claims={"email": "student-1@lms.example.edu"},
        )
        self.assertIn(self.other_pool.pk, roles.managed_pool_ids(oidc_user))


class LaunchErrorTests(LaunchTestCase):
    def test_unknown_platform_is_a_403_page(self):
        state, nonce, redirect_uri = self.start_login()
        LtiPlatform.objects.filter(pk=self.platform.pk).update(is_active=False)
        response = self.client.post(
            redirect_uri,
            {"state": state, "id_token": self.make_id_token(nonce)},
            HTTP_ACCEPT_LANGUAGE="de",
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Unbekannte Plattform", status_code=403)
        self.assertFalse(User.objects.filter(subject__startswith="lti:").exists())

    def test_tampered_token_is_a_400_page(self):
        from jwcrypto import jwk

        foreign = jwk.JWK.generate(kty="RSA", size=2048, kid="platform-key")
        response = self.launch(
            key_pem=foreign.export_to_pem(private_key=True, password=None)
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(subject__startswith="lti:").exists())

    def test_unknown_state_is_a_400_page(self):
        _, nonce, redirect_uri = self.start_login()
        response = self.client.post(
            redirect_uri, {"state": "forged", "id_token": self.make_id_token(nonce)}
        )
        self.assertEqual(response.status_code, 400)

    def test_launch_without_course_is_a_400_page(self):
        response = self.launch(context={})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "keinen Kurs", status_code=400)

    def test_launch_is_post_only(self):
        self.assertEqual(self.client.get("/lti/launch/").status_code, 405)


class LaunchInfrastructureTests(TestCase):
    def test_default_cache_is_shared_database_cache(self):
        """pylti1p3 keeps state/nonce in the "default" cache between login and
        launch, which may run in different gunicorn workers."""
        from django.core.cache import caches
        from django.core.cache.backends.db import DatabaseCache
        from django.core.cache.backends.locmem import LocMemCache

        self.assertIsInstance(caches["default"], DatabaseCache)
        caches["default"].set("lti-probe", "ok", 60)
        self.assertEqual(caches["default"].get("lti-probe"), "ok")
        self.assertIsInstance(caches["throttle"], LocMemCache)

    def test_session_cookie_samesite_default_lax(self):
        from django.conf import settings

        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")

    def test_lti_stylesheet_is_a_static_file(self):
        from django.contrib.staticfiles import finders

        self.assertTrue(finders.find("lti/lti.css"))


# --- Task 3: hand-off, cache housekeeping, management APIs ------------------


class HandoffTests(LaunchTestCase):
    """Framed launches hand the session to the new tab via one-time links."""

    def _continue_urls(self, response):
        import re

        return re.findall(r'href="(http://testserver/lti/continue/[^"]+)"',
                          response.content.decode())

    def _fresh_client(self):
        return self.client_class()

    def test_instructor_handoff_logs_in_and_restores_course_session(self):
        response = self.launch(framed=True)
        [url] = self._continue_urls(response)
        tab = self._fresh_client()
        response = tab.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://testserver/lti/course/")
        page = tab.get("/lti/course/", HTTP_ACCEPT_LANGUAGE="de")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Biologie 101")
        self.assertEqual(int(tab.session["_auth_user_id"]), self.lti_user().pk)

    def test_learner_handoff_redirects_to_pool_and_is_logged_in(self):
        from django.conf import settings

        create_link(platform=self.platform, context_id="course-42", pool=self.pool)
        create_link(platform=self.platform, context_id="course-42", pool=self.other_pool)
        response = self.launch(framed=True, roles=LEARNER, sub="student-1")
        urls = self._continue_urls(response)
        self.assertEqual(len(urls), 2)  # one token per button
        tab = self._fresh_client()
        response = tab.get(urls[0])
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(
            settings.SHOP_BASE_URL.rstrip("/") + "/pools/"
        ))
        self.assertEqual(
            int(tab.session["_auth_user_id"]), self.lti_user("student-1").pk
        )
        # The other button still works (its own token).
        self.assertEqual(self._fresh_client().get(urls[1]).status_code, 302)

    def test_token_is_single_use(self):
        response = self.launch(framed=True)
        [url] = self._continue_urls(response)
        self.assertEqual(self._fresh_client().get(url).status_code, 302)
        tab = self._fresh_client()
        response = tab.get(url, HTTP_ACCEPT_LANGUAGE="de")
        self.assertEqual(response.status_code, 410)
        self.assertContains(response, "abgelaufen", status_code=410)
        self.assertNotIn("_auth_user_id", tab.session)

    def test_expired_token_refused(self):
        from django.core.cache import cache

        from .views import HANDOFF_PREFIX

        response = self.launch(framed=True)
        [url] = self._continue_urls(response)
        key = HANDOFF_PREFIX + url.rstrip("/").rsplit("/", 1)[-1]
        cache.set(key, cache.get(key), -5)  # past its lifetime
        tab = self._fresh_client()
        self.assertEqual(tab.get(url).status_code, 410)
        self.assertNotIn("_auth_user_id", tab.session)

    def test_ttl_is_two_minutes(self):
        from .views import HANDOFF_TTL

        self.assertEqual(HANDOFF_TTL, 120)

    def test_unknown_token_refused(self):
        self.assertEqual(self.client.get("/lti/continue/nope/").status_code, 410)

    def _plant(self, next_url, user=None, token="planted-token"):
        from django.core.cache import cache

        from .views import HANDOFF_PREFIX

        user = user or User.objects.get_or_create(username="planted")[0]
        cache.set(
            HANDOFF_PREFIX + token,
            {"user_id": user.pk, "next": next_url, "course": None}, 60,
        )
        return f"/lti/continue/{token}/"

    def test_foreign_next_refused(self):
        for target in ("https://evil.example/x", "//evil.example/x",
                       "javascript:alert(1)"):
            with self.subTest(target=target):
                tab = self._fresh_client()
                self.assertEqual(tab.get(self._plant(target)).status_code, 410)
                self.assertNotIn("_auth_user_id", tab.session)

    def test_local_path_and_shop_targets_allowed(self):
        from django.conf import settings

        for target in ("/lti/course/", settings.SHOP_BASE_URL.rstrip("/") + "/pools/1"):
            with self.subTest(target=target):
                response = self._fresh_client().get(self._plant(target))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], target)

    def test_inactive_user_refused(self):
        user = User.objects.create_user(username="gone", is_active=False)
        tab = self._fresh_client()
        self.assertEqual(tab.get(self._plant("/lti/course/", user=user)).status_code, 410)
        self.assertNotIn("_auth_user_id", tab.session)

    def test_handoff_url_refuses_foreign_target(self):
        from django.test import RequestFactory

        from .views import handoff_url

        request = RequestFactory().get("/lti/launch/")
        user = User.objects.create_user(username="someone")
        with self.assertRaises(ValueError):
            handoff_url(request, user, "https://evil.example/", None)


class PurgeCacheTests(TestCase):
    def _keys(self):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key FROM django_cache")
            return {row[0] for row in cursor.fetchall()}

    def test_deletes_only_expired_rows(self):
        from io import StringIO

        from django.core.cache import cache
        from django.core.management import call_command

        cache.set("purge-old", 1, -5)
        cache.set("purge-new", 1, 600)
        keys = self._keys()
        self.assertTrue(any(k.endswith("purge-old") for k in keys))
        out = StringIO()
        call_command("lti_purge_cache", stdout=out)
        keys = self._keys()
        self.assertFalse(any(k.endswith("purge-old") for k in keys))
        self.assertTrue(any(k.endswith("purge-new") for k in keys))
        self.assertIn("Deleted 1 expired", out.getvalue())


class ManageApiTestCase(APITestCase):
    def setUp(self):
        from accounts.testing import make_lender

        self.admin = User.objects.create_user(username="admin", is_staff=True)
        # Admin via an access group, not the Django flag.
        self.group_admin = User.objects.create_user(username="groupadmin")
        AccessGroup.objects.create(name="Admins (Test)", is_admin=True).members.add(
            self.group_admin
        )
        self.owner = User.objects.create_user(
            username="lecturer", first_name="Frida", last_name="Lehrend"
        )
        self.colleague = User.objects.create_user(username="colleague")
        self.other_lender = User.objects.create_user(username="other")
        self.borrower = User.objects.create_user(username="borrower")
        self.pool = ResourcePool.objects.create(
            name="Lehrstuhl", pool_id="CHAIR", owner=self.owner
        )
        self.other_pool = ResourcePool.objects.create(name="Chemie", pool_id="CHE")
        make_lender(self.owner, self.pool)
        make_lender(self.colleague, self.pool)
        make_lender(self.other_lender, self.other_pool)

    def as_user(self, user):
        self.client.force_authenticate(user)


class LtiSettingApiTests(ManageApiTestCase):
    URL = "/api/manage/lti-setting/"

    def test_admin_reads_and_writes(self):
        for admin in (self.admin, self.group_admin):
            with self.subTest(admin=admin.username):
                self.as_user(admin)
                LtiSetting.objects.all().delete()
                self.assertEqual(
                    self.client.get(self.URL).data, {"instructors_create_pools": False}
                )
                response = self.client.put(
                    self.URL, {"instructors_create_pools": True}, format="json"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, {"instructors_create_pools": True})
                self.assertTrue(LtiSetting.load().instructors_create_pools)

    def test_others_refused(self):
        for user in (self.owner, self.other_lender, self.borrower):
            with self.subTest(user=user.username):
                self.as_user(user)
                self.assertEqual(self.client.get(self.URL).status_code, 403)
                response = self.client.put(
                    self.URL, {"instructors_create_pools": True}, format="json"
                )
                self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertFalse(LtiSetting.load().instructors_create_pools)


class LtiPlatformApiTests(ManageApiTestCase):
    URL = "/api/manage/lti/platforms/"
    DATA = {
        "name": "Stud.IP",
        "issuer": "https://studip.example.org",
        "client_id": "abc",
        "auth_login_url": "https://studip.example.org/auth",
        "auth_token_url": "https://studip.example.org/token",
        "key_set_url": "https://studip.example.org/jwks",
        "deployment_ids": ["1"],
        "link_by_email": False,
        "is_active": True,
    }

    def test_admin_crud(self):
        self.as_user(self.group_admin)
        response = self.client.post(self.URL, self.DATA, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        listing = self.client.get(self.URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([p["name"] for p in listing.data["results"]], ["Stud.IP"])
        response = self.client.patch(
            f"{self.URL}{pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LtiPlatform.objects.get(pk=pk).is_active)
        self.assertEqual(self.client.delete(f"{self.URL}{pk}/").status_code, 204)

    def test_others_refused(self):
        platform = make_platform()
        for user in (self.owner, self.borrower):
            with self.subTest(user=user.username):
                self.as_user(user)
                self.assertEqual(self.client.get(self.URL).status_code, 403)
                self.assertEqual(
                    self.client.post(self.URL, self.DATA, format="json").status_code, 403
                )
                self.assertEqual(
                    self.client.delete(f"{self.URL}{platform.pk}/").status_code, 403
                )


class LtiToolInfoApiTests(ManageApiTestCase):
    URL = "/api/manage/lti/tool/"

    def test_admin_gets_urls_and_public_key(self):
        self.as_user(self.admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["login_url"], "http://testserver/lti/login/")
        self.assertEqual(response.data["launch_url"], "http://testserver/lti/launch/")
        self.assertEqual(response.data["jwks_url"], "http://testserver/lti/jwks/")
        self.assertTrue(
            response.data["public_key"].startswith("-----BEGIN PUBLIC KEY-----")
        )

    def test_others_refused(self):
        for user in (self.owner, self.borrower):
            with self.subTest(user=user.username):
                self.as_user(user)
                self.assertEqual(self.client.get(self.URL).status_code, 403)


class PoolCoursesApiTests(ManageApiTestCase):
    def setUp(self):
        super().setUp()
        self.platform = make_platform()
        self.link, _ = create_link(
            platform=self.platform, context_id="c1", pool=self.pool, title="Optik",
            created_by=self.owner,
        )
        self.students = [User.objects.create_user(username=f"s{i}") for i in range(2)]
        self.link.access_group.members.add(*self.students)
        self.other_link, _ = create_link(
            platform=self.platform, context_id="c2", pool=self.other_pool
        )

    def url(self, link=None, pool=None):
        base = f"/api/manage/pools/{(pool or self.pool).pk}/courses/"
        return f"{base}{link.pk}/" if link else base

    def test_list_shape(self):
        self.as_user(self.owner)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        [row] = response.data
        self.assertEqual(row["id"], self.link.pk)
        self.assertEqual(row["title"], "Optik")
        self.assertEqual(row["context_id"], "c1")
        self.assertEqual(row["platform"], {"id": self.platform.pk, "name": "Moodle"})
        self.assertEqual(row["member_count"], 2)
        self.assertTrue(row["is_active"])
        self.assertEqual(row["created_by"], {"id": self.owner.pk, "name": "Frida Lehrend"})
        self.assertIn("created_at", row)

    def test_list_permissions(self):
        for user, status in (
            (self.owner, 200), (self.colleague, 200), (self.admin, 200),
            (self.group_admin, 200), (self.other_lender, 404), (self.borrower, 403),
        ):
            with self.subTest(user=user.username):
                self.as_user(user)
                self.assertEqual(self.client.get(self.url()).status_code, status)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_switch_off_and_on_keeps_members(self):
        self.as_user(self.colleague)
        response = self.client.patch(self.url(self.link), {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        self.assertEqual(response.data["member_count"], 2)
        self.link.refresh_from_db()
        self.assertFalse(self.link.is_active)
        self.assertFalse(self.pool.access_groups.filter(pk=self.link.access_group.pk).exists())
        response = self.client.patch(self.url(self.link), {"is_active": True}, format="json")
        self.assertTrue(response.data["is_active"])
        self.assertTrue(self.pool.access_groups.filter(pk=self.link.access_group.pk).exists())

    def test_patch_needs_boolean_and_ignores_other_fields(self):
        self.as_user(self.owner)
        response = self.client.patch(self.url(self.link), {"title": "X"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            self.url(self.link), {"is_active": True, "title": "X"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.title, "Optik")

    def test_link_of_another_pool_is_404(self):
        self.as_user(self.admin)
        response = self.client.patch(
            self.url(self.other_link), {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.delete(self.url(self.other_link)).status_code, 404)

    def test_write_permissions(self):
        for user, status in ((self.other_lender, 404), (self.borrower, 403)):
            with self.subTest(user=user.username):
                self.as_user(user)
                self.assertEqual(
                    self.client.patch(
                        self.url(self.link), {"is_active": False}, format="json"
                    ).status_code,
                    status,
                )
                self.assertEqual(self.client.delete(self.url(self.link)).status_code, status)
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_active)

    def test_delete_removes_link_and_group(self):
        group_pk = self.link.access_group.pk
        self.as_user(self.owner)
        self.assertEqual(self.client.delete(self.url(self.link)).status_code, 204)
        self.assertFalse(LtiCourseLink.objects.filter(pk=self.link.pk).exists())
        self.assertFalse(AccessGroup.objects.filter(pk=group_pk).exists())


class OwnerPoolUpdateTests(ManageApiTestCase):
    """The owner of a personal pool may edit its settings (allowed subset);
    other lenders may not edit it at all."""

    HOURS = {"mon": [["10:00", "12:00"]]}

    def url(self, pool=None):
        return f"/api/manage/pools/{(pool or self.pool).pk}/"

    def test_owner_edits_allowed_fields(self):
        self.as_user(self.owner)
        response = self.client.patch(
            self.url(),
            {
                "name_de": "Mein Lehrstuhl", "opening_hours": self.HOURS,
                "lead_time_hours": 4, "max_booking_months": 6,
                "default_max_days": 7, "require_booking_note": True,
                "notify_on_defect": False, "email": "chair@example.org",
                "description_de": "<p>Kameras</p>",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.name_de, "Mein Lehrstuhl")
        self.assertEqual(self.pool.opening_hours, self.HOURS)
        self.assertEqual(self.pool.lead_time_hours, 4)
        self.assertTrue(self.pool.require_booking_note)

    def test_owner_cannot_change_admin_fields(self):
        group = AccessGroup.objects.create(name="Physik-Studis")
        self.as_user(self.owner)
        for data in (
            {"is_active": False}, {"pool_id": "OTHER"}, {"accent_color": "#ff0000"},
            {"access_group_ids": [group.pk]},
        ):
            with self.subTest(data=data):
                response = self.client.patch(
                    self.url(), {**data, "lead_time_hours": 9}, format="json"
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["fields"], list(data))
        self.pool.refresh_from_db()
        self.assertTrue(self.pool.is_active)
        self.assertEqual(self.pool.pool_id, "CHAIR")
        self.assertEqual(self.pool.lead_time_hours, 0)
        self.assertFalse(self.pool.access_groups.exists())

    def test_owner_full_form_save_with_unchanged_admin_fields(self):
        self.as_user(self.owner)
        payload = self.client.get(self.url()).data
        data = {
            key: value for key, value in payload.items()
            if key not in ("id", "image", "resource_count", "access_groups", "position",
                           "owner", "is_personal", "is_restricted", "can_edit_settings")
        }
        data.update(access_group_ids=[], opening_hours=self.HOURS)
        response = self.client.put(self.url(), data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.opening_hours, self.HOURS)

    def test_read_only_fields_are_ignored(self):
        self.as_user(self.owner)
        response = self.client.patch(
            self.url(), {"owner": self.borrower.pk, "position": 99}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.owner, self.owner)

    def test_other_lenders_cannot_edit(self):
        self.as_user(self.colleague)  # lender of the pool, not owner
        response = self.client.patch(self.url(), {"lead_time_hours": 5}, format="json")
        self.assertEqual(response.status_code, 403)
        self.as_user(self.other_lender)
        response = self.client.patch(self.url(), {"lead_time_hours": 5}, format="json")
        self.assertEqual(response.status_code, 404)
        self.as_user(self.borrower)
        response = self.client.patch(self.url(), {"lead_time_hours": 5}, format="json")
        self.assertEqual(response.status_code, 403)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.lead_time_hours, 0)

    def test_owner_of_normal_pool_rules_do_not_apply_to_lenders(self):
        # A lender of a pool without owner can't edit it either.
        self.as_user(self.other_lender)
        response = self.client.patch(
            self.url(self.other_pool), {"lead_time_hours": 5}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_create_delete_reorder_or_upload(self):
        self.as_user(self.owner)
        self.assertEqual(self.client.delete(self.url()).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/manage/pools/", {"name": "Neu", "pool_id": "NEU"}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/manage/pools/reorder/", {"order": [self.pool.pk]}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"{self.url()}image/").status_code, 403)
        self.assertEqual(self.client.get(f"{self.url()}lenders/").status_code, 403)

    def test_admin_may_change_everything(self):
        self.as_user(self.group_admin)
        response = self.client.patch(
            self.url(), {"is_active": False, "lead_time_hours": 3}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.pool.refresh_from_db()
        self.assertFalse(self.pool.is_active)

    def test_payload_fields(self):
        self.as_user(self.owner)
        data = self.client.get(self.url()).data
        self.assertEqual(data["owner"], {"id": self.owner.pk, "name": "Frida Lehrend"})
        self.assertTrue(data["is_personal"])
        self.assertTrue(data["is_restricted"])  # no ordinary group, but owned
        self.assertTrue(data["can_edit_settings"])
        self.as_user(self.colleague)
        self.assertFalse(self.client.get(self.url()).data["can_edit_settings"])
        self.as_user(self.admin)
        data = self.client.get(self.url(self.other_pool)).data
        self.assertIsNone(data["owner"])
        self.assertFalse(data["is_personal"])
        self.assertFalse(data["is_restricted"])
        self.assertTrue(data["can_edit_settings"])

    def test_course_group_alone_does_not_restrict(self):
        create_link(platform=make_platform(), context_id="c", pool=self.other_pool)
        self.as_user(self.admin)
        data = self.client.get(self.url(self.other_pool)).data
        self.assertFalse(data["is_restricted"])
        AccessGroup.objects.create(name="Gate").pools.add(self.other_pool)
        data = self.client.get(self.url(self.other_pool)).data
        self.assertTrue(data["is_restricted"])

    def test_public_payloads_mark_personal_pools(self):
        self.as_user(self.owner)
        by_id = {p["id"]: p for p in self.client.get("/api/pools/").data}
        self.assertTrue(by_id[self.pool.pk]["is_personal"])
        self.assertFalse(by_id[self.other_pool.pk]["is_personal"])
        self.assertNotIn("owner", by_id[self.pool.pk])
        detail = self.client.get(f"/api/pools/{self.pool.pk}/").data
        self.assertTrue(detail["is_personal"])
        self.assertNotIn("owner", detail)

    def test_whoami_lists_owned_pools(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/api/whoami/").json()["owned_pool_ids"], [self.pool.pk])
        self.client.force_login(self.colleague)
        self.assertEqual(self.client.get("/api/whoami/").json()["owned_pool_ids"], [])
