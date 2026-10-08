# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for the catalog app."""
import contextlib
import io
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from rest_framework.test import APITestCase, APITransactionTestCase

from accounts.models import PoolMembership
from catalog.inventory import default_qr_code_id
from catalog.pdf_extract import PdfTextError, extract_pdf_text
from .models import (
    Category,
    Page,
    Product,
    ProductType,
    Resource,
    ResourceDefect,
    ResourcePool,
    Section,
    TrashSetting,
    WelcomeSetting,
)

User = get_user_model()


class ResourceModelTests(TestCase):
    def test_resource_string_representation(self):
        product_type = ProductType.objects.create(name="Laptop")
        product = Product.objects.create(product_type=product_type, title="MacBook Pro")
        pool = ResourcePool.objects.create(name="Main Library", pool_id="LIB")
        resource = Resource.objects.create(
            product=product,
            resource_pool=pool,
            inventory_number="LIB-001",
            qr_code_id="QR-001",
        )
        self.assertEqual(str(resource), "LIB-001 (MacBook Pro)")
        self.assertEqual(resource.status, Resource.Status.AVAILABLE)

    def test_new_fields_have_backward_compatible_defaults(self):
        pt = ProductType.objects.create(name="Cam-defaults")
        product = Product.objects.create(product_type=pt, title="GoPro-defaults")
        pool = ResourcePool.objects.create(name="P-def", pool_id="P-def")
        resource = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="P-def-001", qr_code_id="QR-def-001",
        )
        self.assertEqual(product.min_gap, 0)
        self.assertEqual(product.missing_notice_lead, 0)
        self.assertEqual(resource.condition_rating, 5)
        self.assertEqual(resource.condition_note, "")


class CatalogApiTests(APITestCase):
    def setUp(self):
        self.product_type = ProductType.objects.create(
            name="Camera",
            attribute_schema=[
                {"key": "resolution", "label": "Resolution", "type": "short_text",
                 "visible": True, "required": False, "default": ""},
                {"key": "note", "label": "Note", "type": "long_text",
                 "visible": False, "required": False, "default": ""},
            ],
        )
        self.product = Product.objects.create(
            product_type=self.product_type,
            title="Sony Alpha 7",
            attributes={"resolution": "33 MP", "note": "secret"},
        )
        from catalog.models import Category

        self.section = Section.objects.create(title="Recording Technology")
        self.category = Category.objects.create(name="Cameras")
        self.section.categories.add(self.category)
        self.product.categories.add(self.category)
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        Resource.objects.create(
            product=self.product,
            resource_pool=self.pool,
            inventory_number="DigiLab-001",
            qr_code_id="QR-DigiLab-001",
        )

    def _product(self, product_type, title, lending_type="days"):
        """A product with one unit in the open pool, so the shop lists it."""
        product = Product.objects.create(
            product_type=product_type, title=title, lending_type=lending_type
        )
        n = Resource.objects.count() + 1
        Resource.objects.create(
            product=product, resource_pool=self.pool,
            inventory_number=f"DigiLab-X{n}", qr_code_id=f"QR-DigiLab-X{n}",
        )
        return product

    def test_section_list(self):
        response = self.client.get("/api/sections/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["title"], "Recording Technology")
        self.assertEqual(response.data["results"][0]["category_count"], 1)
        self.assertEqual(response.data["results"][0]["product_count"], 1)

    def test_product_type_and_section_filters(self):
        from catalog.models import Category

        other_type = ProductType.objects.create(name="Tripod")
        tripod = self._product(other_type, "Manfrotto")
        other_section = Section.objects.create(title="Accessories")
        tripods = Category.objects.create(name="Tripods")
        other_section.categories.add(tripods)
        tripod.categories.add(tripods)

        by_type = self.client.get("/api/products/", {"product_type": other_type.id})
        self.assertEqual([p["id"] for p in by_type.data["results"]], [tripod.id])
        by_section = self.client.get("/api/products/", {"section": self.section.id})
        self.assertEqual([p["id"] for p in by_section.data["results"]], [self.product.id])
        by_other = self.client.get("/api/products/", {"section": other_section.id})
        self.assertEqual([p["id"] for p in by_other.data["results"]], [tripod.id])
        bad = self.client.get("/api/products/", {"product_type": "abc"})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.data["count"], 0)

    def test_product_detail_exposes_only_visible_attributes_and_pools(self):
        response = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(response.status_code, 200)
        keys = [attr["key"] for attr in response.data["visible_attributes"]]
        self.assertIn("resolution", keys)
        self.assertNotIn("note", keys)  # not visible
        self.assertEqual(response.data["pools"][0]["name"], "DigiLab")

    def test_product_search(self):
        response = self.client.get("/api/products/", {"search": "sony"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)


class ContentTranslationTests(APITestCase):
    """Catalog content is served in the request language with German fallback
    (issue #6 — django-modeltranslation + ActiveLanguageMiddleware)."""

    def setUp(self):
        # `title` is translated both ways; `description` only has German, so it
        # exercises the fallback when the active language has no value.
        self.section = Section.objects.create(
            title_de="Aufnahmetechnik",
            title_en="Recording Technology",
            description_de="Kameras und Zubehör",
        )

    def _section(self, **params):
        results = self.client.get("/api/sections/", params).data["results"]
        return next(s for s in results if s["id"] == self.section.id)

    def test_lang_query_param_selects_translation(self):
        self.assertEqual(self._section(lang="de")["title"], "Aufnahmetechnik")
        self.assertEqual(self._section(lang="en")["title"], "Recording Technology")

    def test_accept_language_header_selects_translation(self):
        results = self.client.get(
            "/api/sections/", HTTP_ACCEPT_LANGUAGE="en"
        ).data["results"]
        section = next(s for s in results if s["id"] == self.section.id)
        self.assertEqual(section["title"], "Recording Technology")

    def test_untranslated_field_falls_back_to_german(self):
        # No English description was entered → fall back to the German value.
        self.assertEqual(self._section(lang="en")["description"], "Kameras und Zubehör")

    def test_unknown_lang_falls_back_without_error(self):
        # An unsupported ?lang is ignored (Accept-Language / default decide).
        response = self.client.get("/api/sections/", {"lang": "fr"})
        self.assertEqual(response.status_code, 200)


class TranslateApiTests(APITestCase):
    """Optional machine-translation pre-fill endpoint (issue #6 Phase 4)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )

    def _post(self):
        return self.client.post(
            "/api/manage/translate/",
            {"text": "Hallo", "source": "de", "target": "en"},
            format="json",
        )

    def test_anonymous_is_forbidden(self):
        self.assertIn(self._post().status_code, (401, 403))

    @override_settings(CONTENT_TRANSLATION_PROVIDER="none", LIBRETRANSLATE_URL="")
    def test_disabled_by_default_returns_503(self):
        self.client.force_login(self.admin)
        self.assertEqual(self._post().status_code, 503)

    @override_settings(
        CONTENT_TRANSLATION_PROVIDER="libretranslate",
        LIBRETRANSLATE_URL="http://libretranslate.local",
    )
    def test_translates_via_provider(self):
        self.client.force_login(self.admin)
        fake = MagicMock()
        fake.read.return_value = b'{"translatedText": "Hello"}'
        fake.__enter__.return_value = fake
        with patch(
            "basicbar_integrations.translation_service.request.urlopen", return_value=fake
        ) as urlopen:
            response = self._post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["translated"], "Hello")
        self.assertTrue(urlopen.called)

    @override_settings(
        CONTENT_TRANSLATION_PROVIDER="libretranslate",
        LIBRETRANSLATE_URL="http://libretranslate.local",
    )
    def test_upstream_failure_returns_502(self):
        self.client.force_login(self.admin)
        with patch(
            "basicbar_integrations.translation_service.request.urlopen",
            side_effect=URLError("boom"),
        ):
            self.assertEqual(self._post().status_code, 502)


class ManageTranslationEditingTests(APITestCase):
    """Admin can edit each language explicitly via the manage API (issue #6,
    Phase 2). The canonical (German) column is kept in sync and required."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)

    def test_create_with_per_language_fields(self):
        resp = self.client.post(
            "/api/manage/sections/",
            {"title_de": "Kameras", "title_en": "Cameras"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        sec = Section.objects.get(id=resp.data["id"])
        self.assertEqual(sec.title_de, "Kameras")
        self.assertEqual(sec.title_en, "Cameras")
        # Each language reads back its own value through the descriptor.
        with translation.override("de"):
            self.assertEqual(sec.title, "Kameras")
        with translation.override("en"):
            self.assertEqual(sec.title, "Cameras")

    def test_legacy_bare_field_still_accepted(self):
        resp = self.client.post(
            "/api/manage/sections/", {"title": "Camcorders"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_english_only_create_rejected(self):
        resp = self.client.post(
            "/api/manage/sections/", {"title_en": "Cameras"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("title_de", resp.data)

    def test_blank_translation_stored_as_null_without_collision(self):
        a = self.client.post(
            "/api/manage/sections/",
            {"title_de": "A", "title_en": ""},
            format="json",
        )
        b = self.client.post(
            "/api/manage/sections/",
            {"title_de": "B", "title_en": ""},
            format="json",
        )
        self.assertEqual((a.status_code, b.status_code), (201, 201), (a.data, b.data))
        self.assertIsNone(Section.objects.get(id=a.data["id"]).title_en)

    def test_update_one_language_leaves_the_other(self):
        sec = Section.objects.create(title_de="Alt", title_en="Old")
        resp = self.client.patch(
            f"/api/manage/sections/{sec.id}/", {"title_en": "New"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        sec.refresh_from_db()
        self.assertEqual(sec.title_en, "New")
        self.assertEqual(sec.title_de, "Alt")

    def test_clearing_canonical_on_update_is_a_clean_400(self):
        # Emptying the required canonical language must be rejected with a
        # validation error, not blow up as an IntegrityError (NOT NULL).
        sec = Section.objects.create(title_de="Alt", title_en="Old")
        resp = self.client.patch(
            f"/api/manage/sections/{sec.id}/", {"title_de": ""}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("title_de", resp.data)
        sec.refresh_from_db()
        self.assertEqual(sec.title_de, "Alt")  # unchanged


class ManagePoolApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(username="alice")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)

    def _payload(self, **overrides):
        data = {
            "name": "Media Lab",
            "pool_id": "MediaLab",
            "address": "Building B\nMain Street 1",
            "room": "B1.01",
            "opening_hours": {"mon": [["09:00", "17:00"]]},
            "closed_weekdays": [5, 6],
            "lead_time_hours": 24,
        }
        data.update(overrides)
        return data

    def test_borrower_and_lender_cannot_manage_pools(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/pools/").status_code, 403)
        self.client.force_login(self.lender)  # lenders manage bookings, not catalog
        self.assertEqual(
            self.client.post("/api/manage/pools/", self._payload(), format="json").status_code,
            403,
        )

    def test_pool_lists_its_access_groups(self):
        from accounts.models import AccessGroup

        group = AccessGroup.objects.create(name="IGB")
        group.pools.add(self.pool)
        self.client.force_login(self.admin)
        detail = self.client.get(f"/api/manage/pools/{self.pool.id}/").data
        self.assertEqual(detail["access_groups"], [{"id": group.id, "name": "IGB"}])
        # A pool with no group reports an empty list (visible to everyone).
        other = ResourcePool.objects.create(name="Open", pool_id="open")
        body = self.client.get(f"/api/manage/pools/{other.id}/").data
        self.assertEqual(body["access_groups"], [])

    def test_admin_crud_flow(self):
        self.client.force_login(self.admin)
        created = self.client.post("/api/manage/pools/", self._payload(), format="json")
        self.assertEqual(created.status_code, 201)
        pool_id = created.data["id"]
        self.assertEqual(created.data["resource_count"], 0)

        listing = self.client.get("/api/manage/pools/")
        self.assertEqual(listing.data["count"], 2)  # DigiLab + Media Lab

        patched = self.client.patch(
            f"/api/manage/pools/{pool_id}/", {"room": "C2.05"}, format="json"
        )
        self.assertEqual(patched.data["room"], "C2.05")

        self.assertEqual(
            self.client.delete(f"/api/manage/pools/{pool_id}/").status_code, 204
        )

    def test_cannot_delete_pool_with_resources(self):
        product_type = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=product_type, title="GoPro")
        Resource.objects.create(
            product=product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-001",
        )
        self.client.force_login(self.admin)
        response = self.client.delete(f"/api/manage/pools/{self.pool.id}/")
        self.assertEqual(response.status_code, 400)

    def test_invalid_opening_hours_rejected(self):
        self.client.force_login(self.admin)
        bad = self._payload(pool_id="Bad", name="Bad", opening_hours={"mon": [["17:00", "09:00"]]})
        response = self.client.post("/api/manage/pools/", bad, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("opening_hours", response.data)

    def test_invalid_closed_weekday_rejected(self):
        self.client.force_login(self.admin)
        bad = self._payload(pool_id="Bad2", name="Bad2", closed_weekdays=[7])
        response = self.client.post("/api/manage/pools/", bad, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("closed_weekdays", response.data)


class PoolLendersApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.alice = User.objects.create_user(
            username="alice", first_name="Alice", last_name="Zed", email="a@x.de"
        )
        self.bob = User.objects.create_user(
            username="bob", first_name="Bob", last_name="Adams", email="b@x.de"
        )
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        self.other = ResourcePool.objects.create(name="Other", pool_id="Other")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        self.url = f"/api/manage/pools/{self.pool.id}/lenders/"

    def test_admin_get_lists_lenders_ordered(self):
        PoolMembership.objects.create(user=self.alice, resource_pool=self.pool)
        PoolMembership.objects.create(user=self.bob, resource_pool=self.pool)
        PoolMembership.objects.create(user=self.alice, resource_pool=self.other)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [u["username"] for u in response.data], ["len", "bob", "alice"]
        )
        self.assertEqual(
            set(response.data[2]),
            {"id", "username", "first_name", "last_name", "email"},
        )

    def test_lender_of_pool_forbidden(self):
        self.client.force_login(self.lender)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.put(self.url, {"user_ids": []}, format="json").status_code,
            403,
        )

    def test_anonymous_denied(self):
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
        self.assertIn(
            self.client.put(self.url, {"user_ids": []}, format="json").status_code,
            (401, 403),
        )

    def test_put_adds_and_removes_leaving_others_untouched(self):
        PoolMembership.objects.create(user=self.alice, resource_pool=self.other)
        self.client.force_login(self.admin)
        response = self.client.put(
            self.url, {"user_ids": [self.alice.id, self.bob.id]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {u["id"] for u in response.data}, {self.alice.id, self.bob.id}
        )
        self.assertEqual(
            set(
                PoolMembership.objects.filter(resource_pool=self.pool).values_list(
                    "user_id", flat=True
                )
            ),
            {self.alice.id, self.bob.id},
        )
        self.assertTrue(
            PoolMembership.objects.filter(
                user=self.alice, resource_pool=self.other
            ).exists()
        )

    def test_put_empty_removes_all(self):
        self.client.force_login(self.admin)
        response = self.client.put(self.url, {"user_ids": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_put_duplicates_collapse(self):
        self.client.force_login(self.admin)
        response = self.client.put(
            self.url, {"user_ids": [self.bob.id, self.bob.id]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([u["id"] for u in response.data], [self.bob.id])

    def test_unknown_id_rejected_without_changes(self):
        self.client.force_login(self.admin)
        response = self.client.put(
            self.url, {"user_ids": [self.bob.id, 999999]}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("999999", response.data["detail"])
        self.assertEqual(
            PoolMembership.objects.filter(resource_pool=self.pool).count(), 1
        )

    def test_inactive_user_rejected(self):
        self.bob.is_active = False
        self.bob.save()
        self.client.force_login(self.admin)
        response = self.client.put(self.url, {"user_ids": [self.bob.id]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn(str(self.bob.id), response.data["detail"])

    def test_existing_inactive_lender_kept_while_adding_another(self):
        self.lender.is_active = False
        self.lender.save()
        self.client.force_login(self.admin)
        response = self.client.put(
            self.url, {"user_ids": [self.lender.id, self.bob.id]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {u["id"] for u in response.data}, {self.lender.id, self.bob.id}
        )

    def test_admin_account_can_be_added(self):
        self.client.force_login(self.admin)
        response = self.client.put(
            self.url, {"user_ids": [self.admin.id]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([u["id"] for u in response.data], [self.admin.id])

    def test_huge_id_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.put(self.url, {"user_ids": [2**40]}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_body_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.put(self.url, {"user_ids": "x"}, format="json")
        self.assertEqual(response.status_code, 400)


class PoolFieldsTests(APITestCase):
    """position (shop ordering, #6) and accent_color (#16) on ResourcePool."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )

    def test_shop_pools_ordered_by_position(self):
        a = ResourcePool.objects.create(name="A", pool_id="A", position=2, is_active=True)
        b = ResourcePool.objects.create(name="B", pool_id="B", position=1, is_active=True)
        # Both are "open" pools (no access group) — visible to everyone.
        names = [p["name"] for p in self.client.get("/api/pools/").json()]
        self.assertLess(names.index("B"), names.index("A"))  # position 1 before 2

    def test_resourcepool_email_language_defaults_to_de(self):
        pool = ResourcePool.objects.create(name="X", pool_id="x")
        self.assertEqual(pool.email_language, "de")

    def test_accent_color_round_trips_via_manage(self):
        self.client.force_login(self.admin)
        pool = ResourcePool.objects.create(name="C", pool_id="C")
        resp = self.client.patch(
            f"/api/manage/pools/{pool.id}/", {"accent_color": "sky"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        pool.refresh_from_db()
        self.assertEqual(pool.accent_color, "sky")

    def test_pool_reorder(self):
        self.client.force_login(self.admin)
        p1 = ResourcePool.objects.create(name="P1", pool_id="P1", position=0)
        p2 = ResourcePool.objects.create(name="P2", pool_id="P2", position=1)
        resp = self.client.post(
            "/api/manage/pools/reorder/", {"order": [p2.id, p1.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        p1.refresh_from_db(); p2.refresh_from_db()
        self.assertEqual((p2.position, p1.position), (0, 1))


class ManageProductTypeApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")

    def _payload(self, **overrides):
        data = {
            "name": "Camera",
            "description": "",
            "attribute_schema": [
                {"key": "resolution", "label": "Resolution", "type": "short_text",
                 "visible": True, "required": True, "default": ""},
            ],
        }
        data.update(overrides)
        return data

    def test_borrower_cannot_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/product-types/").status_code, 403)

    def _role_statuses(self, user):
        """Status codes of every product-type endpoint for ``user``."""
        pt = ProductType.objects.create(name="Tripod")
        base = "/api/manage/product-types/"
        self.client.force_login(user)
        statuses = {
            "list": self.client.get(base).status_code,
            "retrieve": self.client.get(f"{base}{pt.id}/").status_code,
            "create": self.client.post(base, self._payload(), format="json").status_code,
            "update": self.client.patch(
                f"{base}{pt.id}/", {"description": "x"}, format="json"
            ).status_code,
            "attribute_usage": self.client.get(
                f"{base}{pt.id}/attribute-usage/"
            ).status_code,
            "destroy": self.client.delete(f"{base}{pt.id}/").status_code,
        }
        self.client.logout()
        return statuses

    def test_lender_can_read_but_not_write(self):
        """Lenders need the type list for the product form's type select (#20)."""
        lender = User.objects.create_user(username="lena")
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DL")
        PoolMembership.objects.create(user=lender, resource_pool=pool)
        statuses = self._role_statuses(lender)
        self.assertEqual((statuses.pop("list"), statuses.pop("retrieve")), (200, 200))
        self.assertEqual(set(statuses.values()), {403}, statuses)
        self.client.force_login(lender)
        suggest = self.client.post(
            "/api/manage/product-types/suggest-attributes/", {"name": "x"}, format="json"
        )
        self.assertEqual(suggest.status_code, 403)

    def test_borrower_gets_403_everywhere(self):
        statuses = self._role_statuses(self.borrower)
        self.assertEqual(set(statuses.values()), {403}, statuses)

    def test_admin_can_do_everything(self):
        statuses = self._role_statuses(self.admin)
        self.assertEqual(
            statuses,
            {
                "list": 200, "retrieve": 200, "create": 201, "update": 200,
                "attribute_usage": 200, "destroy": 204,
            },
        )

    def test_duplicate_name_has_clear_message(self):
        self.client.force_login(self.admin)
        self.client.post("/api/manage/product-types/", self._payload(), format="json")
        dup = self.client.post(
            "/api/manage/product-types/", self._payload(), format="json"
        )
        self.assertEqual(dup.status_code, 400)
        flat = str(dup.data)
        # Clear, translatable message — not the internal "name de" column.
        self.assertIn("An entry with this name already exists.", flat)
        self.assertNotIn("name de", flat)

    def test_admin_crud_flow(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/product-types/", self._payload(), format="json"
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["product_count"], 0)
        self.assertEqual(created.data["attribute_schema"][0]["key"], "resolution")
        pt_id = created.data["id"]

        patched = self.client.patch(
            f"/api/manage/product-types/{pt_id}/",
            {"description": "DSLRs and mirrorless"},
            format="json",
        )
        self.assertEqual(patched.data["description"], "DSLRs and mirrorless")
        self.assertEqual(
            self.client.delete(f"/api/manage/product-types/{pt_id}/").status_code, 204
        )

    def test_cannot_delete_type_with_products(self):
        pt = ProductType.objects.create(name="Laptop")
        Product.objects.create(product_type=pt, title="MacBook")
        self.client.force_login(self.admin)
        response = self.client.delete(f"/api/manage/product-types/{pt.id}/")
        self.assertEqual(response.status_code, 400)

    def test_invalid_attribute_type_rejected(self):
        self.client.force_login(self.admin)
        bad = self._payload(attribute_schema=[
            {"key": "x", "label": "X", "type": "bogus"},
        ])
        response = self.client.post("/api/manage/product-types/", bad, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("attribute_schema", response.data)

    def test_duplicate_attribute_key_rejected(self):
        self.client.force_login(self.admin)
        bad = self._payload(attribute_schema=[
            {"key": "a", "label": "A", "type": "number"},
            {"key": "a", "label": "A2", "type": "number"},
        ])
        response = self.client.post("/api/manage/product-types/", bad, format="json")
        self.assertEqual(response.status_code, 400)

    def test_schema_is_normalised(self):
        self.client.force_login(self.admin)
        # Missing visible/required/default get sensible defaults; a string label
        # is normalised to a per-language dict (issue #6 Phase 3).
        payload = self._payload(
            attribute_schema=[{"key": "weight", "type": "number", "label": "Weight"}]
        )
        created = self.client.post(
            "/api/manage/product-types/", payload, format="json"
        )
        attr = created.data["attribute_schema"][0]
        self.assertEqual(attr["label"], {"de": "Weight", "en": ""})
        self.assertTrue(attr["visible"])
        self.assertFalse(attr["required"])

    def test_attribute_label_is_translatable(self):
        self.client.force_login(self.admin)
        # A per-language label round-trips and the borrower view resolves it to
        # the request language, falling back to the canonical value.
        pt = self.client.post(
            "/api/manage/product-types/",
            self._payload(
                attribute_schema=[
                    {
                        "key": "maker",
                        "type": "short_text",
                        "label": {"de": "Hersteller", "en": "Manufacturer"},
                        "visible": True,
                    }
                ]
            ),
            format="json",
        )
        self.assertEqual(pt.status_code, 201, pt.data)
        self.assertEqual(
            pt.data["attribute_schema"][0]["label"],
            {"de": "Hersteller", "en": "Manufacturer"},
        )
        product = Product.objects.create(
            product_type=ProductType.objects.get(id=pt.data["id"]),
            title_de="Kamera",
        )
        pool = ResourcePool.objects.create(name="Lab", pool_id="Lab")
        Resource.objects.create(
            product=product,
            resource_pool=pool,
            inventory_number="Lab-001",
            qr_code_id="QR-Lab-001",
        )
        en = self.client.get(f"/api/products/{product.id}/?lang=en")
        self.assertEqual(en.data["visible_attributes"][0]["label"], "Manufacturer")
        de = self.client.get(f"/api/products/{product.id}/?lang=de")
        self.assertEqual(de.data["visible_attributes"][0]["label"], "Hersteller")


_AI_ON = dict(
    AI_PROVIDER="litellm", AI_BASE_URL="https://x/v1", AI_API_KEY="k", AI_MODEL="qwen-3.5"
)


class SuggestAttributesTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="suggadmin", is_staff=True, is_superuser=True
        )
        self.url = "/api/manage/product-types/suggest-attributes/"

    @override_settings(AI_PROVIDER="none")
    def test_503_when_disabled(self):
        self.client.force_login(self.admin)
        res = self.client.post(self.url, {"description": "Camera"}, format="json")
        self.assertEqual(res.status_code, 503)

    @override_settings(**_AI_ON)
    def test_400_when_description_missing(self):
        self.client.force_login(self.admin)
        res = self.client.post(self.url, {"description": "  "}, format="json")
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_400_when_description_too_long(self):
        self.client.force_login(self.admin)
        res = self.client.post(self.url, {"description": "x" * 2001}, format="json")
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_normalises_dedups_and_caps(self):
        self.client.force_login(self.admin)
        raw = {"attributes": (
            [{"key": "resolution", "label": {"de": "Auflösung", "en": "Resolution"},
              "type": "short_text"}]
            + [{"key": "bogus", "type": "nope"}]          # invalid type -> dropped
            + [{"key": "hersteller", "type": "short_text"}]  # duplicate of existing
            + [{"key": f"a{i}", "type": "number"} for i in range(15)]  # push over 12
        )}
        with patch("catalog.views.ai.chat_json", return_value=raw):
            res = self.client.post(
                self.url,
                {"description": "Camera", "existing_keys": ["hersteller"]},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        keys = [a["key"] for a in res.json()["attributes"]]
        self.assertNotIn("bogus", keys)          # invalid dropped
        self.assertNotIn("hersteller", keys)     # existing deduped
        self.assertLessEqual(len(keys), 12)      # capped
        self.assertEqual(res.json()["attributes"][0]["label"], {"de": "Auflösung", "en": "Resolution"})

    @override_settings(**_AI_ON)
    def test_generates_from_name_and_hints(self):
        self.client.force_login(self.admin)
        raw = {"attributes": [{"key": "resolution", "type": "short_text"}]}
        with patch("catalog.views.ai.chat_json", return_value=raw) as chat:
            res = self.client.post(
                self.url,
                {"name": "Videokamera", "hints": "mit Zubehör"},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        self.assertIn("resolution", [a["key"] for a in res.json()["attributes"]])
        _system, user = chat.call_args.args
        self.assertIn("Videokamera", user)
        self.assertIn("mit Zubehör", user)

    @override_settings(**_AI_ON)
    def test_502_on_ai_error(self):
        from basicbar_integrations.ai import AIError
        self.client.force_login(self.admin)
        with patch("catalog.views.ai.chat_json", side_effect=AIError("boom")):
            res = self.client.post(self.url, {"description": "Camera"}, format="json")
        self.assertEqual(res.status_code, 502)

    @override_settings(**_AI_ON)
    def test_null_attributes_returns_empty_list(self):
        self.client.force_login(self.admin)
        with patch("catalog.views.ai.chat_json", return_value={"attributes": None}):
            res = self.client.post(self.url, {"description": "Camera"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["attributes"], [])

    @override_settings(**_AI_ON)
    def test_non_list_attributes_returns_empty_list(self):
        self.client.force_login(self.admin)
        with patch("catalog.views.ai.chat_json", return_value={"attributes": "oops"}):
            res = self.client.post(self.url, {"description": "Camera"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["attributes"], [])

    @override_settings(**_AI_ON)
    def test_non_list_existing_keys_does_not_crash(self):
        self.client.force_login(self.admin)
        raw = {"attributes": [{"key": "resolution", "type": "short_text"}]}
        with patch("catalog.views.ai.chat_json", return_value=raw):
            res = self.client.post(
                self.url,
                {"description": "Camera", "existing_keys": 123},
                format="json",
            )
        self.assertEqual(res.status_code, 200)
        keys = [a["key"] for a in res.json()["attributes"]]
        self.assertIn("resolution", keys)

    @override_settings(**_AI_ON)
    def test_reserved_builtin_keys_are_dropped(self):
        self.client.force_login(self.admin)
        raw = {"attributes": [
            {"key": "inventory_number", "type": "short_text"},  # built-in unit field
            {"key": "serial_number", "type": "short_text"},     # built-in unit field
            {"key": "resolution", "type": "short_text"},        # a real attribute
        ]}
        with patch("catalog.views.ai.chat_json", return_value=raw):
            res = self.client.post(self.url, {"description": "Camera"}, format="json")
        self.assertEqual(res.status_code, 200)
        keys = [a["key"] for a in res.json()["attributes"]]
        self.assertNotIn("inventory_number", keys)
        self.assertNotIn("serial_number", keys)
        self.assertIn("resolution", keys)


class ManageProductApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.product_type = ProductType.objects.create(
            name="Camera",
            attribute_schema=[
                {"key": "resolution", "label": "Resolution", "type": "short_text",
                 "visible": True, "required": True, "default": ""},
                {"key": "sensor", "label": "Sensor", "type": "short_text",
                 "visible": True, "required": False, "default": "APS-C"},
            ],
        )

    def _payload(self, **overrides):
        data = {
            "title": "Sony Alpha 7",
            "product_type": self.product_type.id,
            "lending_type": "days",
            "attributes": {"resolution": "33 MP"},
        }
        data.update(overrides)
        return data

    def test_borrower_cannot_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/products/").status_code, 403)

    @override_settings(MAX_PRODUCTS=1)
    def test_product_cap_blocks_creation(self):
        self.client.force_login(self.admin)
        first = self.client.post(
            "/api/manage/products/", self._payload(title="P1"), format="json"
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/api/manage/products/", self._payload(title="P2"), format="json"
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Product.objects.count(), 1)

    def test_admin_create_fills_defaults_and_drops_unknown(self):
        self.client.force_login(self.admin)
        payload = self._payload(
            attributes={"resolution": "33 MP", "bogus": "x"}  # unknown key dropped
        )
        response = self.client.post("/api/manage/products/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        attrs = response.data["attributes"]
        # short_text values are stored per language (issue #6); a plain string
        # maps to the canonical (German) language.
        self.assertEqual(attrs["resolution"], {"de": "33 MP", "en": ""})
        self.assertEqual(attrs["sensor"], {"de": "APS-C", "en": ""})  # default filled
        self.assertNotIn("bogus", attrs)
        self.assertEqual(response.data["product_type_name"], "Camera")

    def test_required_attribute_enforced(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/manage/products/", self._payload(attributes={}), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("attributes", response.data)

    def test_changing_type_keeps_matching_attribute_values(self):
        # Changing a product's type preserves values whose key exists in the new
        # type's schema, and drops the rest (UI warns before this).
        self.client.force_login(self.admin)
        product = Product.objects.create(
            product_type=self.product_type,
            title="A7",
            attributes={"resolution": "33 MP", "sensor": "full-frame"},
        )
        other = ProductType.objects.create(
            name="Scanner",
            attribute_schema=[
                {"key": "resolution", "label": "DPI", "type": "short_text",
                 "visible": True, "required": False, "default": ""},
            ],
        )
        response = self.client.patch(
            f"/api/manage/products/{product.id}/",
            {"product_type": other.id, "attributes": {"resolution": "33 MP", "sensor": "full-frame"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        attrs = response.data["attributes"]
        # short_text values are stored per language (issue #6).
        self.assertEqual(attrs["resolution"], {"de": "33 MP", "en": ""})  # matching key kept
        self.assertNotIn("sensor", attrs)  # not in new schema → dropped

    def test_update_and_delete(self):
        product = Product.objects.create(
            product_type=self.product_type, title="A7", attributes={"resolution": "33 MP"}
        )
        self.client.force_login(self.admin)
        patched = self.client.patch(
            f"/api/manage/products/{product.id}/", {"title": "A7 IV"}, format="json"
        )
        self.assertEqual(patched.data["title"], "A7 IV")
        self.assertEqual(
            self.client.delete(f"/api/manage/products/{product.id}/").status_code, 204
        )

    def test_return_info_round_trips(self):
        product = Product.objects.create(
            product_type=self.product_type, title="A7", attributes={"resolution": "33 MP"}
        )
        self.client.force_login(self.admin)
        patched = self.client.patch(
            f"/api/manage/products/{product.id}/",
            {"return_info": "Check the lens cap and count 3 batteries."},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(
            patched.data["return_info"], "Check the lens cap and count 3 batteries."
        )
        product.refresh_from_db()
        self.assertEqual(
            product.return_info, "Check the lens cap and count 3 batteries."
        )

    def test_short_description_round_trips_and_shows_on_borrower_detail(self):
        product = Product.objects.create(
            product_type=self.product_type, title="A7", attributes={"resolution": "33 MP"}
        )
        self.client.force_login(self.admin)
        patched = self.client.patch(
            f"/api/manage/products/{product.id}/",
            {
                "short_description_de": "Kompakte Systemkamera",
                "short_description_en": "Compact mirrorless camera",
            },
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data["short_description_de"], "Kompakte Systemkamera")
        self.assertEqual(patched.data["short_description_en"], "Compact mirrorless camera")
        product.refresh_from_db()
        self.assertEqual(product.short_description_de, "Kompakte Systemkamera")
        self.assertEqual(product.short_description_en, "Compact mirrorless camera")

        # A bookable resource makes the product visible in the shop.
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="DigiLab-001", qr_code_id="QR-DigiLab-001",
        )

        # Appears on the borrower-facing product detail, language-aware.
        en = self.client.get(f"/api/products/{product.id}/?lang=en")
        self.assertEqual(en.data["short_description"], "Compact mirrorless camera")
        de = self.client.get(f"/api/products/{product.id}/?lang=de")
        self.assertEqual(de.data["short_description"], "Kompakte Systemkamera")

    def test_cannot_delete_product_with_resources(self):
        product = Product.objects.create(
            product_type=self.product_type, title="A7", attributes={"resolution": "33 MP"}
        )
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="DigiLab-001", qr_code_id="QR-001",
        )
        self.client.force_login(self.admin)
        response = self.client.delete(f"/api/manage/products/{product.id}/")
        self.assertEqual(response.status_code, 400)


class BilingualAttributeValueTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "biling", "b@x.de", "pw", is_staff=True, is_superuser=True,
        )
        self.pt = ProductType.objects.create(
            name="Camera",
            attribute_schema=[
                {"key": "material", "label": {"de": "Material", "en": "Material"},
                 "type": "short_text", "default": "", "visible": True, "required": True},
                {"key": "weight", "label": {"de": "Gewicht", "en": "Weight"},
                 "type": "number", "default": "", "visible": True, "required": False},
            ],
        )

    def _create(self, attributes):
        self.client.force_login(self.admin)
        return self.client.post(
            "/api/manage/products/",
            {"title_de": "Cam", "title_en": "Cam", "product_type": self.pt.id,
             "lending_type": "days", "attributes": attributes},
            format="json",
        )

    def test_text_dict_value_is_stored_per_language(self):
        res = self._create({"material": {"de": "Aluminium", "en": "Aluminum"}, "weight": 680})
        self.assertEqual(res.status_code, 201, res.data)
        p = Product.objects.get(pk=res.data["id"])
        self.assertEqual(p.attributes["material"], {"de": "Aluminium", "en": "Aluminum"})
        self.assertEqual(p.attributes["weight"], 680)   # number unchanged

    def test_plain_string_text_value_is_wrapped_to_canonical(self):
        res = self._create({"material": "Aluminium", "weight": 680})
        self.assertEqual(res.status_code, 201, res.data)
        p = Product.objects.get(pk=res.data["id"])
        self.assertEqual(p.attributes["material"], {"de": "Aluminium", "en": ""})

    def test_required_text_needs_canonical_language(self):
        res = self._create({"material": {"de": "", "en": "only english"}, "weight": 680})
        self.assertEqual(res.status_code, 400)
        self.assertIn("attributes", res.data)

    def test_visible_attributes_resolve_active_language(self):
        res = self._create({"material": {"de": "Aluminium", "en": "Aluminum"}})
        p = Product.objects.get(pk=res.data["id"])
        from catalog.serializers import ProductDetailSerializer
        with translation.override("en"):
            data = ProductDetailSerializer(p, context={"request": None}).data
        mat = next(a for a in data["visible_attributes"] if a["key"] == "material")
        self.assertEqual(mat["value"], "Aluminum")

    def test_visible_attributes_tolerate_legacy_single_value(self):
        # A product saved before the migration may still hold a plain string.
        p = Product.objects.create(
            title="Old", product_type=self.pt, lending_type="days",
            attributes={"material": "Altwert", "weight": 680},
        )
        from catalog.serializers import ProductDetailSerializer
        with translation.override("de"):
            data = ProductDetailSerializer(p, context={"request": None}).data
        mat = next(a for a in data["visible_attributes"] if a["key"] == "material")
        self.assertEqual(mat["value"], "Altwert")


class ManageProductTypeStructureApiTests(APITestCase):
    """Product types are pure attribute templates again (#78, ADR-0011): no
    image, position, product order or sections."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender_pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        self.lender = User.objects.create_user(username="lena")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.lender_pool)

    def test_lender_can_read_but_not_manage_types(self):
        # Lenders read types for the product form; writes stay admin-only.
        self.client.force_login(self.lender)
        self.assertEqual(self.client.get("/api/manage/product-types/").status_code, 200)
        created = self.client.post(
            "/api/manage/product-types/", {"name": "Camera"}, format="json"
        )
        self.assertEqual(created.status_code, 403)

    def test_navigation_fields_are_gone(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/product-types/",
            {"name": "Camera", "position": 99, "sections": [], "product_order": []},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        for key in ("image", "position", "sections", "products", "product_order"):
            self.assertNotIn(key, created.data)
        self.assertEqual(created.data["product_count"], 0)

    def test_list_is_ordered_by_name(self):
        ProductType.objects.create(name="Charlie")
        ProductType.objects.create(name="Alpha")
        self.client.force_login(self.admin)
        listed = self.client.get("/api/manage/product-types/").json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertEqual([r["name"] for r in rows], ["Alpha", "Charlie"])

    def test_reorder_and_image_endpoints_are_gone(self):
        pt = ProductType.objects.create(name="Camera")
        self.client.force_login(self.admin)
        # ``reorder/`` now falls through to the detail route (no POST there).
        self.assertIn(
            self.client.post(
                "/api/manage/product-types/reorder/", {"order": [pt.id]}, format="json"
            ).status_code,
            (404, 405),
        )
        image_url = f"/api/manage/product-types/{pt.id}/image/"
        self.assertEqual(self.client.post(image_url).status_code, 404)
        self.assertEqual(self.client.delete(image_url).status_code, 404)

    def test_delete_soft_deletes_but_blocks_when_products_exist(self):
        used = ProductType.objects.create(name="Used")
        Product.objects.create(product_type=used, title="P")
        unused = ProductType.objects.create(name="Unused")
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.delete(f"/api/manage/product-types/{used.id}/").status_code, 400
        )
        self.assertEqual(
            self.client.delete(f"/api/manage/product-types/{unused.id}/").status_code, 204
        )
        self.assertFalse(ProductType.objects.filter(pk=unused.pk).exists())
        self.assertTrue(ProductType.all_objects.get(pk=unused.pk).is_trashed)


class ManageSectionApiTests(APITestCase):
    def setUp(self):
        from catalog.models import Category

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.c1 = Category.objects.create(name="Video Cameras")
        self.c2 = Category.objects.create(name="Action Cameras")

    def test_borrower_cannot_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/sections/").status_code, 403)

    def test_admin_crud_with_category_assignment(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/sections/",
            {"title": "Recording Technology", "categories": [self.c1.id, self.c2.id]},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["category_count"], 2)
        self.assertNotIn("product_types", created.data)
        self.assertNotIn("product_type_count", created.data)
        section_id = created.data["id"]

        patched = self.client.patch(
            f"/api/manage/sections/{section_id}/",
            {"categories": [self.c1.id]},
            format="json",
        )
        self.assertEqual(patched.data["category_count"], 1)
        self.assertEqual(patched.data["categories"], [self.c1.id])

        self.assertEqual(
            self.client.delete(f"/api/manage/sections/{section_id}/").status_code, 204
        )

    def test_set_order_is_saved_and_returned(self):
        from catalog.models import ProductSet

        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        s1 = ProductSet.objects.create(name="Kit A", resource_pool=pool)
        s2 = ProductSet.objects.create(name="Kit B", resource_pool=pool)
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/sections/",
            {"title": "Ordered", "sets": [s2.id, s1.id]},
            format="json",
        )
        section_id = created.data["id"]
        self.assertEqual(created.data["sets"], [s2.id, s1.id])
        section = Section.objects.get(id=section_id)
        self.assertEqual(section.set_order, [s2.id, s1.id])
        self.client.patch(
            f"/api/manage/sections/{section_id}/",
            {"sets": [s1.id, s2.id]},
            format="json",
        )
        section.refresh_from_db()
        self.assertEqual(section.set_order, [s1.id, s2.id])


class ManageInventoryApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="A7")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")

    def _payload(self, **overrides):
        data = {
            "product": self.product.id,
            "resource_pool": self.pool.id,
            "inventory_number": "DigiLab-001",
            "qr_code_id": "QR-001",
            "status": "available",
        }
        data.update(overrides)
        return data

    def _create(self, **extra):
        self.client.force_login(self.admin)
        data = {"product": self.product.id, "resource_pool": self.pool.id,
                "inventory_number": "DigiLab-010", "status": "available", **extra}
        return self.client.post("/api/manage/inventory/", data, format="json")

    def test_create_without_qr_code_id_derives_it(self):
        res = self._create()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["qr_code_id"], "QR-DigiLab-010")

    def test_create_blank_qr_code_id_derives_it(self):
        res = self._create(qr_code_id="  ")
        self.assertEqual(res.data["qr_code_id"], "QR-DigiLab-010")

    def test_derived_qr_code_id_avoids_clash(self):
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="Other-1", qr_code_id="QR-DigiLab-010",
        )
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="Other-2", qr_code_id="QR-DigiLab-010-2",
        )
        res = self._create()
        self.assertEqual(res.data["qr_code_id"], "QR-DigiLab-010-3")

    def test_derived_qr_code_id_avoids_trashed_resource(self):
        # A trashed unit keeps its (DB-unique) qr_code_id, so the derivation
        # must not hand it out again.
        trashed = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="Other-1", qr_code_id="QR-DigiLab-010",
        )
        trashed.soft_delete()
        res = self._create()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["qr_code_id"], "QR-DigiLab-010-2")

    def test_derived_qr_code_id_makes_inventory_number_url_safe(self):
        res = self._create(inventory_number="Kamera 01")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["qr_code_id"], "QR-Kamera-01")
        res = self._create(inventory_number="IT/123#5?x")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["qr_code_id"], "QR-IT-123-5-x")

    def test_derived_qr_code_id_for_max_length_inventory_number(self):
        res = self._create(inventory_number="A" * 255)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertLessEqual(len(res.data["qr_code_id"]), 255)
        # A clash suffix must still fit the 255-character column.
        second = default_qr_code_id("A" * 255)
        self.assertNotEqual(second, res.data["qr_code_id"])
        self.assertLessEqual(len(second), 255)

    def test_derived_qr_code_id_for_garbage_inventory_number(self):
        for number in ("///", "  ", "#?#"):
            qr = default_qr_code_id(number)
            self.assertRegex(qr, r"^QR-[A-Za-z0-9._~-]+$")

    def test_derived_qr_code_id_ignores_longer_prefix_match(self):
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="Other-1", qr_code_id="QR-DigiLab-0100",
        )
        res = self._create()
        self.assertEqual(res.data["qr_code_id"], "QR-DigiLab-010")

    def test_explicit_qr_code_id_kept(self):
        res = self._create(qr_code_id="LEGACY-42")
        self.assertEqual(res.data["qr_code_id"], "LEGACY-42")

    def test_update_with_blank_qr_code_id_keeps_stored(self):
        res = self._create(qr_code_id="LABEL-7")
        rid = res.data["id"]
        upd = self.client.patch(f"/api/manage/inventory/{rid}/", {"qr_code_id": ""}, format="json")
        self.assertEqual(upd.status_code, 200, upd.data)
        self.assertEqual(Resource.objects.get(pk=rid).qr_code_id, "LABEL-7")

    def test_borrower_cannot_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/inventory/").status_code, 403)

    @override_settings(MAX_RESOURCES=1)
    def test_resource_cap_blocks_creation(self):
        self.client.force_login(self.admin)
        first = self.client.post(
            "/api/manage/inventory/", self._payload(), format="json"
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/api/manage/inventory/",
            self._payload(inventory_number="DigiLab-002", qr_code_id="QR-002"),
            format="json",
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Resource.objects.count(), 1)

    def test_admin_crud_flow(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/inventory/", self._payload(), format="json"
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["product_title"], "A7")
        self.assertEqual(created.data["pool_name"], "DigiLab")
        rid = created.data["id"]

        patched = self.client.patch(
            f"/api/manage/inventory/{rid}/", {"status": "blocked"}, format="json"
        )
        self.assertEqual(patched.data["status"], "blocked")
        self.assertEqual(
            self.client.delete(f"/api/manage/inventory/{rid}/").status_code, 204
        )

    def test_duplicate_inventory_number_rejected(self):
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-x",
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/manage/inventory/", self._payload(qr_code_id="QR-002"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inventory_number", response.data)

    def test_filter_by_pool_and_status(self):
        other_pool = ResourcePool.objects.create(name="Studio", pool_id="Studio")
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-1", status="available",
        )
        Resource.objects.create(
            product=self.product, resource_pool=other_pool,
            inventory_number="Studio-001", qr_code_id="QR-2", status="defective",
        )
        self.client.force_login(self.admin)
        by_pool = self.client.get(f"/api/manage/inventory/?pool={self.pool.id}")
        self.assertEqual(by_pool.data["count"], 1)
        by_status = self.client.get("/api/manage/inventory/?status=defective")
        self.assertEqual(by_status.data["count"], 1)

    def test_suggest_number_fills_lowest_gap(self):
        self.client.force_login(self.admin)
        # No resources yet -> first suggestion is 001.
        first = self.client.get(f"/api/manage/inventory/suggest-number/?pool={self.pool.id}")
        self.assertEqual(first.data["inventory_number"], "DigiLab-001")
        self.assertEqual(first.data["qr_code_id"], "QR-DigiLab-001")

        # Occupy 001 and 003; the next suggestion should reuse the gap at 002.
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-DigiLab-001",
        )
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-003", qr_code_id="QR-DigiLab-003",
        )
        gap = self.client.get(f"/api/manage/inventory/suggest-number/?pool={self.pool.id}")
        self.assertEqual(gap.data["inventory_number"], "DigiLab-002")

    def test_suggest_number_requires_pool(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get("/api/manage/inventory/suggest-number/").status_code, 400
        )

    def test_defect_history_recorded_and_resolved(self):
        resource = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-1",
        )
        # Marking defective opens a defect record carrying the note.
        resource.status = "defective"
        resource.defect_note = "Lens cracked"
        resource.save()
        self.assertEqual(resource.defects.count(), 1)
        defect = resource.defects.first()
        self.assertEqual(defect.note, "Lens cracked")
        self.assertIsNone(defect.resolved_at)

        # Back to available resolves the open record (no duplicate created).
        resource.status = "available"
        resource.defect_note = ""
        resource.save()
        self.assertEqual(resource.defects.count(), 1)
        defect.refresh_from_db()
        self.assertIsNotNone(defect.resolved_at)

    def test_detail_endpoint_includes_defect_and_lending_history(self):
        from lending.services import create_reservation
        from django.utils import timezone
        from datetime import timedelta

        resource = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-1",
        )
        start = timezone.now() + timedelta(days=1)
        create_reservation(self.borrower, [(resource, start, start + timedelta(days=1))])
        resource.status = "defective"
        resource.defect_note = "Won't power on"
        resource.save()

        self.client.force_login(self.admin)
        response = self.client.get(f"/api/manage/inventory/{resource.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["defects"]), 1)
        self.assertEqual(response.data["defects"][0]["note"], "Won't power on")
        self.assertEqual(len(response.data["bookings"]), 1)
        self.assertEqual(response.data["bookings"][0]["borrower"], "alice")

    def test_cannot_delete_resource_with_bookings(self):
        from lending.services import create_reservation
        from django.utils import timezone
        from datetime import timedelta

        resource = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-1",
        )
        start = timezone.now() + timedelta(days=1)
        create_reservation(self.borrower, [(resource, start, start + timedelta(days=1))])
        self.client.force_login(self.admin)
        response = self.client.delete(f"/api/manage/inventory/{resource.id}/")
        self.assertEqual(response.status_code, 400)

    def test_backfill_open_defects_for_legacy_data(self):
        from catalog.defects import backfill_open_defects

        resource = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-1",
        )
        # Simulate a defect marked before history existed: .update() bypasses
        # the signal, so no ResourceDefect record is created.
        Resource.objects.filter(pk=resource.id).update(
            status="defective", defect_note="Legacy fault"
        )
        self.assertEqual(resource.defects.count(), 0)

        self.assertEqual(backfill_open_defects(), 1)
        defect = resource.defects.get()
        self.assertEqual(defect.note, "Legacy fault")
        self.assertIsNone(defect.resolved_at)

        # Idempotent: a second run creates nothing.
        self.assertEqual(backfill_open_defects(), 0)
        self.assertEqual(resource.defects.count(), 1)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ImageUploadApiTests(APITestCase):
    """Upload/clear images on catalog entities via the multipart action."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="user")
        self.product_type = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(
            product_type=self.product_type, title="Sony Alpha 7"
        )
        self.section = Section.objects.create(title="Recording")
        from catalog.models import Category

        self.category = Category.objects.create(name="Cameras")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")

    def _png(self, name="pic.png"):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin)
        bad = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        response = self.client.post(
            f"/api/manage/products/{self.product.id}/images/",
            {"image": bad},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_to_all_entities(self):
        self.client.force_login(self.admin)
        cases = [
            ("sections", self.section.id, "/sections/"),
            ("categories", self.category.id, "/categories/"),
            ("pools", self.pool.id, "/pools/"),
        ]
        for path, pk, prefix in cases:
            response = self.client.post(
                f"/api/manage/{path}/{pk}/image/",
                {"image": self._png(f"{path}.png")},
                format="multipart",
            )
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(prefix, response.data["image"], path)

    def test_category_image_shop_exposure(self):
        self.client.force_login(self.admin)
        url = f"/api/manage/categories/{self.category.id}/image/"
        self.client.post(url, {"image": self._png()}, format="multipart")
        self.section.categories.add(self.category)
        shop = self.client.get(f"/api/sections/{self.section.id}/").json()
        self.assertTrue(shop["categories"][0]["image"].startswith("http"))
        self.assertIn("/categories/", shop["categories"][0]["image"])

    def test_product_type_has_no_image_endpoint(self):
        """#78: type images moved to categories; the endpoint is gone, so it
        can't delete a file the migrated category still references."""
        self.client.force_login(self.admin)
        url = f"/api/manage/product-types/{self.product_type.id}/image/"
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(
            self.client.post(url, {"image": self._png()}, format="multipart").status_code,
            404,
        )


class FeaturedProductsTests(APITestCase):
    """Start-page featured rows: most popular and newest, eligibility-filtered."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from lending.models import Booking
        from lending.services import create_reservation

        self.Booking = Booking
        self.create_reservation = create_reservation
        self.pool = ResourcePool.objects.create(
            name="DigiLab", pool_id="DigiLab", closed_weekdays=[], max_booking_months=0
        )
        pt = ProductType.objects.create(name="Camera")
        # Created in order A, B, C → C is newest.
        self.a = Product.objects.create(product_type=pt, title="Alpha")
        self.b = Product.objects.create(product_type=pt, title="Bravo")
        self.c = Product.objects.create(product_type=pt, title="Charlie")
        self.now = timezone.now()
        self.day = timedelta(days=1)
        for product, count in [(self.a, 3), (self.b, 1)]:
            for i in range(count):
                r = Resource.objects.create(
                    product=product, resource_pool=self.pool,
                    inventory_number=f"{product.title}-{i}", qr_code_id=f"QR-{product.title}-{i}",
                )
                start = self.now + self.day * i
                self.create_reservation(
                    self.borrower_dummy(), [(r, start, start + self.day)],
                    status=Booking.Status.CONFIRMED,
                )
        # Charlie has a resource but no bookings.
        Resource.objects.create(
            product=self.c, resource_pool=self.pool,
            inventory_number="Charlie-0", qr_code_id="QR-Charlie-0",
        )

    def borrower_dummy(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user, _ = User.objects.get_or_create(username="borrower")
        return user

    def test_popular_ranked_and_newest_ordered(self):
        res = self.client.get("/api/products/featured/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        popular_titles = [p["title"] for p in body["popular"]]
        # Alpha (3) before Bravo (1); Charlie (0) excluded.
        self.assertEqual(popular_titles, ["Alpha", "Bravo"])
        newest_titles = [p["title"] for p in body["newest"]]
        self.assertEqual(newest_titles[0], "Charlie")  # most recently created
        self.assertEqual(set(newest_titles), {"Alpha", "Bravo", "Charlie"})

    def test_restricted_products_hidden_from_anonymous(self):
        from accounts.models import AccessGroup

        group = AccessGroup.objects.create(name="Locked")
        group.pools.add(self.pool)  # now every product here is gated
        body = self.client.get("/api/products/featured/").json()
        self.assertEqual(body["popular"], [])
        self.assertEqual(body["newest"], [])

    def test_featured_rows_can_be_toggled_off(self):
        from catalog.models import ShopSetting

        setting = ShopSetting.load()
        setting.show_popular = False
        setting.save()
        body = self.client.get("/api/products/featured/").json()
        self.assertEqual(body["popular"], [])
        self.assertTrue(body["newest"])  # new arrivals still shown

        setting.show_new_arrivals = False
        setting.save()
        body = self.client.get("/api/products/featured/").json()
        self.assertEqual(body["newest"], [])

    def test_is_new_follows_the_window(self):
        from catalog.models import ShopSetting

        # Freshly created products are within the default 30-day window.
        body = self.client.get("/api/products/featured/").json()
        self.assertTrue(body["newest"])
        self.assertTrue(all(p["is_new"] for p in body["newest"]))
        # A window of 0 days turns the "new" label off.
        setting = ShopSetting.load()
        setting.new_product_days = 0
        setting.save()
        body = self.client.get("/api/products/featured/").json()
        self.assertTrue(all(not p["is_new"] for p in body["newest"]))


class DefectsOverviewTests(APITestCase):
    """Admin overview of currently/previously defective resources with counts."""

    def setUp(self):
        from django.utils import timezone

        from .models import ResourceDefect

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pool = ResourcePool.objects.create(name="A", pool_id="A")
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Cam")

        # Currently defective — the defect-tracking signal opens the record.
        self.r1 = Resource.objects.create(
            product=product, resource_pool=pool, status="defective",
            defect_note="cracked", inventory_number="A-1", qr_code_id="QR-1",
        )
        # Previously defective twice, now repaired.
        self.r2 = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="A-2", qr_code_id="QR-2",
        )
        for _ in range(2):
            ResourceDefect.objects.create(
                resource=self.r2, note="x", resolved_at=timezone.now()
            )
        # Never defective.
        Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="A-3", qr_code_id="QR-3",
        )

    def test_overview_lists_defective_with_counts(self):
        self.client.force_login(self.admin)
        res = self.client.get("/api/manage/inventory/defects/")
        self.assertEqual(res.status_code, 200)
        rows = {r["inventory_number"]: r for r in res.json()["resources"]}
        self.assertEqual(set(rows), {"A-1", "A-2"})  # A-3 never defective
        self.assertTrue(rows["A-1"]["currently_defective"])
        self.assertEqual(rows["A-1"]["defect_count"], 1)
        self.assertEqual(rows["A-1"]["defect_note"], "cracked")
        self.assertFalse(rows["A-2"]["currently_defective"])
        self.assertEqual(rows["A-2"]["defect_count"], 2)

    def test_requires_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/inventory/defects/").status_code, 403
        )


class ManageProductSetApiTests(APITestCase):
    """Admin CRUD for product sets (concept §5.5)."""

    def setUp(self):
        from .models import ProductSet

        self.ProductSet = ProductSet
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        self.cam = Product.objects.create(product_type=pt, title="Cam")
        self.mic = Product.objects.create(product_type=pt, title="Mic")

    def test_requires_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/product-sets/").status_code, 403)

    def test_crud_flow(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/product-sets/",
            {"name": "Podcast kit", "products": [self.cam.id, self.mic.id]},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        set_id = created.json()["id"]
        self.assertEqual(created.json()["product_count"], 2)

        # Remove a product.
        patched = self.client.patch(
            f"/api/manage/product-sets/{set_id}/",
            {"products": [self.cam.id]},
            format="json",
        )
        self.assertEqual(patched.json()["product_count"], 1)

        self.assertEqual(
            self.client.delete(f"/api/manage/product-sets/{set_id}/").status_code, 204
        )
        self.assertFalse(self.ProductSet.objects.filter(pk=set_id).exists())


class ResourceByQrTests(APITestCase):
    """Public device-QR resolution for the /r/<qr_id> redirect (concept §6.2)."""

    def test_resolve_returns_product(self):
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Camera")
        pool = ResourcePool.objects.create(name="Pool", pool_id="P")
        resource = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="P-001", qr_code_id="QR-1",
        )
        res = self.client.get(f"/api/resources/by-qr/{resource.qr_code_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["product"], product.id)

    def test_unknown_qr_is_404(self):
        self.assertEqual(
            self.client.get("/api/resources/by-qr/nope/").status_code, 404
        )


class QrLabelTests(APITestCase):
    """Printable device-QR label image endpoint (concept §6.2, phase 2)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Camera")
        pool = ResourcePool.objects.create(name="Pool", pool_id="P")
        self.resource = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="P-001", qr_code_id="QR-1",
        )

    def test_admin_gets_png(self):
        self.client.force_login(self.admin)
        res = self.client.get(f"/api/manage/inventory/{self.resource.id}/qr/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/png")
        self.assertTrue(res.content.startswith(b"\x89PNG"))

    def test_non_admin_forbidden(self):
        self.client.force_login(self.borrower)
        res = self.client.get(f"/api/manage/inventory/{self.resource.id}/qr/")
        self.assertEqual(res.status_code, 403)


class InventoryCreatedAfterFilterTests(APITestCase):
    """`?created_after=` narrows inventory to newly added resources (QR labels)."""

    def test_created_after_excludes_older(self):
        from datetime import timedelta
        from django.utils import timezone

        admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Camera")
        pool = ResourcePool.objects.create(name="Pool", pool_id="P")
        new = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="P-NEW", qr_code_id="QR-NEW",
        )
        old = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="P-OLD", qr_code_id="QR-OLD",
        )
        # created_at is auto-set; backdate the "old" one past the cutoff.
        Resource.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        since = (timezone.now() - timedelta(days=1)).date().isoformat()
        self.client.force_login(admin)
        res = self.client.get(
            f"/api/manage/inventory/?pool={pool.id}&created_after={since}"
        )
        nums = [r["inventory_number"] for r in res.json()["results"]]
        self.assertIn("P-NEW", nums)
        self.assertNotIn("P-OLD", nums)


class InventoryOrderingApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="ordboss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        pt = ProductType.objects.create(name="Cam-ord")
        product = Product.objects.create(product_type=pt, title="GoPro-ord")
        pool = ResourcePool.objects.create(name="P-ord", pool_id="P-ord")
        # Ratings chosen so neither ascending nor descending rating order
        # equals the inventory-number order (A,B,C) — both are real
        # discriminators. ratings: A=4, B=5, C=2.
        self.by_number = {}
        for num, rating in [("P-ord-C", 2), ("P-ord-A", 4), ("P-ord-B", 5)]:
            r = Resource.objects.create(
                product=product, resource_pool=pool,
                inventory_number=num, qr_code_id=f"QR-{num}",
                condition_rating=rating,
            )
            self.by_number[num] = r

    def _numbers(self, ordering):
        resp = self.client.get(f"/api/manage/inventory/?ordering={ordering}")
        self.assertEqual(resp.status_code, 200)
        return [row["inventory_number"] for row in resp.data["results"]]

    def test_order_by_condition_rating_ascending(self):
        self.assertEqual(self._numbers("condition_rating"),
                         ["P-ord-C", "P-ord-A", "P-ord-B"])  # 2,4,5

    def test_order_by_condition_rating_descending(self):
        self.assertEqual(self._numbers("-condition_rating"),
                         ["P-ord-B", "P-ord-A", "P-ord-C"])  # 5,4,2

    def test_unknown_ordering_field_falls_back_to_default(self):
        # `value` is not in ordering_fields -> default inventory_number order.
        self.assertEqual(self._numbers("value"),
                         ["P-ord-A", "P-ord-B", "P-ord-C"])


class AttributeUsageTests(APITestCase):
    """Per-attribute usage count for the delete-attribute warning (§5.2)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.pt = ProductType.objects.create(
            name="Camera",
            attribute_schema=[
                {"key": "color", "label": "Color", "type": "short_text",
                 "default": "black", "visible": True, "required": False},
                {"key": "weight", "label": "Weight", "type": "number",
                 "default": None, "visible": True, "required": False},
            ],
        )
        # filled non-default color + a weight
        Product.objects.create(product_type=self.pt, title="A",
                               attributes={"color": "red", "weight": 500})
        # color left at default -> does not count; weight empty
        Product.objects.create(product_type=self.pt, title="B",
                               attributes={"color": "black"})
        # color filled non-default; no weight
        Product.objects.create(product_type=self.pt, title="C",
                               attributes={"color": "blue"})

    def test_usage_counts_non_default_values(self):
        self.client.force_login(self.admin)
        body = self.client.get(
            f"/api/manage/product-types/{self.pt.id}/attribute-usage/"
        ).json()
        self.assertEqual(body["color"], 2)   # red, blue (black is the default)
        self.assertEqual(body["weight"], 1)  # 500

    def test_requires_admin(self):
        self.client.force_login(self.borrower)
        res = self.client.get(
            f"/api/manage/product-types/{self.pt.id}/attribute-usage/"
        )
        self.assertEqual(res.status_code, 403)


class LeihsImportTests(TestCase):
    """The leihs CSV importer maps models→products, items→resources,
    is idempotent, and never reads personal columns."""

    CSV = (
        "Produkt;Hersteller;Beschreibung;Inventarcode;Seriennummer;"
        "Ausmusterung;Ausleihbar;Gebäude;Raum;Ausleihende/r Nachname\n"
        "Kamera A;Sony;Eine Kamera;INV-1;SN1;;true;StudZ;101;Geheim\n"
        "Kamera A;Sony;Eine Kamera;INV-2;SN2;;false;StudZ;102;Geheim\n"
        "Mikrofon B;Rode;Ein Mikro;INV-3;;2023-01-01;true;EW;201;Geheim\n"
    )

    def _run(self, **kw):
        from django.core.management import call_command

        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", encoding="utf-8", delete=False
        ) as f:
            f.write(self.CSV)
            path = f.name
        call_command("import_leihs", path, pool="TestPool", verbosity=0, **kw)

    def test_import_maps_models_and_items(self):
        from catalog.models import Product, Resource

        self._run()
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Resource.objects.count(), 3)

        kamera = Product.objects.get(title="Kamera A")
        self.assertEqual(kamera.attributes.get("hersteller"), "Sony")
        # #98: the description is rich HTML.
        self.assertEqual(kamera.description, "<p>Eine Kamera</p>")

        r1 = Resource.objects.get(inventory_number="INV-1")
        self.assertEqual(r1.status, Resource.Status.AVAILABLE)
        self.assertEqual(r1.serial_number, "SN1")
        self.assertEqual(r1.storage_location, "StudZ · 101")
        self.assertEqual(r1.qr_code_id, "leihs-INV-1")

        # Ausleihbar=false → blocked; Ausmusterung set → retired.
        self.assertEqual(
            Resource.objects.get(inventory_number="INV-2").status,
            Resource.Status.BLOCKED,
        )
        self.assertEqual(
            Resource.objects.get(inventory_number="INV-3").status,
            Resource.Status.RETIRED,
        )

    def test_personal_columns_are_never_imported(self):
        from catalog.models import Product, Resource

        self._run()
        # "Geheim" (a borrower surname) must not have landed anywhere.
        for p in Product.objects.all():
            self.assertNotIn("Geheim", p.description)
            self.assertNotIn("Geheim", str(p.attributes))
        for r in Resource.objects.all():
            blob = f"{r.serial_number}{r.storage_location}{r.procuring_institution}"
            self.assertNotIn("Geheim", blob)

    def test_import_is_idempotent(self):
        from catalog.models import Product, Resource

        self._run()
        self._run()  # second run must not duplicate
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Resource.objects.count(), 3)

    def test_dry_run_writes_nothing(self):
        from catalog.models import Product, Resource

        self._run(dry_run=True)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Resource.objects.count(), 0)


class AdminListSearchPaginationTests(APITestCase):
    """Manage list endpoints support ?search= and ?page=/?page_size=."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.pt = ProductType.objects.create(name="Camera")
        for i in range(30):
            Product.objects.create(product_type=self.pt, title=f"Cam {i:02d}")
        Product.objects.create(product_type=self.pt, title="Tripod special")

    def test_default_page_size_paginates(self):
        res = self.client.get("/api/manage/products/")
        self.assertEqual(res.data["count"], 31)
        self.assertEqual(len(res.data["results"]), 25)  # first page
        self.assertIsNotNone(res.data["next"])

    def test_second_page(self):
        res = self.client.get("/api/manage/products/?page=2")
        self.assertEqual(len(res.data["results"]), 6)

    def test_search_filters(self):
        res = self.client.get("/api/manage/products/?search=Tripod")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["title"], "Tripod special")

    def test_page_size_override_returns_all(self):
        res = self.client.get("/api/manage/products/?page_size=2000")
        self.assertEqual(len(res.data["results"]), 31)


class PdfAttributeTests(APITestCase):
    """A 'pdf' product-type attribute: upload, expose, validate, delete."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.pt = ProductType.objects.create(
            name="Camera",
            attribute_schema=[
                {"key": "manual", "label": "Manual", "type": "pdf",
                 "visible": True, "required": False, "default": ""},
            ],
        )
        self.product = Product.objects.create(product_type=self.pt, title="A7")
        # An available unit so the product is visible in the borrower shop.
        pool = ResourcePool.objects.create(name="Lab", pool_id="LAB")
        Resource.objects.create(
            product=self.product, resource_pool=pool,
            inventory_number="LAB-1", qr_code_id="QR-LAB-1",
        )

    def _pdf(self, name="manual.pdf", content=b"%PDF-1.4 test"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_upload_sets_media_url_value(self):
        import tempfile
        from django.test import override_settings
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            res = self.client.post(
                f"/api/manage/products/{self.product.id}/attribute-pdf/?key=manual",
                {"file": self._pdf()},
                format="multipart",
            )
            self.assertEqual(res.status_code, 200)
            url = res.data["attributes"]["manual"]
            self.assertTrue(url.startswith("/media/") and url.endswith(".pdf"), url)

    def test_rejects_non_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import tempfile
        from django.test import override_settings
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            bad = SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")
            res = self.client.post(
                f"/api/manage/products/{self.product.id}/attribute-pdf/?key=manual",
                {"file": bad},
                format="multipart",
            )
            self.assertEqual(res.status_code, 400)

    def test_rejects_unknown_or_non_pdf_attribute(self):
        res = self.client.post(
            f"/api/manage/products/{self.product.id}/attribute-pdf/?key=nope",
            {"file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)

    def test_delete_clears_value(self):
        import tempfile
        from django.test import override_settings
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            self.client.post(
                f"/api/manage/products/{self.product.id}/attribute-pdf/?key=manual",
                {"file": self._pdf()}, format="multipart",
            )
            res = self.client.delete(
                f"/api/manage/products/{self.product.id}/attribute-pdf/?key=manual"
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data["attributes"]["manual"], "")

    def test_visible_attribute_exposes_pdf(self):
        self.product.attributes = {"manual": "/media/product-docs/x.pdf"}
        self.product.save()
        res = self.client.get(f"/api/products/{self.product.id}/")
        attrs = {a["key"]: a for a in res.data["visible_attributes"]}
        self.assertEqual(attrs["manual"]["type"], "pdf")
        self.assertEqual(attrs["manual"]["value"], "/media/product-docs/x.pdf")


class ProductTypeFilterTests(APITestCase):
    """Admin product list filters by ?product_type=<id> (#20)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.pt = ProductType.objects.create(name="Camera")
        self.other = ProductType.objects.create(name="Tripod")
        self.a7 = Product.objects.create(product_type=self.pt, title="A7")
        Product.objects.create(product_type=self.other, title="Manfrotto")

    def test_filter_by_product_type(self):
        res = self.client.get(f"/api/manage/products/?product_type={self.pt.id}")
        titles = [p["title"] for p in res.data["results"]]
        self.assertEqual(titles, ["A7"])

    def test_invalid_product_type_returns_nothing(self):
        res = self.client.get("/api/manage/products/?product_type=none")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 0)

    def test_no_filter_returns_all(self):
        res = self.client.get("/api/manage/products/")
        self.assertEqual(res.data["count"], 2)


class WelcomePageTests(APITestCase):
    """Public welcome content + admin-editable rich text (HTML)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab", is_active=True)
        ResourcePool.objects.create(name="Old", pool_id="Old", is_active=False)

    def test_welcome_is_public_and_lists_active_pools(self):
        res = self.client.get("/api/welcome/")  # no auth
        self.assertEqual(res.status_code, 200)
        self.assertIn("text", res.data)
        names = [p["name"] for p in res.data["pools"]]
        self.assertEqual(names, ["DigiLab"])  # inactive pool excluded

    def test_admin_sets_text_and_it_shows_publicly(self):
        self.client.force_login(self.admin)
        put = self.client.put(
            "/api/manage/welcome-setting/",
            {"text": "## Willkommen\nBitte einloggen."},
            format="json",
        )
        self.assertEqual(put.status_code, 200)
        self.client.logout()
        res = self.client.get("/api/welcome/")
        self.assertEqual(res.data["text"], "## Willkommen\nBitte einloggen.")

    def test_setting_edit_requires_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/welcome-setting/").status_code, 403
        )


class LenderInventoryAccessTests(APITestCase):
    """Moved-to-Verleih features: lenders manage inventory/defects scoped to
    their pools, and the shared catalog (products/sets); admins are unscoped."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.pool_a = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        self.pool_b = ResourcePool.objects.create(name="Podcast", pool_id="Podcast")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool_a)
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="Cam")
        self.res_a = Resource.objects.create(
            product=self.product, resource_pool=self.pool_a,
            inventory_number="DigiLab-001", qr_code_id="QR-DigiLab-001",
        )
        self.res_b = Resource.objects.create(
            product=self.product, resource_pool=self.pool_b,
            inventory_number="Podcast-001", qr_code_id="QR-Podcast-001",
        )

    def test_lender_lists_only_their_pool_inventory(self):
        self.client.force_login(self.lender)
        res = self.client.get("/api/manage/inventory/")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], self.res_a.id)
        # Filtering to a foreign pool yields nothing (still scoped).
        res = self.client.get("/api/manage/inventory/", {"pool": self.pool_b.id})
        self.assertEqual(res.data["count"], 0)

    def test_admin_sees_all_inventory(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/api/manage/inventory/").data["count"], 2)

    def test_lender_cannot_retrieve_foreign_resource(self):
        self.client.force_login(self.lender)
        self.assertEqual(
            self.client.get(f"/api/manage/inventory/{self.res_b.id}/").status_code, 404
        )

    def test_lender_can_edit_own_resource(self):
        self.client.force_login(self.lender)
        res = self.client.patch(
            f"/api/manage/inventory/{self.res_a.id}/",
            {"storage_location": "Shelf 3"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["storage_location"], "Shelf 3")

    def test_lender_cannot_create_in_unmanaged_pool(self):
        self.client.force_login(self.lender)
        payload = {
            "product": self.product.id,
            "resource_pool": self.pool_b.id,
            "inventory_number": "Podcast-002",
            "qr_code_id": "QR-Podcast-002",
            "status": "available",
        }
        self.assertEqual(
            self.client.post("/api/manage/inventory/", payload, format="json").status_code,
            403,
        )
        payload["resource_pool"] = self.pool_a.id
        payload["inventory_number"] = "DigiLab-002"
        payload["qr_code_id"] = "QR-DigiLab-002"
        self.assertEqual(
            self.client.post("/api/manage/inventory/", payload, format="json").status_code,
            201,
        )

    def test_lender_reads_only_managed_pools(self):
        self.client.force_login(self.lender)
        res = self.client.get("/api/manage/pools/")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], self.pool_a.id)

    def test_lender_can_edit_shared_catalog_product(self):
        self.client.force_login(self.lender)
        res = self.client.patch(
            f"/api/manage/products/{self.product.id}/",
            {"title": "Camera Pro"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["title"], "Camera Pro")

    def test_lender_defects_overview_scoped_to_pools(self):
        ResourceDefect.objects.create(resource=self.res_a, note="lens")
        ResourceDefect.objects.create(resource=self.res_b, note="mic")
        self.client.force_login(self.lender)
        ids = {r["id"] for r in self.client.get("/api/manage/inventory/defects/").data["resources"]}
        self.assertEqual(ids, {self.res_a.id})
        self.client.force_login(self.admin)
        ids = {r["id"] for r in self.client.get("/api/manage/inventory/defects/").data["resources"]}
        self.assertEqual(ids, {self.res_a.id, self.res_b.id})


class SearchApiTests(APITestCase):
    """Shop search by product name (categories/sections: CategoryShopApiTests)."""

    def setUp(self):
        self.pt = ProductType.objects.create(name="Video Cameras")
        self.product = Product.objects.create(product_type=self.pt, title="Sony Alpha 7")
        self.section = Section.objects.create(title="Recording Technology")
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        Resource.objects.create(
            product=self.product, resource_pool=pool,
            inventory_number="D-1", qr_code_id="QR-D-1",
        )

    def test_product_name_returns_product_only(self):
        res = self.client.get("/api/search/", {"q": "Sony"})
        self.assertEqual([p["title"] for p in res.data["products"]], ["Sony Alpha 7"])
        self.assertEqual(res.data["categories"], [])
        self.assertEqual(res.data["sections"], [])
        # Product types are no longer matched (#78).
        self.assertNotIn("product_types", self.client.get("/api/search/", {"q": "Video"}).data)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductImagesApiTests(APITestCase):
    """Multi-image product gallery: upload/append, cover, delete, reorder."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        pool = ResourcePool.objects.create(name="P", pool_id="P")
        PoolMembership.objects.create(user=self.lender, resource_pool=pool)
        self.borrower = User.objects.create_user(username="bob")
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="Cam")

    def _png(self, name="pic.png"):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), (10, 120, 200)).save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def _upload(self, name="pic.png"):
        return self.client.post(
            f"/api/manage/products/{self.product.id}/images/",
            {"image": self._png(name)},
            format="multipart",
        )

    def _manage(self):
        return self.client.get(f"/api/manage/products/{self.product.id}/").data

    def test_borrower_cannot_upload(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self._upload().status_code, 403)

    def test_lender_uploads_append_and_set_cover(self):
        self.client.force_login(self.lender)
        a = self._upload("a.png")
        b = self._upload("b.png")
        self.assertEqual(a.status_code, 201)
        self.assertEqual(a.data["position"], 0)
        self.assertEqual(b.data["position"], 1)
        data = self._manage()
        self.assertEqual(len(data["images"]), 2)
        self.assertEqual(data["image"], data["images"][0]["image"])  # cover = first

    def test_delete_image_updates_cover(self):
        self.client.force_login(self.lender)
        a = self._upload("a.png")
        b = self._upload("b.png")
        res = self.client.delete(
            f"/api/manage/products/{self.product.id}/images/{a.data['id']}/"
        )
        self.assertEqual(res.status_code, 204)
        data = self._manage()
        self.assertEqual([i["id"] for i in data["images"]], [b.data["id"]])
        self.assertEqual(data["image"], b.data["image"])

    def test_reorder_changes_cover(self):
        self.client.force_login(self.lender)
        a = self._upload("a.png")
        b = self._upload("b.png")
        res = self.client.post(
            f"/api/manage/products/{self.product.id}/images/reorder/",
            {"order": [b.data["id"], a.data["id"]]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        data = self._manage()
        self.assertEqual([i["id"] for i in data["images"]], [b.data["id"], a.data["id"]])
        self.assertEqual(data["image"], b.data["image"])

    def test_reorder_rejects_incomplete_list(self):
        self.client.force_login(self.lender)
        a = self._upload("a.png")
        self._upload("b.png")
        res = self.client.post(
            f"/api/manage/products/{self.product.id}/images/reorder/",
            {"order": [a.data["id"]]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class ShopPoolsApiTests(APITestCase):
    """Borrower browse-by-pool: /api/pools/ (eligible) and /api/products/?pool=."""

    def setUp(self):
        from accounts.models import AccessGroup

        pt = ProductType.objects.create(name="Camera")
        self.open_pool = ResourcePool.objects.create(name="Open", pool_id="OPEN")
        self.locked_pool = ResourcePool.objects.create(name="Locked", pool_id="LOCK")
        group = AccessGroup.objects.create(name="Music")
        group.pools.add(self.locked_pool)

        self.open_product = Product.objects.create(product_type=pt, title="Open Cam")
        Resource.objects.create(
            product=self.open_product, resource_pool=self.open_pool,
            inventory_number="O-1", qr_code_id="QR-O-1",
        )
        self.locked_product = Product.objects.create(product_type=pt, title="Locked Cam")
        Resource.objects.create(
            product=self.locked_product, resource_pool=self.locked_pool,
            inventory_number="L-1", qr_code_id="QR-L-1",
        )

    def test_anonymous_sees_only_open_pool(self):
        names = [p["name"] for p in self.client.get("/api/pools/").json()]
        self.assertEqual(names, ["Open"])

    def test_member_sees_restricted_pool(self):
        member = User.objects.create_user(username="m")
        from accounts.models import AccessGroup

        AccessGroup.objects.get(name="Music").members.add(member)
        self.client.force_login(member)
        names = {p["name"] for p in self.client.get("/api/pools/").json()}
        self.assertEqual(names, {"Open", "Locked"})

    def test_products_filtered_by_pool(self):
        res = self.client.get("/api/products/", {"pool": self.open_pool.id})
        titles = [p["title"] for p in res.json()["results"]]
        self.assertEqual(titles, ["Open Cam"])

    def test_blocked_only_pool_product_hidden(self):
        # An open pool whose product has only a blocked unit stays out of the shop.
        pool = ResourcePool.objects.create(name="Empty", pool_id="EMP")
        pt = ProductType.objects.create(name="Beamer")
        prod = Product.objects.create(product_type=pt, title="Dead Cam")
        Resource.objects.create(
            product=prod, resource_pool=pool, status=Resource.Status.BLOCKED,
            inventory_number="E-1", qr_code_id="QR-E-1",
        )
        res = self.client.get("/api/products/", {"pool": pool.id})
        self.assertEqual(res.json()["results"], [])


class ShopPoolProductsGroupedApiTests(APITestCase):
    """/api/pools/<id>/products-grouped/ access (grouping: CategoryShopApiTests)."""

    def test_hidden_pool_404s(self):
        from accounts.models import AccessGroup

        locked_pool = ResourcePool.objects.create(name="Locked", pool_id="LOCK")
        group = AccessGroup.objects.create(name="Music")
        group.pools.add(locked_pool)
        res = self.client.get(f"/api/pools/{locked_pool.id}/products-grouped/")
        self.assertEqual(res.status_code, 404)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BrandingApiTests(APITestCase):
    """Admin uploads the shop logo (image or SVG); /api/branding/ serves it."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="bob")

    def _png(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="PNG")
        return SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")

    def _post(self, upload):
        return self.client.post(
            "/api/manage/welcome-setting/logo/", {"logo": upload}, format="multipart"
        )

    def test_branding_empty_by_default(self):
        self.assertIsNone(self.client.get("/api/branding/").json()["logo"])

    def test_admin_uploads_png_and_branding_serves_it(self):
        self.client.force_login(self.admin)
        res = self._post(self._png())
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["logo"])
        self.client.logout()
        self.assertTrue(self.client.get("/api/branding/").json()["logo"])

    def test_svg_accepted(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin)
        svg = SimpleUploadedFile(
            "logo.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )
        res = self._post(svg)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["logo"].endswith(".svg"))

    def test_non_image_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin)
        bad = SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")
        self.assertEqual(self._post(bad).status_code, 400)

    def test_requires_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self._post(self._png()).status_code, 403)

    def test_delete_clears_logo(self):
        self.client.force_login(self.admin)
        self._post(self._png())
        res = self.client.delete("/api/manage/welcome-setting/logo/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data["logo"])


class EffectiveMaxDurationTests(APITestCase):
    """Product detail exposes the max lending duration with pool inheritance (#21)."""

    def setUp(self):
        self.pt = ProductType.objects.create(name="Camera", attribute_schema=[])
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")

    def _product(self, **kwargs):
        product = Product.objects.create(product_type=self.pt, title="Cam", **kwargs)
        Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number=f"D-{product.pk}",
            qr_code_id=f"QR-{product.pk}",
        )
        return product

    def _emax(self, product):
        res = self.client.get(f"/api/products/{product.id}/")
        self.assertEqual(res.status_code, 200)
        return res.data["effective_max_duration"]

    def test_product_override_wins(self):
        self.pool.default_max_days = 14
        self.pool.save()
        product = self._product(lending_type="days", max_duration=5)
        self.assertEqual(self._emax(product), 5)

    def test_inherits_pool_default_when_product_has_none(self):
        self.pool.default_max_days = 14
        self.pool.save()
        product = self._product(lending_type="days", max_duration=None)
        self.assertEqual(self._emax(product), 14)

    def test_hourly_inherits_hour_default_not_day_default(self):
        self.pool.default_max_days = 14
        self.pool.default_max_hours = 8
        self.pool.save()
        product = self._product(lending_type="hours", max_duration=None)
        self.assertEqual(self._emax(product), 8)

    def test_none_when_no_limit_anywhere(self):
        product = self._product(lending_type="days", max_duration=None)
        self.assertIsNone(self._emax(product))


class PageApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        # Start from a clean slate (the seed migration creates imprint/privacy).
        Page.objects.all().delete()
        self.published = Page.objects.create(
            slug="imprint", title="Impressum", body="# Impressum", footer_order=10
        )
        self.draft = Page.objects.create(
            slug="privacy",
            title="Datenschutz",
            body="draft",
            is_published=False,
            footer_order=20,
        )
        self.hidden = Page.objects.create(
            slug="internal", title="Internal", body="x", show_in_footer=False
        )

    def test_footer_lists_only_published_footer_pages(self):
        # Public, no auth required.
        res = self.client.get("/api/pages/")
        self.assertEqual(res.status_code, 200)
        slugs = [p["slug"] for p in res.data]
        self.assertEqual(slugs, ["imprint"])  # ordered by footer_order

    def test_public_detail_returns_published_page(self):
        res = self.client.get("/api/pages/imprint/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["body"], "# Impressum")

    def test_public_detail_hides_unpublished(self):
        self.assertEqual(self.client.get("/api/pages/privacy/").status_code, 404)

    def test_borrower_cannot_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/pages/").status_code, 403)

    def test_admin_crud(self):
        self.client.force_login(self.admin)
        # Admin sees drafts too (paginated response).
        listing = self.client.get("/api/manage/pages/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 3)

        created = self.client.post(
            "/api/manage/pages/",
            {"slug": "faq", "title": "FAQ", "body": "## FAQ"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        page_id = created.data["id"]

        patched = self.client.patch(
            f"/api/manage/pages/{page_id}/",
            {"is_published": False},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(patched.data["is_published"])

        self.assertEqual(
            self.client.delete(f"/api/manage/pages/{page_id}/").status_code, 204
        )

    def test_new_page_appends_at_end(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/pages/",
            {"slug": "faq", "title": "FAQ", "body": "## FAQ"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        # Highest existing footer_order is 20 (privacy) → new page gets 21.
        self.assertEqual(Page.objects.get(slug="faq").footer_order, 21)

    def test_reorder_rewrites_footer_order_and_footer_listing(self):
        self.client.force_login(self.admin)
        # Put the (published, footer) pages in a deliberate order.
        self.draft.is_published = True
        self.draft.save(update_fields=["is_published"])
        order = [self.draft.id, self.hidden.id, self.published.id]
        res = self.client.post(
            "/api/manage/pages/reorder/", {"order": order}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.published.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_order, 0)
        self.assertEqual(self.published.footer_order, 2)
        # The public footer reflects the new order (privacy now before imprint).
        slugs = [p["slug"] for p in self.client.get("/api/pages/").data]
        self.assertEqual(slugs, ["privacy", "imprint"])

    def test_reorder_rejects_incomplete_id_list(self):
        self.client.force_login(self.admin)
        res = self.client.post(
            "/api/manage/pages/reorder/",
            {"order": [self.published.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_reorder_requires_admin(self):
        self.client.force_login(self.borrower)
        res = self.client.post(
            "/api/manage/pages/reorder/",
            {"order": [self.published.id, self.draft.id, self.hidden.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TransferTests(APITestCase):
    """Export → import round-trip of the catalog data set (catalog/transfer.py)."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def _png_bytes():
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, format="PNG")
        return buffer.getvalue()

    def setUp(self):
        from django.core.files.base import ContentFile

        from catalog.models import ProductSet

        self.ptype = ProductType.objects.create(name="Camera")
        self.ptype.description_en = "Cameras"
        self.ptype.save()
        self.mic_type = ProductType.objects.create(name="Microphone")
        self.product = Product.objects.create(
            product_type=self.ptype, title="Alpha 7", lending_type="days",
            attributes={"mp": 24},
        )
        self.product.title_en = "Alpha 7"
        self.product.description_en = "A camera"
        self.product.save()
        self.p2 = Product.objects.create(product_type=self.ptype, title="GoPro")
        self.mic = Product.objects.create(product_type=self.mic_type, title="Rode NT")
        self.section = Section.objects.create(title="Recording")
        self.set = ProductSet.objects.create(name="Video Kit")
        self.set.products.set([self.product])
        # Shop navigation (#78): Cameras › Action, plus a second root "Audio".
        self.cameras = Category.objects.create(name="Cameras", position=1)
        self.cameras.name_en = "Cameras"
        self.cameras.description_en = "All cameras"
        self.cameras.image.save("cams.png", ContentFile(self._png_bytes()), save=False)
        self.cameras.save()
        self.action = Category.objects.create(name="Action", parent=self.cameras)
        self.audio = Category.objects.create(name="Audio", position=0)
        self.cameras.products.set([self.product, self.p2])
        self.action.products.set([self.p2])
        self.audio.products.set([self.mic])
        self.cameras.product_order = [self.p2.id, self.product.id]
        self.cameras.save()
        # A trashed category is not part of the export.
        Category.objects.create(name="Old", parent=None).soft_delete(None)
        self.section.categories.set([self.cameras, self.audio])
        self.section.category_order = [self.cameras.id, self.audio.id]
        self.section.save()
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="digilab")
        self.r1 = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DL-1", qr_code_id="qr-dl-1", serial_number="SN1",
        )
        # A second pool/resource to prove pool-scoped export filters.
        self.pool2 = ResourcePool.objects.create(name="Studio", pool_id="studio")
        Resource.objects.create(
            product=self.p2, resource_pool=self.pool2,
            inventory_number="ST-1", qr_code_id="qr-st-1",
        )

    def _archive(self, edit):
        import io, json, zipfile
        from catalog.transfer import build_archive
        zin = zipfile.ZipFile(io.BytesIO(build_archive("full")))
        manifest = json.loads(zin.read("manifest.json"))
        edit(manifest)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = json.dumps(manifest) if item.filename == "manifest.json" else zin.read(item.filename)
                zout.writestr(item, data)
        return io.BytesIO(out.getvalue())

    def _row(self, manifest, number):
        return next(r for r in manifest["resources"] if r["inventory_number"] == number)

    def test_import_blank_qr_keeps_existing_id(self):
        from catalog.transfer import import_archive
        import_archive(self._archive(lambda m: self._row(m, "DL-1").update(qr_code_id="")))
        self.assertEqual(Resource.objects.get(inventory_number="DL-1").qr_code_id, "qr-dl-1")

    def test_import_clashing_qr_keeps_existing_id(self):
        from catalog.transfer import import_archive
        import_archive(self._archive(lambda m: self._row(m, "DL-1").update(qr_code_id="qr-st-1")))
        self.assertEqual(Resource.objects.get(inventory_number="DL-1").qr_code_id, "qr-dl-1")
        self.assertEqual(Resource.objects.get(inventory_number="ST-1").qr_code_id, "qr-st-1")

    def test_import_new_unit_without_qr_gets_default(self):
        from catalog.transfer import import_archive
        def edit(m):
            row = dict(self._row(m, "DL-1"), inventory_number="DL 2", qr_code_id="")
            m["resources"].append(row)
        import_archive(self._archive(edit))
        self.assertEqual(Resource.objects.get(inventory_number="DL 2").qr_code_id, "QR-DL-2")

    def test_import_new_unit_with_free_qr_keeps_it(self):
        from catalog.transfer import import_archive
        def edit(m):
            m["resources"].append(dict(self._row(m, "DL-1"), inventory_number="DL-3", qr_code_id="label-77"))
        import_archive(self._archive(edit))
        self.assertEqual(Resource.objects.get(inventory_number="DL-3").qr_code_id, "label-77")

    def test_import_existing_unit_takes_new_free_qr(self):
        from catalog.transfer import import_archive
        import_archive(self._archive(lambda m: self._row(m, "DL-1").update(qr_code_id="qr-new-1")))
        self.assertEqual(Resource.objects.get(inventory_number="DL-1").qr_code_id, "qr-new-1")

    def test_import_integer_qr_code_id_converted_to_string(self):
        from catalog.transfer import import_archive
        import_archive(self._archive(lambda m: self._row(m, "DL-1").update(qr_code_id=1234)))
        self.assertEqual(Resource.objects.get(inventory_number="DL-1").qr_code_id, "1234")

    def _manifest(self, archive):
        import json
        import zipfile

        return json.loads(zipfile.ZipFile(io.BytesIO(archive)).read("manifest.json"))

    def test_export_manifest_has_categories_by_path(self):
        import json
        import zipfile
        from catalog.transfer import build_archive

        zf = zipfile.ZipFile(io.BytesIO(build_archive("full")))
        manifest = json.loads(zf.read("manifest.json"))
        # Parents first; natural key = names from the root; trashed left out.
        self.assertEqual(
            [c["path"] for c in manifest["categories"]],
            [["Audio"], ["Cameras"], ["Cameras", "Action"]],
        )
        cams = manifest["categories"][1]
        self.assertEqual(cams["position"], 1)
        self.assertEqual(cams["product_order"], ["GoPro", "Alpha 7"])
        self.assertEqual(cams["description_en"], "All cameras")
        self.assertTrue(cams["image"].startswith("media/categories/"))
        self.assertEqual(zf.read(cams["image"]), self._png_bytes())
        gopro = next(p for p in manifest["products"] if p["title"] == "GoPro")
        self.assertEqual(gopro["categories"], [["Cameras"], ["Cameras", "Action"]])
        section = next(s for s in manifest["sections"] if s["title"] == "Recording")
        self.assertEqual(sorted(section["categories"]), ["Audio", "Cameras"])
        self.assertEqual(section["category_order"], ["Cameras", "Audio"])
        # Product types are attribute templates only (no navigation fields).
        self.assertNotIn("product_types", section)
        camera = next(t for t in manifest["product_types"] if t["name"] == "Camera")
        for key in ("position", "product_order", "image"):
            self.assertNotIn(key, camera)

    def _wipe(self):
        from catalog.models import ProductSet

        Resource.all_objects.all().delete()
        Section.all_objects.all().delete()
        ProductSet.all_objects.all().delete()
        Product.all_objects.all().delete()
        for category in Category.children_first(Category.all_objects.all()):
            category.delete()
        ProductType.all_objects.all().delete()
        ResourcePool.all_objects.all().delete()

    def test_full_roundtrip_recreates_data(self):
        import io
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        self._wipe()

        summary = import_archive(io.BytesIO(archive))
        self.assertGreaterEqual(summary["created"].get("products", 0), 2)
        self.assertEqual(summary["created"]["categories"], 3)
        self.assertEqual(summary["converted"], {})

        product = Product.objects.get(title="Alpha 7")
        gopro = Product.objects.get(title="GoPro")
        self.assertEqual(product.title_en, "Alpha 7")
        self.assertEqual(product.attributes, {"mp": 24})
        self.assertEqual(product.product_type.name, "Camera")

        cameras = Category.objects.get(name="Cameras")
        audio = Category.objects.get(name="Audio")
        action = Category.objects.get(name="Action")
        self.assertIsNone(cameras.parent)
        self.assertEqual(action.parent, cameras)
        self.assertEqual((cameras.position, audio.position), (1, 0))
        self.assertEqual(cameras.description_en, "All cameras")
        # product_order is remapped to the new ids, in the saved order.
        self.assertEqual(cameras.product_order, [gopro.id, product.id])
        self.assertEqual(set(cameras.products.all()), {product, gopro})
        self.assertEqual(list(action.products.all()), [gopro])
        self.assertTrue(cameras.image.name.startswith("categories/"))
        with cameras.image.open("rb") as fh:
            self.assertEqual(fh.read(), self._png_bytes())
        self.assertFalse(Category.all_objects.filter(name="Old").exists())
        section = Section.objects.get(title="Recording")
        self.assertEqual(set(section.categories.all()), {cameras, audio})
        self.assertEqual(section.category_order, [cameras.id, audio.id])

        resource = Resource.objects.get(inventory_number="DL-1")
        self.assertEqual(resource.resource_pool.pool_id, "digilab")
        self.assertEqual(resource.product.title, "Alpha 7")
        self.assertEqual(resource.serial_number, "SN1")

    def test_reimport_updates_categories_in_place(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        # The bare ``name`` column is the natural key.
        Category.objects.rewrite(False).filter(pk=self.action.pk).update(
            name="Changed", name_de="Changed", name_en="Changed"
        )
        Section.objects.get(pk=self.section.pk).categories.clear()

        summary = import_archive(io.BytesIO(archive))

        self.assertEqual(summary["updated"]["categories"], 2)
        self.assertEqual(summary["created"], {"categories": 1})  # "Action" again
        self.assertEqual(Category.objects.filter(name="Cameras").count(), 1)
        self.assertEqual(
            set(self.section.categories.all()), {self.cameras, self.audio}
        )

    def test_import_restores_trashed_category_chain(self):
        from catalog.transfer import import_archive, build_archive

        archive = build_archive("full")
        self.action.soft_delete(None)
        self.cameras.soft_delete(None)

        import_archive(io.BytesIO(archive))

        self.assertEqual(Category.objects.get(name="Cameras").pk, self.cameras.pk)
        self.assertEqual(Category.objects.get(name="Action").pk, self.action.pk)
        self.assertEqual(Category.all_objects.filter(name="Action").count(), 1)

    def test_import_rejects_duplicate_category_paths(self):
        from catalog.transfer import ImportError_, import_archive

        def edit(m):
            m["categories"].append(dict(m["categories"][2]))
        with self.assertRaisesMessage(ImportError_, "Cameras › Action"):
            import_archive(self._archive(edit))

    def test_import_rejects_category_without_parent_row(self):
        from catalog.transfer import ImportError_, import_archive

        def edit(m):
            m["categories"].append({"path": ["Lights", "LED"]})
        with self.assertRaisesMessage(ImportError_, "Lights › LED"):
            import_archive(self._archive(edit))

    def test_import_rejects_malformed_category_path(self):
        from catalog.transfer import ImportError_, import_archive

        for bad in ([], [""], "Cameras", None, [1]):
            with self.subTest(path=bad):
                with self.assertRaises(ImportError_):
                    import_archive(self._archive(
                        lambda m: m["categories"].append({"path": bad})
                    ))

    def test_import_rejects_too_long_category_name(self):
        from catalog.transfer import ImportError_, import_archive

        with self.assertRaisesMessage(ImportError_, "255"):
            import_archive(self._archive(
                lambda m: m["categories"].append({"path": ["x" * 256]})
            ))

    def test_import_view_turns_malformed_archive_into_400(self):
        admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(admin)

        def edit(m):
            del m["products"][0]["title"]  # KeyError deep in the import
        for archive in (
            self._archive(edit),
            self._archive(lambda m: m["categories"].append({"path": ["x" * 256]})),
        ):
            archive.name = "a.zip"
            res = self.client.post("/api/manage/import/", {"file": archive})
            self.assertEqual(res.status_code, 400, res.content)
            self.assertIn("detail", res.json())

    def test_import_db_error_becomes_import_error(self):
        from django.db import IntegrityError

        from catalog import transfer

        with patch.object(transfer, "_import_categories", side_effect=IntegrityError("dup")):
            with self.assertRaises(transfer.ImportError_):
                transfer.import_archive(self._archive(lambda m: None))

    def test_pool_import_keeps_existing_category_texts_and_assignments(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("pool", pool=self.pool)
        Category.objects.filter(pk=self.cameras.pk).update(
            name_en="Local EN", description_en="Local text"
        )
        local = Category.objects.create(name="Local")
        self.product.categories.add(local)

        import_archive(io.BytesIO(archive))

        cams = Category.objects.get(pk=self.cameras.pk)
        self.assertEqual((cams.name_en, cams.description_en), ("Local EN", "Local text"))
        self.assertEqual(
            set(self.product.categories.all()), {self.cameras, local}
        )

    def test_full_import_replaces_product_categories(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        local = Category.objects.create(name="Local")
        self.product.categories.add(local)
        import_archive(io.BytesIO(archive))
        self.assertEqual(list(self.product.categories.all()), [self.cameras])

    def test_section_keeps_only_top_level_categories(self):
        # A hand-edited section naming a subcategory (or an unknown name)
        # only gets the top-level ones.
        from catalog.transfer import import_archive

        def edit(m):
            sec = next(s for s in m["sections"] if s["title"] == "Recording")
            sec["categories"] = ["Action", "Cameras", "Nope"]
            sec["category_order"] = ["Action", "Cameras", "Nope"]
        import_archive(self._archive(edit))
        self.section.refresh_from_db()
        self.assertEqual(list(self.section.categories.all()), [self.cameras])
        self.assertEqual(self.section.category_order, [self.cameras.id])

    def test_import_is_idempotent(self):
        import io
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        summary = import_archive(io.BytesIO(archive))
        # Nothing was deleted, so a re-import only updates — never duplicates.
        self.assertEqual(summary["created"], {})
        self.assertEqual(Product.objects.filter(title="Alpha 7").count(), 1)
        self.assertEqual(Resource.objects.count(), 2)

    def test_pool_scope_includes_only_that_pool(self):
        from catalog.transfer import build_archive

        manifest = self._manifest(build_archive("pool", pool=self.pool))
        self.assertEqual([r["inventory_number"] for r in manifest["resources"]], ["DL-1"])
        self.assertEqual([p["title"] for p in manifest["products"]], ["Alpha 7"])
        self.assertEqual([p["pool_id"] for p in manifest["resource_pools"]], ["digilab"])
        # Pool scope carries no sections (system-wide structure), only the
        # needed product type and the product's categories.
        self.assertEqual(manifest["sections"], [])
        self.assertEqual([t["name"] for t in manifest["product_types"]], ["Camera"])
        self.assertEqual([c["path"] for c in manifest["categories"]], [["Cameras"]])
        self.assertNotIn("position", manifest["categories"][0])
        self.assertNotIn("product_order", manifest["categories"][0])

    def test_pool_scope_includes_category_ancestors(self):
        from catalog.transfer import build_archive

        Resource.objects.create(
            product=self.mic, resource_pool=self.pool2, inventory_number="ST-2",
        )
        sub = Category.objects.create(name="Mics", parent=self.audio)
        self.mic.categories.set([sub])
        manifest = self._manifest(build_archive("pool", pool=self.pool2))
        self.assertEqual(
            [c["path"] for c in manifest["categories"]],
            [["Audio"], ["Audio", "Mics"], ["Cameras"], ["Cameras", "Action"]],
        )

    def test_pool_import_keeps_existing_category_structure(self):
        # A pool archive carries only the pool's products; importing it must
        # not move a category, truncate its product order or swap its image,
        # and it never touches sections.
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("pool", pool=self.pool)
        image_name = self.cameras.image.name
        self.cameras.position = 5
        self.cameras.save()
        self.section.categories.set([self.audio])

        import_archive(io.BytesIO(archive))

        self.cameras.refresh_from_db()
        self.assertEqual(self.cameras.position, 5)
        self.assertEqual(self.cameras.product_order, [self.p2.id, self.product.id])
        self.assertEqual(self.cameras.image.name, image_name)
        self.assertEqual(list(self.section.categories.all()), [self.audio])

    def test_pool_import_fills_new_category_after_siblings(self):
        from catalog.transfer import build_archive, import_archive

        Resource.objects.create(
            product=self.p2, resource_pool=self.pool, inventory_number="DL-9",
        )
        archive = build_archive("pool", pool=self.pool)
        Resource.objects.all().delete()
        Product.objects.all().delete()
        self.action.delete()
        self.cameras.delete()
        Category.objects.create(name="Lights", position=7)

        import_archive(io.BytesIO(archive))

        cameras = Category.objects.get(name="Cameras")
        action = Category.objects.get(name="Action")
        self.assertTrue(cameras.image)
        self.assertEqual(cameras.position, 8)  # after Lights (7), not 0
        self.assertEqual(action.parent, cameras)
        self.assertEqual(action.position, 0)
        self.assertEqual(cameras.product_order, [])
        self.assertEqual(
            set(cameras.products.values_list("title", flat=True)), {"Alpha 7", "GoPro"}
        )

    def test_dry_run_changes_nothing(self):
        import io
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        Resource.objects.all().delete()
        summary = import_archive(io.BytesIO(archive), dry_run=True)
        self.assertTrue(summary.get("dry_run"))
        # Rolled back: the deleted resources were not recreated.
        self.assertEqual(Resource.objects.count(), 0)

    def test_dry_run_creates_no_categories(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        self._wipe()
        summary = import_archive(io.BytesIO(archive), dry_run=True)
        self.assertEqual(summary["created"]["categories"], 3)
        self.assertFalse(Category.all_objects.exists())

    def test_import_restores_trashed_natural_key_match(self):
        # I2: an import whose live item's natural key matches a currently
        # TRASHED row must update+restore that row instead of trying (and
        # failing) to INSERT a duplicate and aborting the whole import.
        import io

        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")  # snapshot while "Recording" is alive.
        self.section.soft_delete(None)
        self.assertIsNone(Section.objects.filter(title="Recording").first())
        self.assertTrue(Section.all_objects.get(pk=self.section.pk).is_trashed)

        summary = import_archive(io.BytesIO(archive))

        self.assertNotIn("dry_run", summary)
        section = Section.objects.get(title="Recording")
        self.assertEqual(section.pk, self.section.pk)  # same row, restored
        self.assertFalse(section.is_trashed)
        self.assertIsNone(section.deleted_at)
        # Not duplicated.
        self.assertEqual(Section.all_objects.filter(title="Recording").count(), 1)
        self.assertEqual(summary["updated"].get("sections", 0), 1)

    def test_import_restores_trashed_product_and_resource(self):
        # Same guarantee for Product (title) and Resource (inventory_number),
        # both listed in I1/I2 as affected soft-delete models.
        import io

        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        self.product.soft_delete(None)
        self.r1.soft_delete(None)
        self.assertTrue(Product.all_objects.get(pk=self.product.pk).is_trashed)
        self.assertTrue(Resource.all_objects.get(pk=self.r1.pk).is_trashed)

        summary = import_archive(io.BytesIO(archive))

        product = Product.objects.get(title="Alpha 7")
        self.assertEqual(product.pk, self.product.pk)
        self.assertFalse(product.is_trashed)
        resource = Resource.objects.get(inventory_number="DL-1")
        self.assertEqual(resource.pk, self.r1.pk)
        self.assertFalse(resource.is_trashed)
        # p2/second resource were never trashed, so they also count as
        # "updated" (plain re-import) — just confirm nothing was miscounted
        # as a fresh "created" row (which would mean a duplicate was made).
        self.assertNotIn("products", summary["created"])
        self.assertNotIn("resources", summary["created"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TransferOldArchiveTests(TestCase):
    """Importing a pre-#20 archive (flat ``categories`` with ``title``, sections
    listing ``categories``): its categories become top-level categories (#78)."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def _png(color):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
        return buffer.getvalue()

    def _archive(self):
        import json
        import zipfile

        def ptype(name, de=""):
            return {"name": name, "attribute_schema": [], "name_de": name, "name_en": name,
                    "description_de": de, "description_en": ""}

        def product(title, type_name):
            return {"title": title, "product_type": type_name, "lending_type": "days",
                    "attributes": {}, "images": [], "title_de": title, "title_en": title}

        def category(title, position, products, order=(), image=None, de="", en=""):
            return {"title": title, "position": position, "products": list(products),
                    "product_order": list(order), "image": image,
                    "title_de": title, "title_en": title,
                    "description_de": de, "description_en": en}

        manifest = {
            "format": "ausleihbar-transfer", "version": 1, "scope": "full",
            "product_types": [
                ptype("Camera"), ptype("Microphone", de="Vorhanden"),
                ptype("Tripod"), ptype("Unused"),
            ],
            "products": [
                product("Alpha", "Camera"), product("GoPro", "Camera"),
                product("Rode", "Microphone"), product("Manfrotto", "Tripod"),
            ],
            "categories": [
                category("Cams", 1, ["Alpha", "GoPro"], order=["GoPro", "Alpha"],
                         image="media/categories/cams.png", de="Kameras", en="Cameras"),
                category("Audio & Stands", 0, ["Rode", "Manfrotto"],
                         image="media/categories/mixed.png", de="Gemischt"),
                category("Mics", 2, ["Rode"], de="Mikros", en="Microphones"),
                category("Orphan", 3, ["Manfrotto"]),
            ],
            "product_sets": [],
            "sections": [
                {"title": "Audio", "position": 1, "image": None, "categories": ["Mics"],
                 "category_order": [], "sets": [], "set_order": [],
                 "title_de": "Audio", "title_en": "Audio"},
                {"title": "Recording", "position": 0, "image": None,
                 "categories": ["Cams", "Audio & Stands"],
                 "category_order": ["Audio & Stands", "Cams"], "sets": [], "set_order": [],
                 "title_de": "Recording", "title_en": "Recording"},
            ],
            "resource_pools": [], "resources": [],
        }
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("media/categories/cams.png", self._png((1, 2, 3)))
            zf.writestr("media/categories/mixed.png", self._png((4, 5, 6)))
        out.seek(0)
        return out

    def test_old_archive_categories_become_top_level_categories(self):
        from catalog.transfer import import_archive

        summary = import_archive(self._archive())

        self.assertEqual(summary["converted"], {"categories": 4})
        self.assertEqual(summary["created"]["categories"], 4)

        cams = Category.objects.get(name="Cams")
        mixed = Category.objects.get(name="Audio & Stands")
        mics = Category.objects.get(name="Mics")
        orphan = Category.objects.get(name="Orphan")
        self.assertFalse(Category.objects.filter(parent__isnull=False).exists())
        self.assertEqual(
            [c.position for c in (cams, mixed, mics, orphan)], [1, 0, 2, 3]
        )
        self.assertEqual((cams.name_de, cams.name_en), ("Cams", "Cams"))
        self.assertEqual((cams.description_de, cams.description_en), ("Kameras", "Cameras"))
        with cams.image.open("rb") as fh:
            self.assertEqual(fh.read(), self._png((1, 2, 3)))
        self.assertFalse(mics.image)
        alpha, gopro = Product.objects.get(title="Alpha"), Product.objects.get(title="GoPro")
        self.assertEqual(set(cams.products.all()), {alpha, gopro})
        self.assertEqual(cams.product_order, [gopro.id, alpha.id])
        self.assertEqual(
            set(mixed.products.values_list("title", flat=True)), {"Rode", "Manfrotto"}
        )
        self.assertEqual(list(orphan.products.values_list("title", flat=True)), ["Manfrotto"])

        recording = Section.objects.get(title="Recording")
        self.assertEqual(set(recording.categories.all()), {cams, mixed})
        self.assertEqual(recording.category_order, [mixed.id, cams.id])
        audio = Section.objects.get(title="Audio")
        self.assertEqual(list(audio.categories.all()), [mics])

        # Product types stay attribute templates: nothing is copied onto them.
        self.assertEqual(ProductType.objects.get(name="Microphone").description_de, "Vorhanden")
        self.assertEqual(ProductType.objects.get(name="Camera").description_de, "")

    def test_old_archive_reimport_is_idempotent(self):
        from catalog.transfer import import_archive

        import_archive(self._archive())
        summary = import_archive(self._archive())
        self.assertNotIn("categories", summary["created"])
        self.assertEqual(summary["updated"]["categories"], 4)
        self.assertEqual(Category.all_objects.count(), 4)

    def test_old_archive_dry_run_changes_nothing(self):
        from catalog.transfer import import_archive

        summary = import_archive(self._archive(), dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["converted"], {"categories": 4})
        self.assertFalse(Category.all_objects.exists())
        self.assertFalse(ProductType.objects.exists())
        self.assertFalse(Section.objects.exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TransferTypeNavigationArchiveTests(TestCase):
    """Importing an ADR-0010-era archive (sections listing ``product_types``,
    types with image/position/product order): every type in a section becomes
    a top-level category, like data migration 0052 (#78)."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def _png():
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (9, 8, 7)).save(buffer, format="PNG")
        return buffer.getvalue()

    def _manifest(self):
        def ptype(name, position, order=(), image=None, en=""):
            return {"name": name, "attribute_schema": [], "name_de": name,
                    "name_en": name + " EN", "description_de": "",
                    "description_en": en, "image": image, "position": position,
                    "product_order": list(order)}

        def product(title, type_name):
            return {"title": title, "product_type": type_name, "lending_type": "days",
                    "attributes": {}, "images": [], "title_de": title, "title_en": title}

        def section(title, position, types, order):
            return {"title": title, "position": position, "image": None,
                    "product_types": types, "product_type_order": order,
                    "sets": [], "set_order": [], "title_de": title, "title_en": title}

        return {
            "format": "ausleihbar-transfer", "version": 1, "scope": "full",
            "product_types": [
                ptype("Camera", 1, order=["GoPro", "Alpha"],
                      image="media/product_types/cam.png", en="Cameras"),
                ptype("Microphone", 0), ptype("Tripod", 2), ptype("Unused", 3),
            ],
            "products": [
                product("Alpha", "Camera"), product("GoPro", "Camera"),
                product("Rode", "Microphone"), product("Manfrotto", "Tripod"),
                product("Spare", "Unused"),
            ],
            "product_sets": [],
            "sections": [
                # Tripod is in the section but not in its order: appended.
                section("Recording", 0, ["Camera", "Microphone", "Tripod"],
                        ["Microphone", "Camera"]),
                section("Audio", 1, ["Microphone"], ["Microphone"]),
            ],
            "resource_pools": [], "resources": [],
        }

    def _archive(self, manifest=None):
        import json
        import zipfile

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest or self._manifest()))
            zf.writestr("media/product_types/cam.png", self._png())
        out.seek(0)
        return out

    def test_types_in_sections_become_categories(self):
        from catalog.transfer import import_archive

        summary = import_archive(self._archive())

        self.assertEqual(summary["converted"], {"product_types": 3})
        self.assertEqual(summary["created"]["categories"], 3)
        self.assertFalse(Category.all_objects.filter(name_de="Unused").exists())
        camera = Category.objects.get(name_de="Camera")
        mic = Category.objects.get(name_de="Microphone")
        tripod = Category.objects.get(name_de="Tripod")
        self.assertIsNone(camera.parent)
        self.assertEqual((camera.position, mic.position, tripod.position), (1, 0, 2))
        self.assertEqual((camera.name_en, camera.description_en), ("Camera EN", "Cameras"))
        with camera.image.open("rb") as fh:
            self.assertEqual(fh.read(), self._png())
        alpha, gopro = Product.objects.get(title="Alpha"), Product.objects.get(title="GoPro")
        self.assertEqual(set(camera.products.all()), {alpha, gopro})
        self.assertEqual(camera.product_order, [gopro.id, alpha.id])
        self.assertEqual(list(tripod.products.values_list("title", flat=True)), ["Manfrotto"])

        recording = Section.objects.get(title="Recording")
        self.assertEqual(set(recording.categories.all()), {camera, mic, tripod})
        self.assertEqual(recording.category_order, [mic.id, camera.id, tripod.id])
        self.assertEqual(Section.objects.get(title="Audio").category_order, [mic.id])
        # The archive's type navigation lands on categories only.
        self.assertTrue(ProductType.objects.filter(name_de="Camera").exists())

    def test_existing_category_is_reused_and_reimport_is_idempotent(self):
        from catalog.transfer import import_archive

        existing = Category.objects.create(name="Camera", position=9)
        import_archive(self._archive())
        summary = import_archive(self._archive())

        self.assertNotIn("categories", summary["created"])
        self.assertEqual(summary["updated"]["categories"], 3)
        self.assertEqual(Category.all_objects.filter(name_de="Camera").get().pk, existing.pk)
        # An existing category keeps its position (like migration 0052).
        self.assertEqual(Category.objects.get(pk=existing.pk).position, 9)
        self.assertEqual(Category.objects.get(name_de="Tripod").position, 2)
        self.assertEqual(Category.all_objects.count(), 3)

    def test_pool_archive_of_that_era_converts_nothing(self):
        from catalog.transfer import import_archive

        manifest = self._manifest()
        manifest["scope"] = "pool"
        manifest["sections"] = []
        for row in manifest["product_types"]:
            row.pop("position")
            row.pop("product_order")
        summary = import_archive(self._archive(manifest))

        self.assertEqual(summary["converted"], {})
        self.assertFalse(Category.objects.exists())
        self.assertTrue(Product.objects.filter(title="Alpha").exists())

    def test_dry_run_changes_nothing(self):
        from catalog.transfer import import_archive

        summary = import_archive(self._archive(), dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["converted"], {"product_types": 3})
        self.assertFalse(Category.all_objects.exists())
        self.assertEqual(summary["media"], 1)


class SeedDemoTests(TestCase):
    """``seed_demo`` builds sections and categories and is idempotent."""

    def test_seed_creates_section_types_and_is_idempotent(self):
        from catalog.models import Category

        out = io.StringIO()
        call_command("seed_demo", stdout=out)
        call_command("seed_demo", stdout=out)
        section = Section.objects.get(title="Recording Technology")
        self.assertEqual(
            set(ProductType.objects.values_list("name", flat=True)), {"Camera", "Room"}
        )
        self.assertEqual(Product.objects.filter(title="Sony Alpha 7 IV").count(), 1)
        # Shop navigation (#78): one top-level category per demo group.
        names = [
            Category.objects.get(pk=pk).name for pk in section.category_order
        ]
        self.assertEqual(names, ["Cameras", "Rooms"])
        self.assertEqual(
            Product.objects.get(title="Podcast Room").categories.get().name, "Rooms"
        )
        self.assertEqual(Category.objects.filter(name="Cameras").count(), 1)


class FavoritesApiTests(APITestCase):
    """Borrower favorites: add from a product, list, remove, is_favorite flag."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera-fav")
        self.product = Product.objects.create(product_type=pt, title="Alpha-fav")
        # A resource in an open pool makes the product visible/eligible.
        pool = ResourcePool.objects.create(name="FavPool", pool_id="favpool")
        Resource.objects.create(
            product=self.product,
            resource_pool=pool,
            inventory_number="FAV-001",
            qr_code_id="QR-FAV-001",
        )

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/favorites/").status_code, 403)

    def test_add_list_and_remove(self):
        self.client.force_login(self.user)
        # Add
        res = self.client.post(
            "/api/favorites/", {"product": self.product.id}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        # Idempotent
        self.assertEqual(
            self.client.post(
                "/api/favorites/", {"product": self.product.id}, format="json"
            ).status_code,
            201,
        )
        # List
        listing = self.client.get("/api/favorites/")
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(listing.data[0]["id"], self.product.id)
        # is_favorite on the product detail
        detail = self.client.get(f"/api/products/{self.product.id}/")
        self.assertTrue(detail.data["is_favorite"])
        # Remove
        self.assertEqual(
            self.client.delete(f"/api/favorites/{self.product.id}/").status_code, 204
        )
        self.assertEqual(len(self.client.get("/api/favorites/").data), 0)

    def test_is_favorite_false_for_anonymous(self):
        detail = self.client.get(f"/api/products/{self.product.id}/")
        self.assertFalse(detail.data["is_favorite"])


class PdfExtractTests(SimpleTestCase):
    def test_garbage_bytes_raise_pdf_text_error(self):
        with self.assertRaises(PdfTextError):
            extract_pdf_text(io.BytesIO(b"this is not a pdf"))

    def test_blank_pdf_has_no_text(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        with self.assertRaises(PdfTextError):
            extract_pdf_text(buf)

    def test_extracts_and_normalises_page_text(self):
        page1 = MagicMock()
        page1.extract_text.return_value = "Canon   EOS\nR6"
        page2 = MagicMock()
        page2.extract_text.return_value = "  20 MP  "
        reader = MagicMock()
        reader.pages = [page1, page2]
        with patch("pypdf.PdfReader", return_value=reader):
            text = extract_pdf_text(io.BytesIO(b"%PDF-1.4"))
        self.assertEqual(text, "Canon EOS R6 20 MP")

    def test_caps_at_max_chars(self):
        page = MagicMock()
        page.extract_text.return_value = "x" * 100
        reader = MagicMock()
        reader.pages = [page]
        with patch("pypdf.PdfReader", return_value=reader):
            text = extract_pdf_text(io.BytesIO(b"%PDF-1.4"), max_chars=10)
        self.assertEqual(len(text), 10)


class ExtractFromPdfTests(APITestCase):
    """AI feature 2: pre-fill product fields from an uploaded PDF manual."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="extractadmin", is_staff=True, is_superuser=True
        )
        self.pt = ProductType.objects.create(
            name="Camera-extract",
            attribute_schema=[
                {"key": "resolution", "label": {"de": "Auflösung", "en": "Resolution"},
                 "type": "short_text", "default": "", "visible": True, "required": False},
                {"key": "weight", "label": {"de": "Gewicht", "en": "Weight"},
                 "type": "number", "default": "", "visible": True, "required": False},
            ],
        )
        self.url = "/api/manage/products/extract-from-pdf/"

    def _pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile("m.pdf", b"%PDF-1.4 dummy", content_type="application/pdf")

    def _post(self):
        return self.client.post(
            self.url,
            {"product_type": self.pt.id, "file": self._pdf()},
            format="multipart",
        )

    @override_settings(AI_PROVIDER="none")
    def test_503_when_disabled(self):
        self.client.force_login(self.admin)
        self.assertEqual(self._post().status_code, 503)

    @override_settings(**_AI_ON)
    def test_400_when_no_file(self):
        self.client.force_login(self.admin)
        res = self.client.post(self.url, {"product_type": self.pt.id}, format="multipart")
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_404_unknown_product_type(self):
        self.client.force_login(self.admin)
        res = self.client.post(
            self.url,
            {"product_type": 99999, "file": self._pdf()},
            format="multipart",
        )
        self.assertEqual(res.status_code, 404)

    @override_settings(**_AI_ON)
    def test_422_when_no_text(self):
        self.client.force_login(self.admin)
        with patch("catalog.views.extract_pdf_text", side_effect=PdfTextError("x")):
            self.assertEqual(self._post().status_code, 422)

    @override_settings(**_AI_ON)
    def test_502_on_ai_error(self):
        from basicbar_integrations.ai import AIError
        self.client.force_login(self.admin)
        with patch("catalog.views.extract_pdf_text", return_value="some text"), \
             patch("catalog.views.ai.chat_json", side_effect=AIError("boom")):
            self.assertEqual(self._post().status_code, 502)

    @override_settings(**_AI_ON)
    def test_200_normalises_and_drops_unknown_keys(self):
        self.client.force_login(self.admin)
        reply = {
            "title": {"de": "Canon EOS R6", "en": "Canon EOS R6"},
            "description": {"de": "Kamera.", "en": "Camera."},
            "attributes": {
                "resolution": "20 MP",
                "weight": "680",          # number type -> coerced
                "bogus": "ignored",       # not in schema -> dropped
            },
        }
        with patch("catalog.views.extract_pdf_text", return_value="some text"), \
             patch("catalog.views.ai.chat_json", return_value=reply):
            res = self._post()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["title"], {"de": "Canon EOS R6", "en": "Canon EOS R6"})
        # #98: the description is rich HTML for the editor.
        self.assertEqual(body["description"], {"de": "<p>Kamera.</p>", "en": "<p>Camera.</p>"})
        self.assertEqual(body["attributes"]["resolution"], {"de": "20 MP", "en": ""})
        self.assertEqual(body["attributes"]["weight"], 680)
        self.assertNotIn("bogus", body["attributes"])

    @override_settings(**_AI_ON)
    def test_400_when_pdf_too_large(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.admin)
        big = SimpleUploadedFile(
            "big.pdf",
            b"%PDF-1.4" + b"0" * (20 * 1024 * 1024 + 1),
            content_type="application/pdf",
        )
        res = self.client.post(
            self.url,
            {"product_type": self.pt.id, "file": big},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_400_when_not_a_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.admin)
        txt = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        res = self.client.post(
            self.url,
            {"product_type": self.pt.id, "file": txt},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_200_drops_unparseable_numbers_and_empty_values(self):
        self.client.force_login(self.admin)
        reply = {
            "title": {"de": "T", "en": "T"},
            "description": {"de": "D", "en": "D"},
            "attributes": {"weight": "n/a", "resolution": ""},
        }
        with patch("catalog.views.extract_pdf_text", return_value="text"), \
             patch("catalog.views.ai.chat_json", return_value=reply):
            res = self._post()
        self.assertEqual(res.status_code, 200)
        attributes = res.json()["attributes"]
        self.assertNotIn("weight", attributes)
        self.assertNotIn("resolution", attributes)


class ExtractFromPdfBilingualTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "extbi", "e2@x.de", "pw", is_staff=True, is_superuser=True,
        )
        self.pt = ProductType.objects.create(
            name="Cam",
            attribute_schema=[
                {"key": "material", "type": "short_text", "label": "Material",
                 "default": "", "visible": True, "required": False},
                {"key": "weight", "type": "number", "label": "Weight",
                 "default": "", "visible": True, "required": False},
            ],
        )
        self.url = "/api/manage/products/extract-from-pdf/"

    def _extract(self, reply):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.admin)
        with patch("catalog.views.extract_pdf_text", return_value="text"), \
             patch("catalog.views.ai.chat_json", return_value=reply):
            return self.client.post(
                self.url,
                {"product_type": self.pt.id, "file": SimpleUploadedFile(
                    "m.pdf", b"%PDF-1.4", content_type="application/pdf")},
                format="multipart",
            )

    @override_settings(**_AI_ON)
    def test_short_description_returned_and_truncated(self):
        reply = {"title": {"de": "K", "en": "C"}, "description": {"de": "d", "en": "d"},
                 "short_description": {"de": "Kurz", "en": "x" * 250}, "attributes": {}}
        res = self._extract(reply)
        self.assertEqual(res.status_code, 200)
        short = res.json()["short_description"]
        self.assertEqual(short["de"], "Kurz")
        self.assertEqual(len(short["en"]), 200)

    @override_settings(**_AI_ON)
    def test_short_description_missing_is_empty(self):
        res = self._extract({"title": {}, "description": {}, "attributes": {}})
        self.assertEqual(res.json()["short_description"], {"de": "", "en": ""})

    @override_settings(**_AI_ON)
    def test_description_plain_text_becomes_escaped_html(self):
        reply = {"title": {"de": "K", "en": "C"},
                 "description": {"de": "Satz <b> & mehr\n\nZweiter", "en": ""},
                 "attributes": {}}
        res = self._extract(reply)
        self.assertEqual(res.json()["description"], {
            "de": "<p>Satz &lt;b&gt; &amp; mehr</p><p>Zweiter</p>", "en": "",
        })

    @override_settings(**_AI_ON)
    def test_description_html_reply_is_sanitized(self):
        reply = {"title": {}, "attributes": {},
                 "description": {"de": "<p>Ok</p><script>x()</script>", "en": "<ul><li>A</li></ul>"}}
        res = self._extract(reply)
        self.assertEqual(res.json()["description"], {"de": "<p>Ok</p>", "en": "<ul><li>A</li></ul>"})

    def test_prompt_asks_for_short_description(self):
        from catalog.ai_prompts import build_product_extraction_prompt
        system, _ = build_product_extraction_prompt(self.pt, "text")
        self.assertIn("short_description", system)
        self.assertIn("200", system)

    @override_settings(**_AI_ON)
    def test_free_text_attribute_returned_bilingual(self):
        self.client.force_login(self.admin)
        reply = {"title": {"de": "K", "en": "C"}, "description": {"de": "d", "en": "d"},
                 "attributes": {"material": {"de": "Aluminium", "en": "Aluminum"}, "weight": "680"}}
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch("catalog.views.extract_pdf_text", return_value="text"), \
             patch("catalog.views.ai.chat_json", return_value=reply):
            res = self.client.post(
                self.url,
                {"product_type": self.pt.id, "file": SimpleUploadedFile(
                    "m.pdf", b"%PDF-1.4", content_type="application/pdf")},
                format="multipart",
            )
        self.assertEqual(res.status_code, 200)
        attrs = res.json()["attributes"]
        self.assertEqual(attrs["material"], {"de": "Aluminium", "en": "Aluminum"})
        self.assertEqual(attrs["weight"], 680)   # number still coerced

    @override_settings(**_AI_ON)
    def test_free_text_from_plain_string_wrapped(self):
        self.client.force_login(self.admin)
        reply = {"title": {}, "description": {}, "attributes": {"material": "Aluminium"}}
        from django.core.files.uploadedfile import SimpleUploadedFile
        with patch("catalog.views.extract_pdf_text", return_value="text"), \
             patch("catalog.views.ai.chat_json", return_value=reply):
            res = self.client.post(
                self.url,
                {"product_type": self.pt.id, "file": SimpleUploadedFile(
                    "m.pdf", b"%PDF-1.4", content_type="application/pdf")},
                format="multipart",
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["attributes"]["material"], {"de": "Aluminium", "en": ""})


class BilingualAttrMigrationTests(TestCase):
    def test_forwards_wraps_only_text_values_and_is_idempotent(self):
        import importlib
        from django.apps import apps
        module = importlib.import_module(
            "catalog.migrations.0037_bilingual_attr_values"
        )
        pt = ProductType.objects.create(
            name="Cam",
            attribute_schema=[
                {"key": "material", "type": "short_text", "label": "Material",
                 "default": "", "visible": True, "required": False},
                {"key": "weight", "type": "number", "label": "Weight",
                 "default": "", "visible": True, "required": False},
            ],
        )
        p = Product.objects.create(
            title="Old", product_type=pt, lending_type="days",
            attributes={"material": "Aluminium", "weight": 680},
        )
        module.forwards(apps, None)
        p.refresh_from_db()
        self.assertEqual(p.attributes["material"], {"de": "Aluminium", "en": ""})
        self.assertEqual(p.attributes["weight"], 680)
        # idempotent: running again leaves the dict unchanged
        module.forwards(apps, None)
        p.refresh_from_db()
        self.assertEqual(p.attributes["material"], {"de": "Aluminium", "en": ""})


class TransferAttrNormaliseTests(TestCase):
    def test_import_wraps_text_attribute_values(self):
        from catalog.transfer import _normalise_import_attributes
        schema = [
            {"key": "material", "type": "short_text", "label": "M", "default": "",
             "visible": True, "required": False},
            {"key": "weight", "type": "number", "label": "W", "default": "",
             "visible": True, "required": False},
        ]
        out = _normalise_import_attributes({"material": "Alu", "weight": 680, "extra": "x"}, schema)
        self.assertEqual(out["material"], {"de": "Alu", "en": ""})
        self.assertEqual(out["weight"], 680)
        self.assertEqual(out["extra"], "x")   # unknown key passes through


class ManageOnlyGapConditionExposureTests(TestCase):
    """min_gap/missing_notice_lead and condition_rating/condition_note (#48, #49)
    must be exposed on manage APIs only, never on borrower-facing serializers."""

    def test_manage_resource_serializer_exposes_condition(self):
        from catalog.serializers import ResourceManageSerializer
        self.assertIn("condition_rating", ResourceManageSerializer().fields)
        self.assertIn("condition_note", ResourceManageSerializer().fields)

    def test_condition_not_in_borrower_booking_serializer(self):
        from lending.serializers import BookingItemSerializer
        fields = set(BookingItemSerializer().fields)
        self.assertNotIn("condition_rating", fields)
        self.assertNotIn("condition_note", fields)


class SoftDeleteTests(TestCase):
    def test_soft_delete_hides_from_default_manager(self):
        c = Section.objects.create(title="Temp")
        c.soft_delete()
        self.assertFalse(Section.objects.filter(pk=c.pk).exists())      # hidden
        self.assertTrue(Section.all_objects.filter(pk=c.pk).exists())   # still there
        self.assertIsNotNone(Section.all_objects.get(pk=c.pk).deleted_at)

    def test_restore_makes_it_visible_again(self):
        c = Section.objects.create(title="Temp")
        c.soft_delete()
        Section.all_objects.get(pk=c.pk).restore()
        self.assertTrue(Section.objects.filter(pk=c.pk).exists())

    def test_relation_excludes_trashed_children(self):
        # A pool's `resources` (default manager) must not count a trashed resource.
        pt = ProductType.objects.create(name="SoftDelete-Type")
        product = Product.objects.create(product_type=pt, title="SoftDelete-Product")
        pool = ResourcePool.objects.create(name="SoftDelete-Pool", pool_id="SD-POOL")
        resource = Resource.objects.create(
            product=product,
            resource_pool=pool,
            inventory_number="SD-001",
            qr_code_id="QR-SD-001",
        )
        self.assertEqual(pool.resources.count(), 1)
        resource.soft_delete()
        self.assertEqual(pool.resources.count(), 0)
        self.assertEqual(pool.resources(manager="all_objects").count(), 1)

    def test_soft_delete_records_deleted_by(self):
        user = User.objects.create_user(username="deleter", password="x")
        c = Section.objects.create(title="Temp2")
        c.soft_delete(user=user)
        trashed = Section.all_objects.get(pk=c.pk)
        self.assertEqual(trashed.deleted_by, user)
        self.assertTrue(trashed.is_trashed)

    def test_restore_clears_deleted_by(self):
        user = User.objects.create_user(username="deleter2", password="x")
        c = Section.objects.create(title="Temp3")
        c.soft_delete(user=user)
        restored = Section.all_objects.get(pk=c.pk)
        restored.restore()
        self.assertIsNone(restored.deleted_by)
        self.assertFalse(restored.is_trashed)


class ManageSoftDeleteEndpointTests(APITestCase):
    """The manage `destroy` endpoints soft-delete instead of hard-deleting.
    A resource with ANY booking history (active or past) is blocked from
    trashing — it must be retired instead — so a trashed resource never has
    `BookingItem`s and `purge_trash` can always hard-delete it safely."""

    def setUp(self):
        from datetime import timedelta

        from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
        from django.utils import timezone

        from lending.models import Booking, BookingItem

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")

        self.empty_pool = ResourcePool.objects.create(
            name="Empty Pool", pool_id="EmptyPool"
        )
        self.pool_with_resource = ResourcePool.objects.create(
            name="Occupied Pool", pool_id="OccupiedPool"
        )

        pt = ProductType.objects.create(name="Camera-SD")
        product = Product.objects.create(product_type=pt, title="GoPro-SD")

        self.unbooked_resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool_with_resource,
            inventory_number="OccupiedPool-001",
            qr_code_id="QR-OccupiedPool-001",
        )

        self.booked_resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool_with_resource,
            inventory_number="OccupiedPool-002",
            qr_code_id="QR-OccupiedPool-002",
        )
        booked = Booking.objects.create(
            borrower=self.borrower, status=Booking.Status.CONFIRMED
        )
        BookingItem.objects.create(
            booking=booked,
            resource=self.booked_resource,
            period=DateTimeTZRange(
                timezone.now() + timedelta(days=1),
                timezone.now() + timedelta(days=2),
            ),
        )

        self.returned_resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool_with_resource,
            inventory_number="OccupiedPool-003",
            qr_code_id="QR-OccupiedPool-003",
        )
        history_only = Booking.objects.create(
            borrower=self.borrower, status=Booking.Status.RETURNED
        )
        BookingItem.objects.create(
            booking=history_only,
            resource=self.returned_resource,
            period=DateTimeTZRange(
                timezone.now() - timedelta(days=5),
                timezone.now() - timedelta(days=4),
            ),
            handed_out_at=timezone.now() - timedelta(days=5),
            returned_at=timezone.now() - timedelta(days=4),
            is_active=False,
        )

        self.client.force_login(self.admin)

    def test_delete_pool_soft_deletes(self):
        resp = self.client.delete(f"/api/manage/pools/{self.empty_pool.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ResourcePool.objects.filter(pk=self.empty_pool.id).exists())
        self.assertTrue(ResourcePool.all_objects.filter(pk=self.empty_pool.id).exists())

    def test_delete_pool_with_resources_blocked(self):
        resp = self.client.delete(f"/api/manage/pools/{self.pool_with_resource.id}/")
        self.assertEqual(resp.status_code, 400)

    def test_delete_resource_with_active_booking_blocked(self):
        resp = self.client.delete(f"/api/manage/inventory/{self.booked_resource.id}/")
        self.assertEqual(resp.status_code, 400)

    def test_delete_resource_with_only_history_blocked(self):
        # Even past-only booking history blocks trashing (must retire
        # instead) — this guarantees purge_trash never hits a resource that
        # BookingItem.resource (PROTECT) still points to.
        resp = self.client.delete(f"/api/manage/inventory/{self.returned_resource.id}/")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(
            Resource.all_objects.get(pk=self.returned_resource.id).is_trashed
        )

    def test_delete_resource_without_bookings_soft_deletes(self):
        resp = self.client.delete(f"/api/manage/inventory/{self.unbooked_resource.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertTrue(
            Resource.all_objects.get(pk=self.unbooked_resource.id).is_trashed
        )

    def test_delete_product_type_soft_deletes(self):
        pt = ProductType.objects.create(name="Empty-Type-SD")
        resp = self.client.delete(f"/api/manage/product-types/{pt.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ProductType.objects.filter(pk=pt.id).exists())
        self.assertTrue(ProductType.all_objects.filter(pk=pt.id).exists())

    def test_delete_product_soft_deletes(self):
        pt = ProductType.objects.create(name="Product-Type-SD")
        product = Product.objects.create(product_type=pt, title="Empty-Product-SD")
        resp = self.client.delete(f"/api/manage/products/{product.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Product.objects.filter(pk=product.id).exists())
        self.assertTrue(Product.all_objects.filter(pk=product.id).exists())

    def test_delete_section_soft_deletes(self):
        section = Section.objects.create(title="Section-SD")
        resp = self.client.delete(f"/api/manage/sections/{section.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Section.objects.filter(pk=section.id).exists())
        self.assertTrue(Section.all_objects.filter(pk=section.id).exists())

    def test_delete_product_set_soft_deletes(self):
        from catalog.models import ProductSet

        pset = ProductSet.objects.create(
            name="Set-SD", resource_pool=self.empty_pool
        )
        resp = self.client.delete(f"/api/manage/product-sets/{pset.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ProductSet.objects.filter(pk=pset.id).exists())
        self.assertTrue(ProductSet.all_objects.filter(pk=pset.id).exists())


class TrashApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(username="alice")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        self.client.force_login(self.admin)

    def test_list_returns_trashed_items(self):
        c = Section.objects.create(title="Gone")
        c.soft_delete(self.admin)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertTrue(
            any(r["type"] == "section" and r["id"] == c.id for r in rows)
        )

    def test_restore_brings_it_back(self):
        c = Section.objects.create(title="Gone")
        c.soft_delete(self.admin)
        resp = self.client.post(f"/api/manage/trash/section/{c.id}/restore/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Section.objects.filter(pk=c.id).exists())

    def test_purge_one_hard_deletes(self):
        c = Section.objects.create(title="Gone")
        c.soft_delete(self.admin)
        resp = self.client.delete(f"/api/manage/trash/section/{c.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Section.all_objects.filter(pk=c.id).exists())

    def test_lender_cannot_see_admin_only_types(self):
        self.client.force_login(self.lender)
        s = Section.objects.create(title="X")
        s.soft_delete(self.admin)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertFalse(any(r["type"] == "section" for r in rows))

    def test_borrower_forbidden(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/trash/").status_code, 403)

    def test_lender_sees_trashed_resource_in_own_pool(self):
        product_type = ProductType.objects.create(name="Trash-Type")
        product = Product.objects.create(product_type=product_type, title="Trash-Product")
        resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number="TR-001",
            qr_code_id="QR-TR-001",
        )
        resource.soft_delete(self.admin)
        self.client.force_login(self.lender)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertTrue(
            any(r["type"] == "resource" and r["id"] == resource.id for r in rows)
        )

    def test_lender_cannot_see_resource_in_other_pool(self):
        other_pool = ResourcePool.objects.create(name="Other", pool_id="Other")
        product_type = ProductType.objects.create(name="Trash-Type2")
        product = Product.objects.create(product_type=product_type, title="Trash-Product2")
        resource = Resource.objects.create(
            product=product,
            resource_pool=other_pool,
            inventory_number="TR-002",
            qr_code_id="QR-TR-002",
        )
        resource.soft_delete(self.admin)
        self.client.force_login(self.lender)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertFalse(any(r["type"] == "resource" for r in rows))

    def test_unknown_type_restore_returns_404(self):
        resp = self.client.post("/api/manage/trash/bogus/1/restore/")
        self.assertEqual(resp.status_code, 404)

    def test_purge_missing_item_returns_404(self):
        resp = self.client.delete("/api/manage/trash/section/999999/")
        self.assertEqual(resp.status_code, 404)

    def test_empty_trash_purges_everything_caller_may_manage(self):
        c1 = Section.objects.create(title="Gone1")
        c1.soft_delete(self.admin)
        c2 = Section.objects.create(title="Gone2")
        c2.soft_delete(self.admin)
        resp = self.client.delete("/api/manage/trash/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Section.all_objects.filter(pk__in=[c1.id, c2.id]).exists())

    def test_purge_at_reflects_retention_days(self):
        from catalog.models import TrashSetting

        TrashSetting.load()
        setting = TrashSetting.objects.get(pk=1)
        setting.retention_days = 5
        setting.save()
        c = Section.objects.create(title="Gone")
        c.soft_delete(self.admin)
        rows = self.client.get("/api/manage/trash/").json()
        row = next(r for r in rows if r["type"] == "section" and r["id"] == c.id)
        self.assertIn("purge_at", row)

    def test_empty_trash_purges_dependency_chain_in_order(self):
        # resource -> product -> product_type is a chain of PROTECT FKs; all
        # three trashed together must not trip ProtectedError on empty-trash.
        product_type = ProductType.objects.create(name="Chain-Type")
        product = Product.objects.create(product_type=product_type, title="Chain-Product")
        resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number="CH-001",
            qr_code_id="QR-CH-001",
        )
        resource.soft_delete(self.admin)
        product.soft_delete(self.admin)
        product_type.soft_delete(self.admin)

        resp = self.client.delete("/api/manage/trash/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Resource.all_objects.filter(pk=resource.id).exists())
        self.assertFalse(Product.all_objects.filter(pk=product.id).exists())
        self.assertFalse(ProductType.all_objects.filter(pk=product_type.id).exists())

    def test_purge_one_blocked_by_dependent_then_succeeds_after_clearing(self):
        product_type = ProductType.objects.create(name="Blocked-Type")
        product = Product.objects.create(product_type=product_type, title="Blocked-Product")
        resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number="BL-001",
            qr_code_id="QR-BL-001",
        )
        resource.soft_delete(self.admin)
        product.soft_delete(self.admin)
        product_type.soft_delete(self.admin)

        # The trashed product still references product_type (PROTECT) -> 400.
        blocked = self.client.delete(f"/api/manage/trash/product-type/{product_type.id}/")
        self.assertEqual(blocked.status_code, 400)
        self.assertTrue(ProductType.all_objects.filter(pk=product_type.id).exists())

        # Clear dependents first, then the product-type purge succeeds.
        self.assertEqual(
            self.client.delete(f"/api/manage/trash/resource/{resource.id}/").status_code,
            204,
        )
        self.assertEqual(
            self.client.delete(f"/api/manage/trash/product/{product.id}/").status_code,
            204,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/manage/trash/product-type/{product_type.id}/"
            ).status_code,
            204,
        )

    def test_empty_trash_skips_protected_row_and_empties_the_rest(self):
        # M2: the manage endpoint normally blocks trashing a Resource with
        # booking history, so this can only happen via a legacy/out-of-band
        # row (simulated here with .update(), bypassing that guard) — empty
        # trash must not 500 on it, and must still purge everything else.
        from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

        from lending.models import Booking, BookingItem

        product_type = ProductType.objects.create(name="Protected-Type")
        product = Product.objects.create(
            product_type=product_type, title="Protected-Product"
        )
        protected_resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number="PROT-001",
            qr_code_id="QR-PROT-001",
        )
        borrower = User.objects.create_user(username="protected-borrower")
        booking = Booking.objects.create(
            borrower=borrower, status=Booking.Status.RETURNED
        )
        BookingItem.objects.create(
            booking=booking,
            resource=protected_resource,
            period=DateTimeTZRange(
                timezone.now() - timedelta(days=10),
                timezone.now() - timedelta(days=9),
            ),
            handed_out_at=timezone.now() - timedelta(days=10),
            returned_at=timezone.now() - timedelta(days=9),
            is_active=False,
        )
        # Bypass the endpoint block (.update() skips model methods) to
        # simulate a legacy row already in the trash despite booking history.
        Resource.all_objects.filter(pk=protected_resource.pk).update(
            deleted_at=timezone.now()
        )

        other = Section.objects.create(title="Emptiable")
        other.soft_delete(self.admin)

        resp = self.client.delete("/api/manage/trash/")

        self.assertEqual(resp.status_code, 204)
        # Protected row survives, still in the trash.
        self.assertTrue(
            Resource.all_objects.filter(pk=protected_resource.pk).exists()
        )
        # Everything else was still purged.
        self.assertFalse(Section.all_objects.filter(pk=other.pk).exists())

    def test_lender_restore_and_purge_forbidden_outside_managed_pool(self):
        other_pool = ResourcePool.objects.create(name="Other2", pool_id="Other2")
        product_type = ProductType.objects.create(name="Trash-Type3")
        product = Product.objects.create(product_type=product_type, title="Trash-Product3")
        resource = Resource.objects.create(
            product=product,
            resource_pool=other_pool,
            inventory_number="TR-003",
            qr_code_id="QR-TR-003",
        )
        resource.soft_delete(self.admin)
        self.client.force_login(self.lender)
        restore_resp = self.client.post(
            f"/api/manage/trash/resource/{resource.id}/restore/"
        )
        self.assertEqual(restore_resp.status_code, 404)
        delete_resp = self.client.delete(f"/api/manage/trash/resource/{resource.id}/")
        self.assertEqual(delete_resp.status_code, 404)


class UniqueCollisionWithTrashedRowTests(APITransactionTestCase):
    """I1: recreating an object with the same unique value as a TRASHED one
    must be a clean 400 (not an unhandled IntegrityError / 500) — the
    default manager `UniqueValidator` can't see the trashed row, so it's the
    DB's unique constraint that trips on `.save()`.

    Uses APITransactionTestCase (not APITestCase): APITestCase wraps the
    whole test body in one shared transaction, so a failed INSERT would mark
    that shared transaction for rollback and the *test's* follow-up query
    would itself blow up with TransactionManagementError — masking the very
    thing under test. A TransactionTestCase runs each request the same way
    production does (autocommit, no enclosing atomic), which is what
    actually proves the connection survives for the next request."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)

    def test_recreate_with_trashed_name_returns_400_not_500(self):
        pt = ProductType.objects.create(name="Camera-Trash")
        pt.soft_delete(self.admin)

        resp = self.client.post(
            "/api/manage/product-types/",
            {"name": "Camera-Trash", "attribute_schema": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("trash", resp.json().get("detail", "").lower())

        # The failed INSERT must not poison the connection for the next
        # request — a hallmark of the bug being an unhandled 500 instead of
        # a handled 400.
        follow_up = self.client.get("/api/manage/product-types/")
        self.assertEqual(follow_up.status_code, 200)


class TrashSettingApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss-ts", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice-ts")

    def test_get_returns_default(self):
        self.client.force_login(self.admin)
        resp = self.client.get("/api/manage/trash-setting/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["retention_days"], 30)

    def test_put_updates_retention_days(self):
        self.client.force_login(self.admin)
        resp = self.client.put(
            "/api/manage/trash-setting/", {"retention_days": 45}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["retention_days"], 45)
        self.assertEqual(TrashSetting.load().retention_days, 45)

    def test_borrower_forbidden(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/trash-setting/").status_code, 403)


class PurgeTrashCommandTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss-purge", is_staff=True, is_superuser=True
        )
        self.pool = ResourcePool.objects.create(name="PurgePool", pool_id="PurgePool")

    def test_purges_only_past_retention(self):
        old = Section.objects.create(title="Old")
        old.soft_delete(self.admin)
        recent = Section.objects.create(title="Recent")
        recent.soft_delete(self.admin)
        # Backdate `old` beyond the 30-day window.
        Section.all_objects.filter(pk=old.pk).update(
            deleted_at=timezone.now() - timedelta(days=31)
        )
        call_command("purge_trash")
        self.assertFalse(Section.all_objects.filter(pk=old.pk).exists())
        self.assertTrue(Section.all_objects.filter(pk=recent.pk).exists())

    def test_dry_run_writes_nothing(self):
        c = Section.objects.create(title="Old")
        c.soft_delete(self.admin)
        Section.all_objects.filter(pk=c.pk).update(
            deleted_at=timezone.now() - timedelta(days=99)
        )
        call_command("purge_trash", "--dry-run")
        self.assertTrue(Section.all_objects.filter(pk=c.pk).exists())

    def test_respects_configured_retention_days(self):
        setting = TrashSetting.load()
        setting.retention_days = 5
        setting.save()
        c = Section.objects.create(title="Custom")
        c.soft_delete(self.admin)
        Section.all_objects.filter(pk=c.pk).update(
            deleted_at=timezone.now() - timedelta(days=6)
        )
        call_command("purge_trash")
        self.assertFalse(Section.all_objects.filter(pk=c.pk).exists())

    def test_full_dependency_chain_purges_without_protected_error(self):
        product_type = ProductType.objects.create(name="Purge-Type")
        product = Product.objects.create(
            product_type=product_type, title="Purge-Product"
        )
        resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number="PG-001",
            qr_code_id="QR-PG-001",
        )
        cutoff = timezone.now() - timedelta(days=31)
        resource.soft_delete(self.admin)
        product.soft_delete(self.admin)
        product_type.soft_delete(self.admin)
        Resource.all_objects.filter(pk=resource.pk).update(deleted_at=cutoff)
        Product.all_objects.filter(pk=product.pk).update(deleted_at=cutoff)
        ProductType.all_objects.filter(pk=product_type.pk).update(deleted_at=cutoff)

        call_command("purge_trash")

        self.assertFalse(Resource.all_objects.filter(pk=resource.pk).exists())
        self.assertFalse(Product.all_objects.filter(pk=product.pk).exists())
        self.assertFalse(ProductType.all_objects.filter(pk=product_type.pk).exists())

    def test_protected_row_is_skipped_without_raising(self):
        """The manage endpoint blocks trashing a Resource with booking
        history, so this should never happen via the API — but simulate a
        legacy/edge case (bypassing the endpoint via .update()) to prove a
        single ProtectedError can't abort the whole scheduled run."""
        from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

        from lending.models import Booking, BookingItem

        product_type = ProductType.objects.create(name="Protected-Type")
        product = Product.objects.create(
            product_type=product_type, title="Protected-Product"
        )
        protected_resource = Resource.objects.create(
            product=product,
            resource_pool=self.pool,
            inventory_number="PG-PROT-001",
            qr_code_id="QR-PG-PROT-001",
        )
        borrower = User.objects.create_user(username="protected-borrower")
        booking = Booking.objects.create(
            borrower=borrower, status=Booking.Status.RETURNED
        )
        BookingItem.objects.create(
            booking=booking,
            resource=protected_resource,
            period=DateTimeTZRange(
                timezone.now() - timedelta(days=40),
                timezone.now() - timedelta(days=39),
            ),
            handed_out_at=timezone.now() - timedelta(days=40),
            returned_at=timezone.now() - timedelta(days=39),
            is_active=False,
        )
        cutoff = timezone.now() - timedelta(days=31)
        # Bypass the endpoint block (.update() skips model methods/signals)
        # to simulate a legacy row that slipped into the trash already
        # referenced by booking history.
        Resource.all_objects.filter(pk=protected_resource.pk).update(deleted_at=cutoff)

        unprotected = Section.objects.create(title="Unprotected")
        unprotected.soft_delete(self.admin)
        Section.all_objects.filter(pk=unprotected.pk).update(deleted_at=cutoff)

        # Must not raise ProtectedError.
        call_command("purge_trash")

        self.assertTrue(
            Resource.all_objects.filter(pk=protected_resource.pk).exists()
        )
        self.assertFalse(Section.all_objects.filter(pk=unprotected.pk).exists())


class ComplementaryProductTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="boss", is_staff=True, is_superuser=True)
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(username="alice")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        self.ptype = ProductType.objects.create(name="Gear", attribute_schema=[])
        self.a = Product.objects.create(title="Camera", product_type=self.ptype, lending_type="days")
        self.b = Product.objects.create(title="Tripod", product_type=self.ptype, lending_type="days")
        self.c = Product.objects.create(title="Mic", product_type=self.ptype, lending_type="days")
        for i, p in enumerate([self.a, self.b, self.c]):
            Resource.objects.create(
                product=p, resource_pool=self.pool,
                inventory_number=f"R-{i}", qr_code_id=f"QR-R-{i}",
            )

    def _set(self, product, ids, user=None):
        self.client.force_login(user or self.lender)
        return self.client.patch(
            f"/api/manage/products/{product.id}/",
            {"complementary_products": ids}, format="json",
        )

    def _complements(self, product):
        self.client.force_login(self.lender)
        return self.client.get(f"/api/manage/products/{product.id}/").data["complementary_products"]

    def test_lender_can_set_and_link_is_symmetric(self):
        res = self._set(self.a, [self.b.id])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._complements(self.a), [self.b.id])
        self.assertEqual(self._complements(self.b), [self.a.id])  # symmetric

    def test_curated_order_is_kept(self):
        self._set(self.a, [self.c.id, self.b.id])
        self.assertEqual(self._complements(self.a), [self.c.id, self.b.id])
        self._set(self.a, [self.b.id, self.c.id])
        self.assertEqual(self._complements(self.a), [self.b.id, self.c.id])

    def test_link_from_other_side_sorts_after_curated(self):
        self._set(self.a, [self.b.id])          # a: [b]
        self._set(self.c, [self.a.id])          # symmetric → a also has c, not in a's order
        self.assertEqual(self._complements(self.a), [self.b.id, self.c.id])

    def test_cannot_complement_itself(self):
        res = self._set(self.a, [self.a.id])
        self.assertEqual(res.status_code, 400)

    def test_duplicates_are_collapsed(self):
        self._set(self.a, [self.b.id, self.b.id])
        self.assertEqual(self._complements(self.a), [self.b.id])

    def test_update_without_key_leaves_complements(self):
        self._set(self.a, [self.b.id])
        self.client.force_login(self.lender)
        self.client.patch(f"/api/manage/products/{self.a.id}/", {"title": "Cam"}, format="json")
        self.assertEqual(self._complements(self.a), [self.b.id])

    def _detail(self, product, user):
        self.client.force_login(user)
        return self.client.get(f"/api/products/{product.id}/").data["complementary_products"]

    def test_borrower_sees_ordered_complements_with_pools(self):
        self.b.short_description = "Steady shots"
        self.b.save(update_fields=["short_description"])
        self._set(self.a, [self.c.id, self.b.id])
        rows = self._detail(self.a, self.borrower)
        self.assertEqual([r["id"] for r in rows], [self.c.id, self.b.id])
        self.assertEqual(rows[1]["short_description"], "Steady shots")
        self.assertEqual([p["id"] for p in rows[0]["pools"]], [self.pool.id])
        self.assertNotIn("available", rows[0])  # no availability

    def test_complement_rows_carry_thumbnail_and_type(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from .models import ProductImage

        media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=media):
                buffer = BytesIO()
                Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, format="PNG")
                ProductImage.objects.create(
                    product=self.b,
                    image=SimpleUploadedFile("tripod.png", buffer.getvalue(), content_type="image/png"),
                )
                self._set(self.a, [self.b.id, self.c.id])
                rows = self._detail(self.a, self.borrower)
                self.assertIn("tripod", rows[0]["image"])
                self.assertIsNone(rows[1]["image"])  # no gallery → emoji fallback
                self.assertEqual(rows[0]["product_type_name"], "Gear")
        finally:
            shutil.rmtree(media, ignore_errors=True)

    def test_complement_in_restricted_pool_hidden_for_non_member(self):
        from accounts.models import AccessGroup

        locked = ResourcePool.objects.create(name="Locked", pool_id="locked")
        AccessGroup.objects.create(name="Staff only").pools.add(locked)
        hidden = Product.objects.create(title="Secret", product_type=self.ptype, lending_type="days")
        Resource.objects.create(product=hidden, resource_pool=locked,
                                inventory_number="S-1", qr_code_id="QR-S-1")
        self._set(self.a, [hidden.id, self.b.id])
        ids = [r["id"] for r in self._detail(self.a, self.borrower)]
        self.assertEqual(ids, [self.b.id])

    def test_only_eligible_pools_listed(self):
        from accounts.models import AccessGroup

        locked = ResourcePool.objects.create(name="Locked", pool_id="locked")
        AccessGroup.objects.create(name="Staff only").pools.add(locked)
        Resource.objects.create(product=self.b, resource_pool=locked,
                                inventory_number="B-L", qr_code_id="QR-B-L")
        self._set(self.a, [self.b.id])
        pools = self._detail(self.a, self.borrower)[0]["pools"]
        self.assertEqual([p["id"] for p in pools], [self.pool.id])

    def test_trashed_complement_hidden(self):
        self._set(self.a, [self.b.id, self.c.id])
        self.c.soft_delete()
        ids = [r["id"] for r in self._detail(self.a, self.borrower)]
        self.assertEqual(ids, [self.b.id])

    def test_complement_with_only_retired_units_hidden(self):
        # I1: a complement with no bookable unit anywhere must follow the same
        # visibility rule as any other product (visible_products) — it's
        # currently invisible via /api/products/<id>/, so it shouldn't be
        # listed (with a pool chip) as a complement either.
        self.b.resources.update(status=Resource.Status.RETIRED)
        self._set(self.a, [self.b.id, self.c.id])
        ids = [r["id"] for r in self._detail(self.a, self.borrower)]
        self.assertEqual(ids, [self.c.id])

    def test_complement_pool_chips_are_bookable_units_only(self):
        # I1: a complement with one AVAILABLE unit in pool P and one RETIRED
        # unit in pool Q lists only P — not the non-bookable pool.
        retired_pool = ResourcePool.objects.create(name="Retired store", pool_id="retired")
        Resource.objects.create(
            product=self.b, resource_pool=retired_pool, status=Resource.Status.RETIRED,
            inventory_number="B-RET", qr_code_id="QR-B-RET",
        )
        self._set(self.a, [self.b.id])
        rows = self._detail(self.a, self.borrower)
        self.assertEqual(len(rows), 1)
        self.assertEqual([p["id"] for p in rows[0]["pools"]], [self.pool.id])

    def test_manage_representation_prefetch_and_trashed_link_survives_removal_and_restore(self):
        # Regression (M4/pins a review claim): trashing a linked complement and
        # then saving the product with the list the form would actually send
        # (which excludes it, since a trashed product isn't a selectable
        # option) must not sever the underlying link — restoring the complement
        # should make it reappear in the manage representation.
        self._set(self.a, [self.b.id])
        self.b.soft_delete()
        # What the manage GET returns for A right now (the "list the form would
        # send" back unchanged) already excludes the trashed B.
        current = self._complements(self.a)
        self.assertEqual(current, [])
        # Lender saves A (e.g. edits an unrelated field) with that list.
        res = self._set(self.a, current)
        self.assertEqual(res.status_code, 200)
        self.b.restore()
        self.assertEqual(self._complements(self.a), [self.b.id])


class PrivacyFreeTextMigrationTests(TestCase):
    """Migration 0046 extends the seeded privacy draft (#26, #38).

    By the time the test DB is built, migration 0047 (#5) has already run and
    turned the seeded page's Markdown into HTML, so the "as seeded" check
    below looks for the HTML form; the idempotent/reversible checks reset the
    page to the raw Markdown state 0046 itself produces, to exercise its own
    anchor-replace logic in isolation from 0047's later conversion.
    """

    NOTE_LINE = "**Nachricht des Verleihteams** zur Bestätigung"
    NOTE_LINE_HTML = "<strong>Nachricht des Verleihteams</strong> zur Bestätigung"
    CLAUSE_LINE = "Buchungen (Nachrichten) und die Begründungen von Verwarnungen."

    def _mod(self):
        import importlib

        return importlib.import_module("catalog.migrations.0046_privacy_free_texts")

    def _page(self):
        return Page.objects.get(slug="privacy")

    def test_seeded_page_gets_both_additions_once(self):
        body = self._page().body_de
        self.assertEqual(body.count(self.NOTE_LINE_HTML), 1)
        self.assertEqual(body.count(self.CLAUSE_LINE), 1)

    def test_idempotent_and_reversible(self):
        from django.apps import apps

        mod = self._mod()
        page = self._page()
        page.body_de = "".join(replacement for _, replacement in mod.EDITS)
        page.save()

        mod.add_free_texts(apps, None)  # second run: no duplicates
        body = self._page().body_de
        self.assertEqual(body.count(self.NOTE_LINE), 1)
        self.assertEqual(body.count(self.CLAUSE_LINE), 1)
        mod.remove_free_texts(apps, None)
        body = self._page().body_de
        self.assertNotIn(self.NOTE_LINE, body)
        self.assertNotIn(self.CLAUSE_LINE, body)
        self.assertIn("**Nachricht an das Verleihteam**", body)
        mod.add_free_texts(apps, None)
        self.assertEqual(self._page().body_de.count(self.NOTE_LINE), 1)

    def test_admin_edited_text_is_left_alone(self):
        from django.apps import apps

        page = self._page()
        page.body_de = "Eigener Text der Datenschutzstelle."
        page.save()
        self._mod().add_free_texts(apps, None)
        self.assertEqual(self._page().body_de, "Eigener Text der Datenschutzstelle.")


class RichTextHelperTests(SimpleTestCase):
    def test_markdown_to_html(self):
        from catalog.richtext import markdown_to_html

        html = markdown_to_html("## Titel\n\n**fett** und [Link](https://uni-osnabrueck.de)\n\n- a\n- b")
        self.assertIn("<h2>Titel</h2>", html)
        self.assertIn("<strong>fett</strong>", html)
        self.assertIn('href="https://uni-osnabrueck.de"', html)
        self.assertIn("<li>a</li>", html)

    def test_markdown_single_newline_becomes_space_not_br(self):
        # I3: a hard-wrapped paragraph must render like the previous
        # react-markdown client rendering — a single newline is just
        # whitespace; only a blank line starts a new paragraph.
        from catalog.richtext import markdown_to_html

        html = markdown_to_html("Zeile eins\nZeile zwei")
        self.assertNotIn("<br", html)
        self.assertEqual(html.count("<p>"), 1)
        collapsed = " ".join(html.replace("<p>", "").replace("</p>", "").split())
        self.assertEqual(collapsed, "Zeile eins Zeile zwei")

    def test_markdown_heading_remap(self):
        # I3: headings the allowlist doesn't keep (h1, h4-h6) are remapped
        # rather than stripped down to plain text.
        from catalog.richtext import markdown_to_html

        self.assertEqual(markdown_to_html("# Titel"), "<h2>Titel</h2>")
        self.assertEqual(markdown_to_html("#### Klein"), "<h3>Klein</h3>")
        self.assertEqual(markdown_to_html("##### Kleiner"), "<h3>Kleiner</h3>")
        self.assertEqual(markdown_to_html("###### Am kleinsten"), "<h3>Am kleinsten</h3>")

    def test_plain_to_html_escapes_and_breaks(self):
        from catalog.richtext import plain_to_html

        html = plain_to_html("Erdgeschoss <links>\nRaum 1\n\nZweiter Absatz")
        self.assertEqual(html, "<p>Erdgeschoss &lt;links&gt;<br>Raum 1</p><p>Zweiter Absatz</p>")

    def test_looks_like_html(self):
        from catalog.richtext import looks_like_html

        self.assertTrue(looks_like_html("<p>x</p>"))
        self.assertTrue(looks_like_html("<h2>Section</h2>"))
        self.assertFalse(looks_like_html("a < b and c > d"))
        self.assertFalse(looks_like_html("## Markdown"))

    def test_looks_like_html_ignores_inline_br_in_markdown(self):
        # M2: a Markdown source may legitimately contain an inline "<br>"
        # without becoming "HTML" — only a leading allowlisted block tag
        # (p/h2/h3/ul/ol) counts.
        from catalog.richtext import looks_like_html

        self.assertFalse(looks_like_html("Zeile eins<br>Zeile zwei"))
        self.assertFalse(looks_like_html("<br>Am Zeilenanfang"))

    def test_html_to_text(self):
        from catalog.richtext import html_to_text

        text = html_to_text(
            '<p>Eingang <strong>Nord</strong></p><ul><li>2. OG</li><li>Raum 5</li></ul>'
            '<p><a href="https://x.de/plan">Lageplan</a></p>'
        )
        self.assertEqual(text, "Eingang Nord\n- 2. OG\n- Raum 5\nLageplan (https://x.de/plan)")


class CleanRichEmptyContentTests(SimpleTestCase):
    """M1: an editor left with no visible content should store "" rather
    than markup like "<p></p>"."""

    def test_empty_paragraph_becomes_empty_string(self):
        from catalog.richtext import clean_rich

        self.assertEqual(clean_rich("<p></p>"), "")
        self.assertEqual(clean_rich("<p><br></p>"), "")
        self.assertEqual(clean_rich("<p>   </p>"), "")
        self.assertEqual(clean_rich("<p></p><p><br></p>"), "")

    def test_image_only_content_is_kept(self):
        from catalog.richtext import clean_rich

        html = clean_rich('<p><img src="/media/rich/a.png" alt=""></p>')
        self.assertIn("<img", html)

    def test_actual_text_is_kept(self):
        from catalog.richtext import clean_rich

        self.assertEqual(clean_rich("<p>ok</p>"), "<p>ok</p>")


class RichFieldSanitizeTests(APITestCase):
    """Rich-HTML fields are sanitized on save (#5) — the backend is the
    security boundary for whatever the rich-text editor sends."""

    DIRTY = '<p onclick="x()">ok</p><script>alert(1)</script><img src="https://evil.example/a.png">'
    FORMATTED = '<h2>Title</h2><p><strong>bold</strong></p><p><a href="https://uni-osnabrueck.de">link</a></p>'

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )

    def assertClean(self, value):
        self.assertIn("<p>ok</p>", value)
        self.assertNotIn("script", value)
        self.assertNotIn("onclick", value)
        self.assertNotIn("evil.example", value)

    def test_page_body_sanitized_on_save(self):
        page = Page.objects.create(slug="rt-page", title="RT", body="x")
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/manage/pages/{page.id}/",
            {"body_de": self.DIRTY, "body_en": self.FORMATTED},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        page.refresh_from_db()
        self.assertClean(page.body_de)
        self.assertIn("<strong>bold</strong>", page.body_en)
        self.assertIn("<h2>Title</h2>", page.body_en)
        self.assertIn('href="https://uni-osnabrueck.de"', page.body_en)

    def test_welcome_text_sanitized_on_save(self):
        from .models import WelcomeSetting

        self.client.force_login(self.admin)
        res = self.client.put(
            "/api/manage/welcome-setting/",
            {"text": self.DIRTY},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertClean(WelcomeSetting.load().text)

    def test_pool_description_and_directions_sanitized_on_save(self):
        pool = ResourcePool.objects.create(name="RT Pool", pool_id="RTPool")
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"/api/manage/pools/{pool.id}/",
            {"description_de": self.DIRTY, "directions_en": self.FORMATTED},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        pool.refresh_from_db()
        self.assertClean(pool.description_de)
        self.assertIn("<strong>bold</strong>", pool.directions_en)
        self.assertIn("<h2>Title</h2>", pool.directions_en)
        self.assertIn('href="https://uni-osnabrueck.de"', pool.directions_en)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RichImageUploadApiTests(APITestCase):
    """POST /api/manage/rich-images/ — admin-only image upload for rich text (#5)."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="user")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        self.lender = User.objects.create_user(username="lender")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)

    def _png(self, name="pic.png"):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_lender_forbidden(self):
        self.client.force_login(self.lender)
        response = self.client.post(
            "/api/manage/rich-images/",
            {"file": self._png()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)

    def test_borrower_forbidden(self):
        self.client.force_login(self.borrower)
        response = self.client.post(
            "/api/manage/rich-images/",
            {"file": self._png()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)

    def test_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin)
        bad = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        response = self.client.post(
            "/api/manage/rich-images/",
            {"file": bad},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_oversized_image(self):
        from catalog import rich_images

        self.client.force_login(self.admin)
        with patch.object(rich_images, "RICH_IMAGE_MAX_BYTES", 10):
            response = self.client.post(
                "/api/manage/rich-images/",
                {"file": self._png()},
                format="multipart",
            )
        self.assertEqual(response.status_code, 400)

    def test_admin_upload_returns_relative_media_url(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/manage/rich-images/",
            {"file": self._png()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        url = response.data["url"]
        self.assertTrue(url.startswith("/media/rich/"), url)
        self.assertTrue(url.endswith(".png"), url)
        self.assertTrue(default_storage.exists(url.removeprefix("/media/")))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RichImageHardeningTests(APITestCase):
    """#43: the upload re-encodes images (real format, no metadata, bomb guard)."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)

    def _upload(self, data, name, content_type="image/png"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.post(
            "/api/manage/rich-images/",
            {"file": SimpleUploadedFile(name, data, content_type=content_type)},
            format="multipart",
        )

    def _stored(self, response):
        from PIL import Image

        name = response.data["url"].removeprefix("/media/")
        with default_storage.open(name) as fh:
            data = fh.read()
        return name, Image.open(io.BytesIO(data))

    def _bytes(self, img, **kwargs):
        buffer = io.BytesIO()
        img.save(buffer, **kwargs)
        return buffer.getvalue()

    def test_real_format_decides_extension(self):
        from PIL import Image

        data = self._bytes(Image.new("RGB", (8, 8), (1, 2, 3)), format="PNG")
        response = self._upload(data, "evil.jpg", "image/jpeg")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["url"].endswith(".png"))

    def test_exif_and_gps_are_stripped(self):
        from PIL import Image

        img = Image.new("RGB", (8, 8), (1, 2, 3))
        exif = Image.Exif()
        exif[0x010F] = "Camera Inc"
        exif[0x8825] = {1: "N", 2: (52.0, 16.0, 0.0), 3: "E", 4: (8.0, 2.0, 0.0)}
        data = self._bytes(img, format="JPEG", exif=exif.tobytes())
        self.assertTrue(Image.open(io.BytesIO(data)).getexif())  # sanity
        response = self._upload(data, "photo.jpg", "image/jpeg")
        self.assertEqual(response.status_code, 201)
        name, stored = self._stored(response)
        self.assertTrue(name.endswith(".jpg"))
        self.assertEqual(len(stored.getexif()), 0)
        self.assertEqual(dict(stored.getexif().get_ifd(0x8825)), {})

    def test_exif_orientation_is_applied(self):
        from PIL import Image

        exif = Image.Exif()
        exif[0x0112] = 6
        data = self._bytes(
            Image.new("RGB", (20, 10), (1, 2, 3)), format="JPEG", exif=exif.tobytes()
        )
        response = self._upload(data, "rot.jpg", "image/jpeg")
        self.assertEqual(response.status_code, 201)
        _, stored = self._stored(response)
        self.assertEqual(stored.size, (10, 20))
        self.assertEqual(len(stored.getexif()), 0)

    def test_animated_gif_keeps_frames(self):
        from PIL import Image

        frames = [
            Image.new("RGB", (6, 6), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))
        ]
        data = self._bytes(
            frames[0], format="GIF", save_all=True, append_images=frames[1:],
            duration=80, loop=0,
        )
        self.assertEqual(Image.open(io.BytesIO(data)).n_frames, 3)
        response = self._upload(data, "a.gif", "image/gif")
        self.assertEqual(response.status_code, 201)
        name, stored = self._stored(response)
        self.assertTrue(name.endswith(".gif"))
        self.assertEqual(getattr(stored, "n_frames", 1), 3)

    def test_too_many_frames_rejected(self):
        from catalog import rich_images
        from PIL import Image

        frames = [Image.new("RGB", (2, 2), (i, 0, 0)) for i in range(5)]
        data = self._bytes(frames[0], format="GIF", save_all=True, append_images=frames[1:])
        with patch.object(rich_images, "RICH_IMAGE_MAX_FRAMES", 3):
            self.assertEqual(self._upload(data, "a.gif", "image/gif").status_code, 400)
        with patch.object(rich_images, "RICH_IMAGE_MAX_TOTAL_PIXELS", 10):
            self.assertEqual(self._upload(data, "a.gif", "image/gif").status_code, 400)

    def test_animated_webp_keeps_durations_and_loop(self):
        from PIL import Image

        frames = [
            Image.new("RGB", (6, 6), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))
        ]
        data = self._bytes(
            frames[0], format="WEBP", save_all=True, append_images=frames[1:],
            duration=[50, 120, 300], loop=3,
        )
        response = self._upload(data, "a.webp", "image/webp")
        self.assertEqual(response.status_code, 201)
        _, stored = self._stored(response)
        self.assertEqual(stored.n_frames, 3)
        self.assertEqual(stored.info.get("loop"), 3)
        durations = []
        for n in range(3):
            stored.seek(n)
            stored.load()
            durations.append(stored.info["duration"])
        self.assertEqual(durations, [50, 120, 300])

    def test_gif_without_loop_stays_without_loop(self):
        from PIL import Image

        frames = [Image.new("RGB", (6, 6), c) for c in ((255, 0, 0), (0, 255, 0))]
        data = self._bytes(frames[0], format="GIF", save_all=True,
                           append_images=frames[1:], duration=80)
        self.assertNotIn("loop", Image.open(io.BytesIO(data)).info)
        response = self._upload(data, "a.gif", "image/gif")
        _, stored = self._stored(response)
        self.assertNotIn("loop", stored.info)

    def test_gif_comment_is_dropped(self):
        from PIL import Image

        data = self._bytes(Image.new("RGB", (6, 6), (9, 9, 9)), format="GIF", comment=b"secret")
        self.assertEqual(Image.open(io.BytesIO(data)).info.get("comment"), b"secret")
        _, stored = self._stored(self._upload(data, "a.gif", "image/gif"))
        self.assertNotIn("comment", stored.info)

    def test_mpo_is_accepted_as_jpeg(self):
        from PIL import Image

        a = Image.new("RGB", (8, 8), (1, 2, 3))
        b = Image.new("RGB", (8, 8), (3, 2, 1))
        data = self._bytes(a, format="MPO", save_all=True, append_images=[b])
        self.assertEqual(Image.open(io.BytesIO(data)).format, "MPO")
        response = self._upload(data, "p.jpg", "image/jpeg")
        self.assertEqual(response.status_code, 201)
        name, stored = self._stored(response)
        self.assertTrue(name.endswith(".jpg"))
        self.assertEqual(stored.format, "JPEG")

    def test_pixel_limit_rejected(self):
        from catalog import rich_images
        from PIL import Image

        data = self._bytes(Image.new("RGB", (20, 20)), format="PNG")
        with patch.object(rich_images, "RICH_IMAGE_MAX_PIXELS", 100):
            response = self._upload(data, "big.png")
        self.assertEqual(response.status_code, 400)

    def test_non_image_rejected(self):
        response = self._upload(b"<svg></svg>", "x.png", "image/png")
        self.assertEqual(response.status_code, 400)

    def test_oversized_rejected(self):
        from catalog import rich_images
        from PIL import Image

        data = self._bytes(Image.new("RGB", (8, 8)), format="PNG")
        with patch.object(rich_images, "RICH_IMAGE_MAX_BYTES", 10):
            response = self._upload(data, "x.png")
        self.assertEqual(response.status_code, 400)

    def test_non_admin_forbidden(self):
        from PIL import Image

        self.client.force_login(User.objects.create_user(username="plain"))
        data = self._bytes(Image.new("RGB", (8, 8)), format="PNG")
        self.assertEqual(self._upload(data, "x.png").status_code, 403)


    XMP_GPS = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" '
        b'exif:GPSLatitude="52,16.0N" exif:GPSLongitude="8,2.0E"/>'
        b"</rdf:RDF></x:xmpmeta>"
    )

    def _stored_bytes(self, response):
        name = response.data["url"].removeprefix("/media/")
        with default_storage.open(name) as fh:
            return fh.read()

    def _assert_no_xmp(self, data, fmt, content_type, **kwargs):
        from PIL import Image

        self.assertIn(b"GPSLatitude", data)  # sanity: the source carries it
        response = self._upload(data, f"x.{fmt}", content_type)
        self.assertEqual(response.status_code, 201)
        stored = self._stored_bytes(response)
        self.assertNotIn(b"GPSLatitude", stored)
        self.assertNotIn(b"xmpmeta", stored)
        self.assertNotIn("xmp", Image.open(io.BytesIO(stored)).info)

    def test_xmp_dropped_from_jpeg(self):
        from PIL import Image

        data = self._bytes(Image.new("RGB", (8, 8), (1, 2, 3)), format="JPEG",
                           xmp=self.XMP_GPS)
        self._assert_no_xmp(data, "jpg", "image/jpeg")

    def test_xmp_dropped_from_webp(self):
        from PIL import Image

        data = self._bytes(Image.new("RGB", (8, 8), (1, 2, 3)), format="WEBP",
                           xmp=self.XMP_GPS)
        self._assert_no_xmp(data, "webp", "image/webp")

    def test_xmp_dropped_from_animated_webp(self):
        from PIL import Image

        frames = [Image.new("RGB", (8, 8), (i * 40, 0, 0)) for i in range(3)]
        data = self._bytes(frames[0], format="WEBP", save_all=True,
                           append_images=frames[1:], duration=50, xmp=self.XMP_GPS)
        self._assert_no_xmp(data, "webp", "image/webp")

    def test_xmp_dropped_from_png(self):
        from PIL import Image, PngImagePlugin

        info = PngImagePlugin.PngInfo()
        info.add_itxt("XML:com.adobe.xmp", self.XMP_GPS.decode())
        data = self._bytes(Image.new("RGB", (8, 8), (1, 2, 3)), format="PNG", pnginfo=info)
        self._assert_no_xmp(data, "png", "image/png")

    def _icc(self):
        from PIL import ImageCms

        return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    def test_icc_profile_kept_for_jpeg_and_webp(self):
        from PIL import Image

        icc = self._icc()
        for fmt, ct in (("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
            with self.subTest(fmt=fmt):
                data = self._bytes(Image.new("RGB", (8, 8), (1, 2, 3)), format=fmt,
                                   icc_profile=icc)
                response = self._upload(data, "c.img", ct)
                self.assertEqual(response.status_code, 201)
                _, stored = self._stored(response)
                self.assertEqual(stored.info.get("icc_profile"), icc)

    @staticmethod
    def _webp_chunks(data):
        pos, chunks = 12, []
        while pos + 8 <= len(data):
            chunks.append(data[pos:pos + 4])
            size = int.from_bytes(data[pos + 4:pos + 8], "little")
            pos += 8 + size + (size & 1)
        return chunks

    def test_lossless_webp_stays_lossless(self):
        from PIL import Image

        img = Image.effect_noise((32, 32), 64).convert("RGB")
        for extra in ({}, {"icc_profile": self._icc()}):  # simple and VP8X file
            with self.subTest(extended=bool(extra)):
                data = self._bytes(img, format="WEBP", lossless=True, **extra)
                response = self._upload(data, "l.webp", "image/webp")
                self.assertEqual(response.status_code, 201)
                stored = self._stored_bytes(response)
                self.assertIn(b"VP8L", self._webp_chunks(stored))
                self.assertEqual(
                    list(Image.open(io.BytesIO(stored)).getdata()), list(img.getdata())
                )

    def test_lossy_webp_stays_lossy(self):
        from PIL import Image

        data = self._bytes(Image.new("RGB", (16, 16), (9, 9, 9)), format="WEBP", quality=50)
        response = self._upload(data, "q.webp", "image/webp")
        self.assertEqual(response.status_code, 201)
        chunks = self._webp_chunks(self._stored_bytes(response))
        self.assertIn(b"VP8 ", chunks)
        self.assertNotIn(b"VP8L", chunks)

    def test_webp_lossless_detection(self):
        from catalog.rich_images import _webp_is_lossless

        self.assertFalse(_webp_is_lossless(b""))
        self.assertFalse(_webp_is_lossless(b"RIFF\0\0\0\0WEBPVP8 "))
        self.assertTrue(_webp_is_lossless(b"RIFF\0\0\0\0WEBPVP8L\0\0\0\0"))
        vp8x = b"VP8X" + (10).to_bytes(4, "little") + b"\0" * 10
        self.assertTrue(_webp_is_lossless(b"RIFF\0\0\0\0WEBP" + vp8x + b"VP8L\0\0\0\0"))
        self.assertFalse(_webp_is_lossless(b"RIFF\0\0\0\0WEBP" + vp8x + b"VP8 \0\0\0\0"))

    def test_apng_is_stored_as_first_frame(self):
        from PIL import Image

        frames = [Image.new("RGB", (8, 8), c) for c in ((255, 0, 0), (0, 255, 0))]
        data = self._bytes(frames[0], format="PNG", save_all=True,
                           append_images=frames[1:], duration=100)
        self.assertEqual(Image.open(io.BytesIO(data)).n_frames, 2)  # sanity
        response = self._upload(data, "a.png", "image/png")
        self.assertEqual(response.status_code, 201)
        _, stored = self._stored(response)
        self.assertEqual(getattr(stored, "n_frames", 1), 1)
        self.assertEqual(stored.convert("RGB").getpixel((0, 0)), (255, 0, 0))

class RichMediaNamesTests(SimpleTestCase):
    def test_parses_relative_and_absolute_urls(self):
        from catalog.richtext import rich_media_names

        html = (
            '<p><img src="/media/rich/x.png"></p>'
            '<img src="https://example.org/media/rich/y.jpg" alt="a">'
            "<img src='http://h/media/rich/z.webp'>"
            '<img src="/media/other/q.png"><img src="/static/rich/w.png">'
        )
        self.assertEqual(
            rich_media_names(html), {"rich/x.png", "rich/y.jpg", "rich/z.webp"}
        )

    def test_normalises_like_the_browser(self):
        from catalog.richtext import rich_media_names

        cases = {
            '<img src="/media/rich/%61bc.png">': {"rich/abc.png"},
            '<img src="/media/./rich/abc.png">': {"rich/abc.png"},
            '<img src="/media//rich/abc.png">': {"rich/abc.png"},
            '<img src="/media/x/../rich/abc.png">': {"rich/abc.png"},
            '<img src="/media/rich/a&amp;b.png">': {"rich/a&b.png"},
            '<img src="/media/rich/abc.png?v=1#top">': {"rich/abc.png"},
            '<img src=/media/rich/abc.png alt=x>': {"rich/abc.png"},
        }
        for html, expected in cases.items():
            with self.subTest(html=html):
                self.assertEqual(rich_media_names(html), expected)

    def test_ignores_urls_escaping_rich(self):
        from catalog.richtext import rich_media_names

        for src in ("/media/rich/../products/x.png", "/media/rich/", "/media/rich",
                    "//media/rich/x.png", "/media/rich/%2e%2e/branding/l.png",
                    "/media/richer/x.png", "media/rich/x.png", "/static/media/rich/x.png"):
            with self.subTest(src=src):
                self.assertEqual(rich_media_names(f'<img src="{src}">'), set())

    def test_text_outside_attributes_is_ignored(self):
        from catalog.richtext import rich_media_names

        self.assertEqual(rich_media_names("<p>see /media/rich/x.png</p>"), set())
        self.assertEqual(rich_media_names('<img data-src="/media/rich/x.png">'), set())

    def test_replace_rich_media_rewrites_to_canonical(self):
        from catalog.richtext import replace_rich_media

        html = ('<img src="/media/./rich/a.png" alt="1"><img src="/media/rich/%61.png">'
                "<img src='/media/rich/b.png'><a href=\"/media/rich/a.png\">a</a>")
        self.assertEqual(
            replace_rich_media(html, {"rich/a.png": "rich/a_X.png"}),
            '<img src="/media/rich/a_X.png" alt="1"><img src="/media/rich/a_X.png">'
            "<img src='/media/rich/b.png'><a href=\"/media/rich/a_X.png\">a</a>",
        )

    def test_empty(self):
        from catalog.richtext import rich_media_names

        self.assertEqual(rich_media_names(""), set())
        self.assertEqual(rich_media_names(None), set())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CleanupRichImagesTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        import os

        self.os = os

    def _file(self, name, age_days):
        from django.core.files.base import ContentFile

        default_storage.save(f"rich/{name}", ContentFile(b"x"))
        path = default_storage.path(f"rich/{name}")
        ts = (timezone.now() - timedelta(days=age_days)).timestamp()
        self.os.utime(path, (ts, ts))

    def _run(self, *args):
        out = io.StringIO()
        call_command("cleanup_rich_images", *args, stdout=out)
        return out.getvalue()

    def test_deletes_only_old_unreferenced(self):
        pool = ResourcePool.objects.create(name="P", pool_id="P")
        pool.description_en = '<p><img src="/media/rich/pool.png"></p>'
        pool.save()
        pool.soft_delete()  # trashed pool still counts
        page = Page.objects.create(slug="s", title="S", body="")
        page.body_en = '<p><img src="/media/rich/page.png"></p>'
        page.save()
        for name in ("pool.png", "page.png", "orphan-old.png"):
            self._file(name, 30)
        self._file("orphan-new.png", 1)
        out = self._run()
        self.assertIn("orphan-old.png", out)
        self.assertTrue(default_storage.exists("rich/pool.png"))
        self.assertTrue(default_storage.exists("rich/page.png"))
        self.assertTrue(default_storage.exists("rich/orphan-new.png"))
        self.assertFalse(default_storage.exists("rich/orphan-old.png"))

    def test_dry_run_deletes_nothing(self):
        self._file("orphan-old.png", 30)
        out = self._run("--dry-run")
        self.assertIn("orphan-old.png", out)
        self.assertTrue(default_storage.exists("rich/orphan-old.png"))

    def test_days_option(self):
        self._file("a.png", 3)
        self._run("--days", "2")
        self.assertFalse(default_storage.exists("rich/a.png"))

    def test_non_canonical_reference_keeps_file(self):
        page = Page.objects.create(slug="nc", title="NC", body="")
        page.body_en = (
            '<p><img src="/media/./rich/dot.png"><img src="/media/rich/%65nc.png">'
            '<img src="/media//rich/dbl.png"><img src="/media/x/../rich/up.png">'
            '<img src="/media/rich/a&amp;b.png"></p>'
        )
        page.save()
        for name in ("dot.png", "enc.png", "dbl.png", "up.png", "a&b.png", "gone.png"):
            self._file(name, 30)
        self._run()
        for name in ("dot.png", "enc.png", "dbl.png", "up.png", "a&b.png"):
            self.assertTrue(default_storage.exists(f"rich/{name}"), name)
        self.assertFalse(default_storage.exists("rich/gone.png"))

    def test_negative_days_rejected(self):
        from django.core.management.base import CommandError

        self._file("keep.png", 30)
        with self.assertRaises(CommandError):
            self._run("--days", "-1")
        self.assertTrue(default_storage.exists("rich/keep.png"))

    def test_absolute_media_url_rejected(self):
        from django.core.management.base import CommandError

        self._file("keep.png", 30)
        for url in ("https://cdn.example.org/media/", "http://cdn/media/", "//cdn/media/"):
            with self.subTest(url=url), override_settings(MEDIA_URL=url):
                with self.assertRaises(CommandError):
                    self._run()
        self.assertTrue(default_storage.exists("rich/keep.png"))


class RichTextMigrationTests(TestCase):
    """Migration 0047 converts existing rich-text fields to HTML (#5): CMS
    page bodies and the welcome text (Markdown), pool description/directions
    (plain text). Already-HTML content that is already sanitized is left
    byte-identical; already-HTML content that still carries unsafe markup is
    re-sanitized rather than passed through (I2)."""

    def _forwards(self):
        import importlib

        from django.apps import apps

        mod = importlib.import_module("catalog.migrations.0047_rich_text_html")
        mod.forwards(apps, None)

    def test_page_markdown_body_becomes_html(self):
        page = Page.objects.create(slug="migr-page", title="Test", body_de="**fett**")
        self._forwards()
        page.refresh_from_db()
        self.assertIn("<strong>fett</strong>", page.body_de)

    def test_already_html_page_body_is_untouched(self):
        html = "<p>Schon <strong>HTML</strong></p>"
        page = Page.objects.create(slug="migr-page-html", title="Test", body_de=html)
        self._forwards()
        page.refresh_from_db()
        self.assertEqual(page.body_de, html)

    def test_welcome_text_markdown_becomes_html(self):
        welcome = WelcomeSetting.load()
        welcome.text = "## Willkommen"
        welcome.save()
        self._forwards()
        welcome.refresh_from_db()
        self.assertIn("<h2>Willkommen</h2>", welcome.text)

    def test_pool_plain_directions_becomes_html(self):
        pool = ResourcePool.objects.create(
            name="Migr Pool", pool_id="migr-pool", directions_de="EG\nRaum 1"
        )
        self._forwards()
        pool.refresh_from_db()
        self.assertEqual(pool.directions_de, "<p>EG<br>Raum 1</p>")

    def test_second_run_changes_nothing_further(self):
        pool = ResourcePool.objects.create(
            name="Migr Pool 2", pool_id="migr-pool-2", directions_de="EG\nRaum 1"
        )
        self._forwards()
        pool.refresh_from_db()
        converted = pool.directions_de
        self._forwards()
        pool.refresh_from_db()
        self.assertEqual(pool.directions_de, converted)

    def test_already_html_pool_description_with_unsafe_markup_is_cleaned(self):
        # I2: this value is already HTML (so it's not run through
        # plain_to_html), but it still carries markup the allowlist rejects
        # — e.g. written straight to the DB before the model-level save()
        # sanitization (RichHtmlModelMixin) existed. QuerySet.update()
        # bypasses save() (like a raw SQL write would), so this reproduces
        # that pre-existing-data case without the live model cleaning it
        # first.
        pool = ResourcePool.objects.create(name="Migr Pool 3", pool_id="migr-pool-3")
        ResourcePool.all_objects.filter(pk=pool.pk).update(
            description_de='<p onclick="x()">a</p><script>b</script>'
        )
        self._forwards()
        pool.refresh_from_db()
        self.assertEqual(pool.description_de, "<p>a</p>")

    def test_second_run_of_unsafe_html_cleanup_is_idempotent(self):
        pool = ResourcePool.objects.create(name="Migr Pool 4", pool_id="migr-pool-4")
        ResourcePool.all_objects.filter(pk=pool.pk).update(
            description_de='<p onclick="x()">a</p><script>b</script>'
        )
        self._forwards()
        pool.refresh_from_db()
        cleaned = pool.description_de
        self._forwards()
        pool.refresh_from_db()
        self.assertEqual(pool.description_de, cleaned)


class TransferRichTextTests(APITestCase):
    """The ZIP import normalises rich fields the same way the migration does
    (#5): plain pool directions become HTML; already-HTML content is
    sanitized (script tags stripped)."""

    def _archive_with_directions(self, directions):
        import io
        import json
        import zipfile

        from catalog.transfer import build_archive

        pool = ResourcePool.objects.create(name="Rich Pool", pool_id="rich-pool")
        archive = build_archive("pool", pool=pool)
        zin = zipfile.ZipFile(io.BytesIO(archive))
        manifest = json.loads(zin.read("manifest.json"))
        manifest["resource_pools"][0]["directions"] = directions
        manifest["resource_pools"][0]["directions_de"] = directions
        manifest["resource_pools"][0]["directions_en"] = directions
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "manifest.json":
                    zout.writestr(item, json.dumps(manifest))
                else:
                    zout.writestr(item, zin.read(item.filename))
        return out.getvalue()

    def test_import_converts_plain_directions_to_html(self):
        import io

        from catalog.transfer import import_archive

        archive = self._archive_with_directions("EG\nRaum 1")
        import_archive(io.BytesIO(archive))
        pool = ResourcePool.objects.get(pool_id="rich-pool")
        self.assertEqual(pool.directions, "<p>EG<br>Raum 1</p>")

    def test_import_sanitizes_html_directions(self):
        import io

        from catalog.transfer import import_archive

        archive = self._archive_with_directions(
            "<p>Eingang Nord</p><script>alert(1)</script>"
        )
        import_archive(io.BytesIO(archive))
        pool = ResourcePool.objects.get(pool_id="rich-pool")
        self.assertIn("Eingang Nord", pool.directions)
        self.assertNotIn("<script", pool.directions)


class RichHtmlModelSaveTests(TestCase):
    """I1: rich-HTML fields are sanitized at the model level too, not just
    through the DRF serializer mixin — the Django admin, a data import, or a
    plain shell/ORM caller all go through Model.save() and must not be able
    to store unsafe markup."""

    DIRTY = '<img src=x onerror=alert(1)><script>alert(2)</script><p>ok</p>'

    def assertClean(self, value):
        self.assertIn("<p>ok</p>", value)
        self.assertNotIn("<script", value)
        self.assertNotIn("onerror", value)

    def test_page_body_sanitized_on_create(self):
        page = Page.objects.create(slug="orm-page", title="ORM", body_de=self.DIRTY)
        page.refresh_from_db()
        self.assertClean(page.body_de)

    def test_page_body_sanitized_on_update_fields_save(self):
        page = Page.objects.create(slug="orm-page-2", title="ORM", body_de="x")
        page.body_de = self.DIRTY
        page.save(update_fields=["body_de"])
        page.refresh_from_db()
        self.assertClean(page.body_de)

    def test_resourcepool_description_and_directions_sanitized_on_save(self):
        pool = ResourcePool.objects.create(
            name="ORM Pool", pool_id="orm-pool",
            description_de=self.DIRTY, directions_de=self.DIRTY,
        )
        pool.refresh_from_db()
        self.assertClean(pool.description_de)
        self.assertClean(pool.directions_de)

    def test_welcomesetting_text_sanitized_on_save(self):
        welcome = WelcomeSetting.load()
        welcome.text = self.DIRTY
        welcome.save()
        welcome.refresh_from_db()
        self.assertClean(welcome.text)

    def test_update_fields_only_cleans_the_named_fields(self):
        # A save() naming only one rich field must not skip cleaning it, nor
        # reach into a sibling rich field that wasn't part of this save.
        page = Page.objects.create(slug="orm-page-3", title="ORM", body_de="a", body_en="b")
        page.body_de = self.DIRTY
        page.body_en = self.DIRTY  # deliberately not included below
        page.save(update_fields=["body_de", "updated_at"])
        page.refresh_from_db()
        self.assertClean(page.body_de)
        self.assertEqual(page.body_en, "b")


class RichHtmlAdminSaveTests(TestCase):
    """I1: the Django admin change form writes through Model.save(), which
    must sanitize exactly like the API/serializer path does."""

    DIRTY_DE = '<p onclick="x()">ok</p><script>alert(1)</script>'
    FORMATTED_EN = '<p><strong>bold</strong></p>'

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin-rt", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)

    def test_page_admin_change_form_sanitizes_body(self):
        page = Page.objects.create(slug="admin-rt-page", title="T", body_de="old")
        response = self.client.post(
            reverse("admin:catalog_page_change", args=[page.id]),
            {
                "slug": "admin-rt-page",
                "title_de": "T",
                "title_en": "T",
                "body_de": self.DIRTY_DE,
                "body_en": self.FORMATTED_EN,
                "footer_order": 0,
                "show_in_footer": "on",
                "is_published": "on",
                "_save": "Save",
            },
        )
        # A redirect (302) is the normal "save succeeded" response; accept
        # 200 too in case validation errors leave a form unrelated to our
        # sanitize assertion, but still verify the field's stored value below.
        self.assertIn(response.status_code, (200, 302))
        page.refresh_from_db()
        self.assertIn("<p>ok</p>", page.body_de)
        self.assertNotIn("<script", page.body_de)
        self.assertNotIn("onclick", page.body_de)
        self.assertIn("<strong>bold</strong>", page.body_en)


class CategoriesFromTypesTests(SimpleTestCase):
    """catalog.structure.categories_from_types (#78): the ADR-0010 type
    navigation mapped to categories with the rules of migration 0052."""

    TYPES = [
        {"key": "cam", "name": "Camera", "position": 1},
        {"key": "mic", "name": "Microphone", "position": 0},
        {"key": "led", "name": "Light", "position": 1},
        {"key": "unused", "name": "Unused", "position": 0},
    ]

    def test_only_types_in_sections_by_position_then_name(self):
        from catalog.structure import categories_from_types

        converted, _ = categories_from_types(self.TYPES, [
            {"key": "s1", "types": ["led", "cam"], "type_order": []},
            {"key": "s2", "types": ["mic"], "type_order": ["mic"]},
        ])
        self.assertEqual(converted, ["mic", "cam", "led"])

    def test_section_order_then_missing_types_appended(self):
        from catalog.structure import categories_from_types

        _, sections = categories_from_types(self.TYPES, [
            {"key": "s1", "types": ["led", "cam", "mic"], "type_order": ["led", "x", "cam"]},
            {"key": "s2", "types": [], "type_order": ["cam"]},
        ])
        # Order entries outside the section are dropped; mic is appended in
        # type position order.
        self.assertEqual(sections, {"s1": ["led", "cam", "mic"], "s2": []})

    def test_unknown_type_keys_are_ignored(self):
        from catalog.structure import categories_from_types

        converted, sections = categories_from_types(self.TYPES, [
            {"key": "s1", "types": ["ghost", "cam"], "type_order": ["ghost"]},
        ])
        self.assertEqual(converted, ["cam"])
        self.assertEqual(sections, {"s1": ["cam"]})


class CategoriesToProductTypesMigrationTests(TransactionTestCase):
    """Data step 0049 (#20): run 0048 → 0050 on hand-built pre-migration data.

    0049 is irreversible, so the test steps back to 0047 manually: 0050 and
    0048 are unapplied for real, 0049 only fake-unapplied (no data step runs
    backwards). Other apps don't depend on catalog ≥ 0048, so only catalog
    moves.
    """

    BEFORE = ("catalog", "0047_rich_text_html")
    AFTER = ("catalog", "0050_remove_category")
    STEPS = (
        # #78 re-adds a ``catalog_category`` table: step back over it first.
        ("0058_resource_duration_limits", False),
        ("0057_product_rich_text", False),
        ("0056_remove_type_navigation", False),
        ("0055_category_unique_live_names", False),
        ("0054_dedupe_category_names", False),
        ("0053_section_categories_top_level", False),
        ("0052_product_types_to_categories", False),
        ("0051_category", False),
        ("0050_remove_category", False),
        ("0049_categories_to_product_types", True),
        ("0048_product_types_structure_fields", False),
    )

    def setUp(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        loader = executor.loader
        for name, fake in self.STEPS:
            # unapply() replays forwards from the state *before* the migration.
            state = loader.project_state(("catalog", name), at_end=False)
            executor.unapply_migration(
                state, loader.get_migration("catalog", name), fake=fake
            )
        self.old_apps = MigrationExecutor(connection).loader.project_state(
            self.BEFORE
        ).apps

    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        with contextlib.redirect_stdout(io.StringIO()):
            executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate_forward(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            executor.migrate([self.AFTER])
        return out.getvalue()

    def test_sections_get_types_and_single_type_categories_hand_over(self):
        apps = self.old_apps
        PT = apps.get_model("catalog", "ProductType")
        Product = apps.get_model("catalog", "Product")
        Category = apps.get_model("catalog", "Category")
        OldSection = apps.get_model("catalog", "Section")
        now = timezone.now()

        def ptype(name, **kw):
            return PT.objects.create(name=name, name_de=name, **kw)

        def product(title, t, **kw):
            return Product.objects.create(title=title, title_de=title, product_type=t, **kw)

        # Single-type category's type already has a German description.
        ta = ptype("Alpha", description="Schon da", description_de="Schon da")
        tb, tc, td = ptype("beta"), ptype("Camera"), ptype("Delta")
        hidden = ptype("hidden")  # only in a trashed category
        for name in ("Zebra", "apple", "Mango"):  # never reached
            ptype(name)

        p1, p2, p3 = product("A1", ta), product("A2", ta), product("A3", ta)
        p_trashed = product("B-trashed", tb, deleted_at=now)
        q1, q2 = product("B1", tb), product("C1", tc)
        r1 = product("D1", td)
        h1 = product("H1", hidden)

        single = Category.objects.create(
            title="Single", title_de="Single", position=1,
            description="Beschreibung", description_de="Beschreibung",
            description_en="Description", image="categories/single.png",
            # p2 missing, p_trashed (other type) and a dangling id listed.
            product_order=[p3.pk, p_trashed.pk, p1.pk, 99999],
        )
        single.products.set([p1, p2, p3, p_trashed])
        multi = Category.objects.create(
            title="Multi", title_de="Multi", position=0,
            image="categories/multi.png", description_en="Multi text",
            product_order=[q2.pk, q1.pk],
        )
        multi.products.set([q1, q2])
        other = Category.objects.create(title="Other", title_de="Other", position=2)
        other.products.set([r1])
        trashed_cat = Category.objects.create(
            title="Trashed", title_de="Trashed", position=3, deleted_at=now,
            image="categories/trashed.png",
        )
        trashed_cat.products.set([h1])

        s1 = OldSection.objects.create(
            title="S1", title_de="S1", position=0,
            category_order=[multi.pk, single.pk],
        )
        s1.categories.set([single, multi])
        # "Other" is not in category_order → sorts after "Single".
        s2 = OldSection.objects.create(
            title="S2", title_de="S2", position=1, category_order=[single.pk],
        )
        s2.categories.set([other, single, trashed_cat])

        output = self._migrate_forward()
        self.assertIn("Product types replace categories", output)

        # Read back through the post-migration historical models: plain
        # columns, no modeltranslation accessors (``description`` would
        # otherwise resolve to the active language).
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        new_apps = MigrationExecutor(connection).loader.project_state(self.AFTER).apps
        NewSection = new_apps.get_model("catalog", "Section")
        types = {t.name: t for t in new_apps.get_model("catalog", "ProductType").objects.all()}
        s1, s2 = NewSection.objects.get(pk=s1.pk), NewSection.objects.get(pk=s2.pk)
        self.assertEqual(s1.product_type_order, [tc.pk, tb.pk, ta.pk])
        self.assertEqual(
            set(s1.product_types.values_list("pk", flat=True)), {ta.pk, tb.pk, tc.pk}
        )
        self.assertEqual(s2.product_type_order, [ta.pk, td.pk])
        self.assertEqual(
            set(s2.product_types.values_list("pk", flat=True)), {ta.pk, td.pk}
        )

        alpha = types["Alpha"]
        self.assertEqual(alpha.image.name, "categories/single.png")
        self.assertEqual(alpha.description_de, "Schon da")  # kept
        self.assertEqual(alpha.description, "Schon da")  # kept
        self.assertEqual(alpha.description_en, "Description")  # copied
        self.assertEqual(alpha.product_order, [p3.pk, p1.pk])
        # Multi-type and trashed categories hand nothing over.
        for name in ("beta", "Camera", "hidden"):
            self.assertFalse(types[name].image, name)
            self.assertFalse(types[name].description_en, name)
            self.assertEqual(types[name].product_order, [], name)
        # Single-type "Other" had nothing to copy.
        self.assertFalse(types["Delta"].image)
        self.assertEqual(types["Delta"].product_order, [])

        positions = sorted(types.values(), key=lambda t: t.position)
        self.assertEqual(
            [t.name for t in positions],
            ["Camera", "beta", "Alpha", "Delta", "apple", "hidden", "Mango", "Zebra"],
        )
        self.assertEqual([t.position for t in positions], list(range(8)))
        self.assertNotIn("catalog_category", connection.introspection.table_names())


class TransferRichImageTests(TestCase):
    """Rich-text images (#42) travel in the ZIP archive, and importing media
    neither duplicates files on re-import nor writes anything in a dry-run (#64)."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)

        from django.core.files.base import ContentFile

        from catalog.models import Page, WelcomeSetting

        for name, colour in (
            ("page-de.png", 1), ("page-en.png", 2), ("welcome.png", 3),
            ("pool.png", 4), ("pool-dir.png", 5), ("other-pool.png", 6),
        ):
            default_storage.save(f"rich/{name}", ContentFile(self._png(colour)))
        category = Category.objects.create(name="Camera")
        category.image.save("camera.png", ContentFile(self._png(9)), save=True)
        self.page = Page.objects.create(slug="about", title="About")
        self.page.body_de = '<p>de</p><p><img src="/media/rich/page-de.png" alt=""></p>'
        self.page.body_en = '<p>en</p><p><img src="/media/rich/page-en.png" alt=""></p>'
        self.page.save()
        WelcomeSetting.objects.create(
            text='<p>hi</p><p><img src="/media/rich/welcome.png" alt=""></p>'
        )
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="digilab")
        self.pool.description_en = '<p><img src="/media/rich/pool.png" alt=""></p>'
        self.pool.directions_de = '<p><img src="/media/rich/pool-dir.png" alt=""></p>'
        self.pool.save()
        self.pool2 = ResourcePool.objects.create(
            name="Studio", pool_id="studio",
            description='<p><img src="/media/rich/other-pool.png" alt=""></p>',
        )

    @staticmethod
    def _png(colour):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (colour * 20, 10, 10)).save(buffer, format="PNG")
        return buffer.getvalue()

    def _files(self):
        import os

        found = set()
        for root, _dirs, files in os.walk(self.media_root):
            for name in files:
                found.add(os.path.relpath(os.path.join(root, name), self.media_root))
        return found

    def _snapshot(self):
        import os

        return {
            name: open(os.path.join(self.media_root, name), "rb").read()
            for name in self._files()
        }

    @staticmethod
    def _names(archive):
        import zipfile

        return set(zipfile.ZipFile(io.BytesIO(archive)).namelist())

    def test_full_export_contains_rich_images(self):
        from catalog.transfer import build_archive

        names = self._names(build_archive("full"))
        for name in ("page-de", "page-en", "welcome", "pool", "pool-dir", "other-pool"):
            self.assertIn(f"media/rich/{name}.png", names)

    def test_pool_export_contains_only_that_pools_rich_images(self):
        from catalog.transfer import build_archive

        rich = {n for n in self._names(build_archive("pool", pool=self.pool))
                if n.startswith("media/rich/")}
        self.assertEqual(rich, {"media/rich/pool.png", "media/rich/pool-dir.png"})

    def test_import_into_empty_storage_restores_rich_images(self):
        from catalog.models import Page, WelcomeSetting
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        originals = self._snapshot()
        shutil.rmtree(self.media_root)
        import os
        os.makedirs(self.media_root)

        import_archive(io.BytesIO(archive))
        # Rich images are stored re-encoded (#68), other media byte for byte.
        from catalog.rich_images import process_rich_image

        expected = {
            name: process_rich_image(data)[0] if name.startswith("rich/") else data
            for name, data in originals.items()
        }
        self.assertEqual(self._snapshot(), expected)
        page = Page.objects.get(slug="about")
        self.assertIn('src="/media/rich/page-de.png"', page.body_de)
        self.assertIn('src="/media/rich/page-en.png"', page.body_en)
        self.assertIn('src="/media/rich/welcome.png"', WelcomeSetting.objects.get().text)
        pool = ResourcePool.objects.get(pool_id="digilab")
        self.assertIn('src="/media/rich/pool.png"', pool.description_en)
        self.assertIn('src="/media/rich/pool-dir.png"', pool.directions_de)

    def test_reimport_creates_no_new_files(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        before = self._files()
        summary = import_archive(io.BytesIO(archive))
        self.assertEqual(self._files(), before)
        self.assertEqual(summary["media"], 0)
        category = Category.objects.get(name="Camera")
        self.assertEqual(category.image.name, "categories/camera.png")

    def test_dry_run_writes_nothing_and_reports_would_be_media(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        before = self._snapshot()
        shutil.rmtree(self.media_root)
        import os
        os.makedirs(self.media_root)

        summary = import_archive(io.BytesIO(archive), dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(self._files(), set())
        # 6 rich images + the product type image would be written.
        self.assertEqual(summary["media"], len(before))
        self.assertEqual(summary["media"], 7)

    def test_dry_run_with_existing_files_leaves_storage_unchanged(self):
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        default_storage.delete("rich/welcome.png")
        before = self._snapshot()
        summary = import_archive(io.BytesIO(archive), dry_run=True)
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(summary["media"], 1)  # only the missing welcome image

    def test_name_collision_with_different_content_renames_and_rewrites_html(self):
        from django.core.files.base import ContentFile

        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        default_storage.delete("rich/page-en.png")
        default_storage.save("rich/page-en.png", ContentFile(b"not the same image"))

        summary = import_archive(io.BytesIO(archive))
        self.assertEqual(summary["media"], 1)
        new = self._files() - set(self._snapshot_names_before_collision())
        self.assertEqual(len(new), 1)
        new_name = new.pop()
        self.assertTrue(new_name.startswith("rich/page-en"))
        self.assertNotEqual(new_name, "rich/page-en.png")
        from catalog.rich_images import process_rich_image

        with default_storage.open(new_name, "rb") as fh:
            self.assertEqual(fh.read(), process_rich_image(self._png(2))[0])
        with default_storage.open("rich/page-en.png", "rb") as fh:
            self.assertEqual(fh.read(), b"not the same image")  # untouched
        page = Page.objects.get(slug="about")
        self.assertIn(f'src="/media/{new_name}"', page.body_en)
        self.assertNotIn("/media/rich/page-en.png", page.body_en)
        self.assertIn('src="/media/rich/page-de.png"', page.body_de)

    def _rebuild(self, archive, edit, extra=None):
        import json
        import zipfile

        zin = zipfile.ZipFile(io.BytesIO(archive))
        manifest = json.loads(zin.read("manifest.json"))
        edit(manifest)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zout:
            for item in zin.infolist():
                if item.filename == "manifest.json":
                    zout.writestr(item, json.dumps(manifest))
                else:
                    zout.writestr(item, zin.read(item.filename))
            for name, data in (extra or {}).items():
                zout.writestr(name, data)
        return io.BytesIO(out.getvalue())

    def test_malicious_media_paths_are_ignored(self):
        import os

        from catalog.transfer import build_archive, import_archive

        def edit(manifest):
            manifest["categories"][0]["image"] = "media/../x.png"
            manifest["resource_pools"][0]["image"] = "media/rich/a\0.png"
            manifest["resource_pools"][0]["description_en"] = (
                '<p><img src="/media/rich/../../y.png" alt=""></p>'
            )

        archive = self._rebuild(
            build_archive("full"), edit,
            extra={"media/../x.png": self._png(7), "media/rich/../../y.png": self._png(8)},
        )
        parent = os.path.dirname(self.media_root)
        outside_before = set(os.listdir(parent))
        Category.objects.filter(name="Camera").update(image="")
        before = self._snapshot()

        summary = import_archive(archive)  # no exception
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(set(os.listdir(parent)), outside_before)
        self.assertEqual(summary["media"], 0)
        self.assertFalse(Category.objects.get(name="Camera").image)

    def test_rename_does_not_touch_similar_or_case_variant_names(self):
        from django.core.files.base import ContentFile

        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        default_storage.save("rich/a.png", ContentFile(self._png(10)))
        default_storage.save("rich/ab.png", ContentFile(self._png(11)))
        Page.objects.create(
            slug="similar", title="Similar",
            body_de='<p><img src="/media/rich/a.png" alt=""><img src="/media/rich/ab.png" alt="">'
                    '<img src="/media/RICH/A.PNG" alt=""></p>',
        )
        archive = build_archive("full")
        default_storage.delete("rich/a.png")
        default_storage.save("rich/a.png", ContentFile(b"other content"))

        import_archive(io.BytesIO(archive))  # case variant must not raise
        body = Page.objects.get(slug="similar").body_de
        self.assertNotIn('src="/media/rich/a.png"', body)
        self.assertRegex(body, r'src="/media/rich/a_\w+\.png"')
        self.assertIn('src="/media/rich/ab.png"', body)
        self.assertIn('src="/media/RICH/A.PNG"', body)

    def test_reference_missing_from_archive_leaves_html_unchanged(self):
        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        Page.objects.create(
            slug="missing", title="Missing",
            body_de='<p><img src="/media/rich/gone.png" alt=""></p>',
        )
        archive = build_archive("full")  # gone.png doesn't exist: not exported
        self.assertNotIn("media/rich/gone.png", self._names(archive))
        before = self._files()

        import_archive(io.BytesIO(archive))
        self.assertEqual(self._files(), before)
        self.assertIn('src="/media/rich/gone.png"', Page.objects.get(slug="missing").body_de)

    def _snapshot_names_before_collision(self):
        return {
            "rich/page-de.png", "rich/page-en.png", "rich/welcome.png",
            "rich/pool.png", "rich/pool-dir.png", "rich/other-pool.png",
            "categories/camera.png",
        }

    def test_directory_media_names_are_ignored(self):
        from django.core.files.base import ContentFile

        from catalog.transfer import _safe_media_name, build_archive, import_archive

        for name in (".", "rich", "products", "rich/", "rich/.", "./rich/x.png"):
            self.assertFalse(_safe_media_name(name), name)
        self.assertTrue(_safe_media_name("rich/x.png"))

        def edit(manifest):
            manifest["categories"][0]["image"] = "media/products"
            manifest["resource_pools"][0]["image"] = "media/rich"

        default_storage.save("products/p.png", ContentFile(self._png(12)))
        archive = self._rebuild(
            build_archive("full"), edit,
            extra={"media/products": self._png(7), "media/rich": self._png(8)},
        )
        before = self._snapshot()
        summary = import_archive(archive)  # no IsADirectoryError
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(summary["media"], 0)

    def test_storage_error_skips_the_file(self):
        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        shutil.rmtree(self.media_root)
        import os
        os.makedirs(self.media_root)
        with patch.object(default_storage, "save", side_effect=OSError("disk full")):
            summary = import_archive(io.BytesIO(archive))
        self.assertEqual(summary["media"], 0)
        self.assertTrue(Page.objects.filter(slug="about").exists())

    def test_rename_rewrites_non_canonical_references(self):
        import re

        from django.core.files.base import ContentFile

        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        default_storage.save("rich/nc.png", ContentFile(self._png(13)))
        Page.objects.create(
            slug="nc", title="NC",
            body_de='<p><img src="/media/./rich/nc.png" alt=""><img src="/media/rich/%6Ec.png" alt="">'
                    '<img src="/media/rich/nc.png" alt=""></p>',
        )
        archive = build_archive("full")
        self.assertIn("media/rich/nc.png", self._names(archive))
        default_storage.delete("rich/nc.png")
        default_storage.save("rich/nc.png", ContentFile(b"other content"))

        import_archive(io.BytesIO(archive))
        body = Page.objects.get(slug="nc").body_de
        new = re.findall(r'src="/media/(rich/nc_\w+\.png)"', body)
        self.assertEqual(len(new), 3)
        self.assertEqual(len(set(new)), 1)
        self.assertNotIn("/media/./rich/", body)
        from catalog.rich_images import process_rich_image

        with default_storage.open(new[0], "rb") as fh:
            self.assertEqual(fh.read(), process_rich_image(self._png(13))[0])

    # --- #68: archive rich images get the upload's validation + re-encode ---

    def _empty_storage(self):
        import os

        shutil.rmtree(self.media_root)
        os.makedirs(self.media_root)

    @staticmethod
    def _jpeg_with_gps():
        from PIL import Image

        exif = Image.Exif()
        exif[0x0110] = "Secret Phone"  # Model
        exif[0x8825] = {1: "N", 2: (52.0, 16.0, 30.0)}  # GPS IFD
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), (200, 10, 10)).save(buffer, format="JPEG", exif=exif)
        data = buffer.getvalue()
        assert Image.open(io.BytesIO(data)).getexif().get_ifd(0x8825)
        return data

    def _page_with(self, slug, name, data):
        from django.core.files.base import ContentFile

        from catalog.models import Page

        default_storage.save(f"rich/{name}", ContentFile(data))
        return Page.objects.create(
            slug=slug, title=slug, body_de=f'<p><img src="/media/rich/{name}" alt=""></p>',
        )

    def test_import_strips_exif_and_gps_from_rich_images(self):
        from PIL import Image

        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        self._page_with("gps", "photo.jpeg", self._jpeg_with_gps())
        archive = build_archive("full")
        self._empty_storage()

        summary = import_archive(io.BytesIO(archive))
        self.assertEqual(summary["skipped_media"], [])
        # ".jpeg" already names the JPEG format: the name is kept.
        with default_storage.open("rich/photo.jpeg", "rb") as fh:
            stored = Image.open(io.BytesIO(fh.read()))
        self.assertEqual(stored.format, "JPEG")
        self.assertNotIn("exif", stored.info)
        self.assertEqual(dict(stored.getexif()), {})
        self.assertIn('src="/media/rich/photo.jpeg"', Page.objects.get(slug="gps").body_de)

    def test_oversized_rich_image_is_skipped_before_decompression(self):
        from catalog import rich_images
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        self._empty_storage()

        with patch.object(rich_images, "RICH_IMAGE_MAX_BYTES", 10):
            summary = import_archive(io.BytesIO(archive))
        self.assertIn("rich/page-de.png", summary["skipped_media"])
        self.assertFalse(default_storage.exists("rich/page-de.png"))
        self.assertFalse(any(f.startswith("rich/") for f in self._files()))

    def test_rich_image_formats_all_have_extensions(self):
        from catalog.rich_images import RICH_IMAGE_EXTENSIONS, RICH_IMAGE_FORMATS

        self.assertLessEqual(set(RICH_IMAGE_FORMATS.values()), set(RICH_IMAGE_EXTENSIONS))

    def test_invalid_rich_image_is_skipped_and_reported(self):
        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        self._page_with("bad", "bad.png", b"definitely not an image")
        archive = build_archive("full")
        self.assertIn("media/rich/bad.png", self._names(archive))
        self._empty_storage()

        summary = import_archive(io.BytesIO(archive))  # no exception
        self.assertEqual(summary["skipped_media"], ["rich/bad.png"])
        self.assertFalse(default_storage.exists("rich/bad.png"))
        self.assertEqual(summary["media"], 7)  # the valid ones still arrive
        self.assertIn('src="/media/rich/bad.png"', Page.objects.get(slug="bad").body_de)
        self.assertTrue(Page.objects.filter(slug="about").exists())

    def test_png_named_jpg_is_stored_as_png_and_html_rewritten(self):
        from PIL import Image

        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        self._page_with("mislabeled", "shot.jpg", self._png(14))
        archive = build_archive("full")
        self._empty_storage()

        import_archive(io.BytesIO(archive))
        self.assertFalse(default_storage.exists("rich/shot.jpg"))
        with default_storage.open("rich/shot.png", "rb") as fh:
            self.assertEqual(Image.open(io.BytesIO(fh.read())).format, "PNG")
        body = Page.objects.get(slug="mislabeled").body_de
        self.assertIn('src="/media/rich/shot.png"', body)
        self.assertNotIn("shot.jpg", body)

        # Importing the very same archive again writes nothing new.
        before = self._snapshot()
        summary = import_archive(io.BytesIO(archive))
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(summary["media"], 0)
        self.assertIn('src="/media/rich/shot.png"',
                      Page.objects.get(slug="mislabeled").body_de)

    def test_reimport_of_reencoded_jpeg_writes_no_new_file(self):
        from catalog.transfer import build_archive, import_archive

        self._page_with("gps", "photo.jpg", self._jpeg_with_gps())
        archive = build_archive("full")
        self._empty_storage()
        import_archive(io.BytesIO(archive))
        before = self._snapshot()

        summary = import_archive(io.BytesIO(archive))
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(summary["media"], 0)

    def test_dry_run_processes_rich_images_but_writes_nothing(self):
        from catalog.models import Page
        from catalog.transfer import build_archive, import_archive

        self._page_with("bad", "bad.png", b"definitely not an image")
        self._page_with("mislabeled", "shot.jpg", self._png(14))
        archive = build_archive("full")
        self._empty_storage()

        summary = import_archive(io.BytesIO(archive), dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(self._files(), set())
        self.assertEqual(summary["skipped_media"], ["rich/bad.png"])
        self.assertEqual(summary["media"], 8)  # 7 + the renamed shot.png
        # The rename is not applied either (rolled back).
        self.assertIn("rich/shot.jpg", Page.objects.get(slug="mislabeled").body_de)


class AdminPoolScopeManageListTests(APITestCase):
    """Lending-area lists default to an admin's own pools ("My pools").

    A view filter only: retrieve/update and an explicit ?pool= still reach any
    pool; ``X-Pool-Scope: all`` widens it; lenders are unaffected by the header.
    """

    ALL = {"HTTP_X_POOL_SCOPE": "all"}

    def setUp(self):
        self.scoped_admin = User.objects.create_user(
            username="scoped-admin", is_staff=True, is_superuser=True
        )
        self.plain_admin = User.objects.create_user(
            username="plain-admin", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="scope-lender")
        pt = ProductType.objects.create(name="ScopeType")
        product = Product.objects.create(product_type=pt, title="Scope cam")
        self.pool_a = ResourcePool.objects.create(name="Scope A", pool_id="SA")
        self.pool_b = ResourcePool.objects.create(name="Scope B", pool_id="SB")
        self.pool_c = ResourcePool.objects.create(
            name="Scope C", pool_id="SC", is_active=False
        )
        for pool in (self.pool_a, self.pool_c):
            PoolMembership.objects.create(user=self.scoped_admin, resource_pool=pool)
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool_a)
        self.res = {}
        for pool in (self.pool_a, self.pool_b, self.pool_c):
            resource = Resource.objects.create(
                product=product, resource_pool=pool,
                inventory_number=f"{pool.pool_id}-1", qr_code_id=f"QR-{pool.pool_id}-1",
            )
            ResourceDefect.objects.create(resource=resource, note="broken")
            self.res[pool.pool_id] = resource

    def _get(self, user, url, params=None, **headers):
        self.client.force_login(user)
        response = self.client.get(url, params or {}, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _inventory(self, user, params=None, **headers):
        body = self._get(user, "/api/manage/inventory/", params, **headers)
        return sorted(r["inventory_number"] for r in body["results"])

    def test_inventory_list_scoped(self):
        self.assertEqual(self._inventory(self.scoped_admin), ["SA-1"])
        every = ["SA-1", "SB-1", "SC-1"]
        self.assertEqual(self._inventory(self.scoped_admin, **self.ALL), every)
        self.assertEqual(self._inventory(self.plain_admin), every)
        self.assertEqual(self._inventory(self.lender, **self.ALL), ["SA-1"])
        # Explicit pool filter and detail access still reach other pools.
        self.assertEqual(
            self._inventory(self.scoped_admin, {"pool": self.pool_b.id}), ["SB-1"]
        )
        self._get(self.scoped_admin, f"/api/manage/inventory/{self.res['SB'].id}/")
        res = self.client.patch(
            f"/api/manage/inventory/{self.res['SB'].id}/",
            {"storage_location": "Shelf 2"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_scoped_admin_can_patch_defect_ticket_of_other_pool(self):
        self.client.force_login(self.scoped_admin)
        res = self.client.patch(
            f"/api/manage/defect-tickets/{self.pool_b.id}/",
            {"defect_gitlab_url": "https://gitlab.example.org/g/p"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.pool_b.refresh_from_db()
        self.assertEqual(self.pool_b.defect_gitlab_url, "https://gitlab.example.org/g/p")

    def test_scoped_admin_can_update_resource_of_other_pool(self):
        self.client.force_login(self.scoped_admin)
        res = self.client.patch(
            f"/api/manage/inventory/{self.res['SB'].id}/",
            {"storage_location": "Shelf 9"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.res["SB"].refresh_from_db()
        self.assertEqual(self.res["SB"].storage_location, "Shelf 9")

    def test_inventory_defects_scoped(self):
        url = "/api/manage/inventory/defects/"

        def numbers(user, **headers):
            rows = self._get(user, url, **headers)["resources"]
            return sorted(r["inventory_number"] for r in rows)

        self.assertEqual(numbers(self.scoped_admin), ["SA-1"])
        every = ["SA-1", "SB-1", "SC-1"]
        self.assertEqual(numbers(self.scoped_admin, **self.ALL), every)
        self.assertEqual(numbers(self.plain_admin), every)
        self.assertEqual(numbers(self.lender, **self.ALL), ["SA-1"])

    def test_defect_tickets_list_scoped(self):
        url = "/api/manage/defect-tickets/"

        def names(user, **headers):
            return [p["name"] for p in self._get(user, url, **headers)]

        self.assertEqual(names(self.scoped_admin), ["Scope A"])
        every = ["Scope A", "Scope B", "Scope C"]
        self.assertEqual(names(self.scoped_admin, **self.ALL), every)
        self.assertEqual(names(self.plain_admin), every)
        self.assertEqual(names(self.lender, **self.ALL), ["Scope A"])
        self._get(self.scoped_admin, f"{url}{self.pool_b.id}/")

    def test_pool_list_scoped_only_for_lending_pickers(self):
        url = "/api/manage/pools/"

        def names(user, params=None, **headers):
            return sorted(p["name"] for p in self._get(user, url, params, **headers)["results"])

        every = ["Scope A", "Scope B", "Scope C"]
        lending = {"scope": "lending"}
        # The admin area (no opt-in) keeps the full list.
        self.assertEqual(names(self.scoped_admin), every)
        self.assertEqual(names(self.scoped_admin, lending), ["Scope A"])
        self.assertEqual(names(self.scoped_admin, lending, **self.ALL), every)
        self.assertEqual(names(self.plain_admin, lending), every)
        self.assertEqual(names(self.lender, lending, **self.ALL), ["Scope A"])
        self.assertEqual(names(self.lender, **self.ALL), ["Scope A"])
        # Detail access is not narrowed.
        self._get(self.scoped_admin, f"{url}{self.pool_b.id}/")


class CategoryModelTests(TestCase):
    """Hierarchical categories (#78, ADR-0011): tree rules and trash semantics."""

    def setUp(self):
        from catalog.models import Category

        self.Category = Category
        self.root = Category.objects.create(name="Kameras")
        self.child = Category.objects.create(name="Video", parent=self.root)
        self.grandchild = Category.objects.create(name="4K", parent=self.child)

    def test_str_ancestors_and_descendants(self):
        self.assertEqual(str(self.grandchild), "4K")
        self.assertEqual(self.grandchild.ancestors(), [self.root, self.child])
        self.assertEqual(self.root.ancestors(), [])
        self.assertEqual(
            self.root.descendant_ids(), {self.child.pk, self.grandchild.pk}
        )
        self.assertEqual(self.grandchild.depth, 2)

    def test_clean_rejects_self_and_descendant_as_parent(self):
        from django.core.exceptions import ValidationError

        self.root.parent = self.root
        with self.assertRaises(ValidationError):
            self.root.full_clean()
        self.root.parent = self.grandchild
        with self.assertRaises(ValidationError):
            self.root.full_clean()
        self.root.parent = None
        self.root.full_clean()  # fine again

    def test_validate_parent(self):
        from django.core.exceptions import ValidationError

        self.root.validate_parent(None)
        other = self.Category.objects.create(name="Audio")
        self.child.validate_parent(other)  # fine
        for bad in (self.root, self.child, self.grandchild):
            with self.assertRaises(ValidationError):
                self.root.validate_parent(bad)
        other.soft_delete()
        with self.assertRaises(ValidationError):
            self.child.validate_parent(other)
        self.child.parent = other
        with self.assertRaises(ValidationError):
            self.child.full_clean()

    def test_section_admin_offers_top_level_categories_only(self):
        field = Section._meta.get_field("categories")
        choices = field.remote_field.model.objects.complex_filter(
            field.get_limit_choices_to()
        )
        self.assertEqual(list(choices), [self.root])

    def test_clean_rejects_parent_for_category_in_a_section(self):
        from django.core.exceptions import ValidationError

        other = self.Category.objects.create(name="Audio")
        section = Section.objects.create(title="Medien")
        section.categories.add(other)
        other.parent = self.root
        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_product_and_section_relations(self):
        pt = ProductType.objects.create(name="Cam")
        product = Product.objects.create(product_type=pt, title="GoPro")
        product.categories.add(self.child, self.root)
        self.assertEqual(
            set(self.child.products.all()), {product}
        )
        section = Section.objects.create(title="Medien", category_order=[self.root.pk])
        section.categories.add(self.root)
        self.assertEqual(list(self.root.sections.all()), [section])

    def test_hard_delete_refused_while_it_has_children(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.child.delete()

    def test_restore_also_restores_trashed_ancestors(self):
        for c in (self.grandchild, self.child, self.root):
            c.soft_delete()
        self.Category.all_objects.get(pk=self.grandchild.pk).restore()
        self.assertEqual(
            set(self.Category.objects.values_list("pk", flat=True)),
            {self.root.pk, self.child.pk, self.grandchild.pk},
        )

    def test_children_first(self):
        ordered = self.Category.children_first(
            [self.root, self.grandchild, self.child]
        )
        self.assertEqual(ordered, [self.grandchild, self.child, self.root])


class CategoryTrashTests(APITestCase):
    def setUp(self):
        from catalog.models import Category

        self.Category = Category
        self.admin = User.objects.create_user(
            username="boss-cat", is_staff=True, is_superuser=True
        )
        self.root = Category.objects.create(name="Root")
        self.child = Category.objects.create(name="Child", parent=self.root)
        self.leaf = Category.objects.create(name="Leaf", parent=self.child)
        for c in (self.leaf, self.child, self.root):
            c.soft_delete(self.admin)

    def test_trash_lists_categories_for_admins_only(self):
        self.client.force_login(self.admin)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertTrue(any(r["type"] == "category" and r["id"] == self.root.pk for r in rows))
        lender = User.objects.create_user(username="len-cat")
        pool = ResourcePool.objects.create(name="CatPool", pool_id="CatPool")
        PoolMembership.objects.create(user=lender, resource_pool=pool)
        self.client.force_login(lender)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertFalse(any(r["type"] == "category" for r in rows))

    def test_empty_trash_purges_children_first(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.delete("/api/manage/trash/").status_code, 204)
        self.assertFalse(self.Category.all_objects.exists())

    def test_purge_trash_command_purges_children_first(self):
        self.Category.all_objects.update(deleted_at=timezone.now() - timedelta(days=99))
        call_command("purge_trash", stdout=io.StringIO(), stderr=io.StringIO())
        self.assertFalse(self.Category.all_objects.exists())


class ProductTypesToCategoriesMigrationTests(TransactionTestCase):
    """Data step 0052 (#78): product types in sections become categories."""

    BEFORE = ("catalog", "0051_category")
    AFTER = ("catalog", "0052_product_types_to_categories")

    def _state_apps(self, target):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        return MigrationExecutor(connection).loader.project_state(target).apps

    def _migrate(self, target):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            executor.migrate([target])
        return out.getvalue()

    def setUp(self):
        self._migrate(self.BEFORE)

    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        with contextlib.redirect_stdout(io.StringIO()):
            executor.migrate(executor.loader.graph.leaf_nodes())

    def _build(self):
        apps = self._state_apps(self.BEFORE)
        PT = apps.get_model("catalog", "ProductType")
        Product = apps.get_model("catalog", "Product")
        Sec = apps.get_model("catalog", "Section")
        now = timezone.now()
        cam = PT.objects.create(
            name="Kamera", name_de="Kamera", name_en="Camera",
            description="Filmen", description_de="Filmen", description_en="Filming",
            image="product_types/cam.png", position=3,
        )
        mic = PT.objects.create(name="Mikro", name_de="Mikro", name_en="Mic", position=1)
        PT.objects.create(name="Lonely", name_de="Lonely", position=0)  # no section
        gone = PT.objects.create(name="Gone", name_de="Gone", deleted_at=now)
        c1 = Product.objects.create(title="C1", title_de="C1", product_type=cam)
        c2 = Product.objects.create(title="C2", title_de="C2", product_type=cam)
        c_dead = Product.objects.create(
            title="Cx", title_de="Cx", product_type=cam, deleted_at=now
        )
        m1 = Product.objects.create(title="M1", title_de="M1", product_type=mic)
        cam.product_order = [c2.pk, c1.pk]
        cam.save()
        s1 = Sec.objects.create(
            title="S1", title_de="S1", product_type_order=[mic.pk, cam.pk]
        )
        s1.product_types.set([cam, mic, gone])
        s2 = Sec.objects.create(
            title="S2", title_de="S2", deleted_at=now, product_type_order=[cam.pk]
        )
        s2.product_types.set([cam])
        return locals()

    def test_types_in_sections_become_categories(self):
        data = self._build()
        output = self._migrate(self.AFTER)
        self.assertIn("Categories from product types", output)

        apps = self._state_apps(self.AFTER)
        Category = apps.get_model("catalog", "Category")
        Sec = apps.get_model("catalog", "Section")
        Product = apps.get_model("catalog", "Product")
        cats = {c.name_de: c for c in Category.objects.all()}
        self.assertEqual(set(cats), {"Kamera", "Mikro"})
        cam = cats["Kamera"]
        self.assertIsNone(cam.parent_id)
        self.assertEqual(
            (cam.name, cam.name_en, cam.description_de, cam.description_en),
            ("Kamera", "Camera", "Filmen", "Filming"),
        )
        self.assertEqual(cam.image.name, "product_types/cam.png")
        self.assertEqual(cam.position, 3)
        self.assertEqual(cam.product_order, [data["c2"].pk, data["c1"].pk])
        # Trashed products are linked too (hidden while trashed, categorised
        # once restored).
        self.assertEqual(
            set(
                Product._base_manager.filter(categories=cam).values_list(
                    "pk", flat=True
                )
            ),
            {data["c1"].pk, data["c2"].pk, data["c_dead"].pk},
        )
        mic = cats["Mikro"]
        self.assertEqual((mic.position, mic.name_en), (1, "Mic"))
        self.assertFalse(mic.image)

        s1 = Sec.objects.get(pk=data["s1"].pk)
        self.assertEqual(s1.category_order, [mic.pk, cam.pk])
        self.assertEqual(
            set(s1.categories.values_list("pk", flat=True)), {mic.pk, cam.pk}
        )
        s2 = Sec.objects.get(pk=data["s2"].pk)
        self.assertEqual(s2.category_order, [cam.pk])
        self.assertEqual(list(s2.categories.values_list("pk", flat=True)), [cam.pk])

    def test_rerun_is_idempotent(self):
        import importlib

        self._build()
        self._migrate(self.AFTER)
        module = importlib.import_module(
            "catalog.migrations.0052_product_types_to_categories"
        )
        apps = self._state_apps(self.AFTER)
        Category = apps.get_model("catalog", "Category")
        Sec = apps.get_model("catalog", "Section")
        Product = apps.get_model("catalog", "Product")

        def snapshot():
            return (
                sorted(Category.objects.values_list(
                    "pk", "name", "position", "product_order", "image"
                )),
                sorted(
                    (s.pk, tuple(s.category_order),
                     tuple(sorted(s.categories.values_list("pk", flat=True))))
                    for s in Sec.objects.all()
                ),
                sorted(Product.categories.through.objects.values_list(
                    "product_id", "category_id"
                )),
            )

        before = snapshot()
        with contextlib.redirect_stdout(io.StringIO()):
            module.forwards(apps, None)
        self.assertEqual(snapshot(), before)

    def test_type_missing_from_order_is_appended(self):
        data = self._build()
        apps = self._state_apps(self.BEFORE)
        PT = apps.get_model("catalog", "ProductType")
        extra = PT.objects.create(name="Stativ", name_de="Stativ", position=9)
        apps.get_model("catalog", "Section").objects.get(
            pk=data["s1"].pk
        ).product_types.add(extra)
        self._migrate(self.AFTER)

        apps = self._state_apps(self.AFTER)
        cats = {c.name: c.pk for c in apps.get_model("catalog", "Category").objects.all()}
        s1 = apps.get_model("catalog", "Section").objects.get(pk=data["s1"].pk)
        self.assertEqual(
            s1.category_order, [cats["Mikro"], cats["Kamera"], cats["Stativ"]]
        )

    def test_existing_live_category_is_reused_trashed_one_ignored(self):
        data = self._build()
        apps = self._state_apps(self.BEFORE)
        Category = apps.get_model("catalog", "Category")
        live = Category.objects.create(
            name="Kamera", name_de="Kamera", position=42, product_order=[7]
        )
        trashed = Category.objects.create(
            name="Mikro", name_de="Mikro", deleted_at=timezone.now()
        )
        output = self._migrate(self.AFTER)
        self.assertIn("Already present (left unchanged): Kamera", output)

        apps = self._state_apps(self.AFTER)
        Category = apps.get_model("catalog", "Category")
        Product = apps.get_model("catalog", "Product")
        Sec = apps.get_model("catalog", "Section")
        self.assertEqual(Category.objects.filter(name="Kamera").count(), 1)
        live = Category.objects.get(pk=live.pk)
        self.assertEqual((live.position, live.product_order), (42, [7]))
        self.assertEqual(
            set(Product.objects.filter(categories=live).values_list("pk", flat=True)),
            {data["c1"].pk, data["c2"].pk, data["c_dead"].pk},  # trashed too
        )
        fresh_mic = Category.objects.get(name="Mikro", deleted_at__isnull=True)
        self.assertNotEqual(fresh_mic.pk, trashed.pk)
        s1 = Sec.objects.get(pk=data["s1"].pk)
        self.assertEqual(s1.category_order, [fresh_mic.pk, live.pk])
        self.assertFalse(Product.objects.filter(categories__pk=trashed.pk).exists())

    def test_fresh_install_stays_quiet(self):
        self.assertEqual(self._migrate(self.AFTER).strip(), "")


class CategoryShopFixture:
    """Shared tree for the category shop API tests (#78)::

        Section "Recording" (category_order: Audio, Cameras)
          Cameras (pos 0)
            Video (pos 0)
              4K (pos 0)
            Photo (pos 1)
          Audio (pos 1)
    """

    def build(self):
        from catalog.models import Category

        self.pool = ResourcePool.objects.create(name="Lab", pool_id="LAB")
        self.pt = ProductType.objects.create(name="Gear")
        self.cameras = Category.objects.create(name="Cameras", position=0)
        self.video = Category.objects.create(name="Video", parent=self.cameras, position=0)
        self.k4 = Category.objects.create(name="4K", parent=self.video, position=0)
        self.photo = Category.objects.create(name="Photo", parent=self.cameras, position=1)
        self.audio = Category.objects.create(name="Audio", position=1)
        self.section = Section.objects.create(title="Recording", position=0)
        self.section.categories.add(self.cameras, self.audio)
        self.section.category_order = [self.audio.id, self.cameras.id]
        self.section.save()
        self._n = 0

    def product(self, title, *categories, lending_type="days", pool=None):
        self._n += 1
        product = Product.objects.create(
            product_type=self.pt, title=title, lending_type=lending_type
        )
        product.categories.add(*categories)
        Resource.objects.create(
            product=product, resource_pool=pool or self.pool,
            inventory_number=f"C-{self._n}", qr_code_id=f"QR-C-{self._n}",
        )
        return product

    def count_queries(self, method):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            response = method()
        self.assertEqual(response.status_code, 200)
        self._last = "\n".join(q["sql"][:200] for q in ctx.captured_queries)
        return len(ctx.captured_queries), response.json()


class CategoryShopApiTests(CategoryShopFixture, APITestCase):
    """Shop navigation by categories (#78): sections, category pages, search,
    pool grouping and product filters."""

    def setUp(self):
        self.build()

    def test_section_list_counts_categories_and_subtree_products(self):
        self.product("A", self.video)
        self.product("B", self.k4, self.cameras)  # counted once
        self.product("C", self.audio)
        self.product("Unrelated")
        row = self.client.get("/api/sections/").json()["results"][0]
        self.assertEqual(row["category_count"], 2)
        self.assertEqual(row["product_count"], 3)
        self.assertNotIn("product_type_count", row)

    def test_section_list_query_count_is_flat(self):
        from catalog.models import Category

        self.product("A", self.video)

        def get():
            return self.client.get("/api/sections/")

        self.count_queries(get)  # warm-up
        small, body = self.count_queries(get)
        self.assertEqual(len(body["results"]), 1)
        for i in range(4):
            section = Section.objects.create(title=f"S{i}", position=i + 1)
            root = Category.objects.create(name=f"R{i}")
            sub = Category.objects.create(name=f"Sub{i}", parent=root)
            section.categories.add(root)
            self.product(f"P{i}", sub)
        large, body = self.count_queries(get)
        self.assertEqual(len(body["results"]), 5)
        self.assertEqual([s["product_count"] for s in body["results"]], [1, 1, 1, 1, 1])
        self.assertEqual(large, small, self._last)

    def test_section_detail_groups_by_top_level_category(self):
        a = self.product("Alpha", self.video)
        self.product("Bravo", self.audio)
        body = self.client.get(f"/api/sections/{self.section.id}/").json()
        self.assertNotIn("product_types", body)
        groups = body["categories"]
        self.assertEqual([g["name"] for g in groups], ["Audio", "Cameras"])
        self.assertEqual(
            set(groups[1]),
            {"id", "name", "description", "image", "product_count",
             "child_count", "children", "products"},
        )
        # Photo has no visible product, so borrowers don't count it.
        self.assertEqual(groups[1]["child_count"], 1)
        self.assertEqual(groups[1]["product_count"], 1)
        self.assertEqual([p["id"] for p in groups[1]["products"]], [a.id])

    def test_section_detail_children_filter_payload(self):
        a = self.product("A", self.k4)
        b = self.product("B", self.video, self.k4)  # dedup within subtree
        c = self.product("C", self.photo)
        self.product("Own", self.cameras)  # not in any child
        self.product("Audio", self.audio)
        groups = self.client.get(f"/api/sections/{self.section.id}/").json()["categories"]
        cams = next(g for g in groups if g["id"] == self.cameras.id)
        # Direct children only, sibling order (Video pos 0, Photo pos 1).
        self.assertEqual(
            cams["children"],
            [
                {"id": self.video.id, "name": "Video", "product_count": 2,
                 "product_ids": sorted([a.id, b.id])},
                {"id": self.photo.id, "name": "Photo", "product_count": 1,
                 "product_ids": [c.id]},
            ],
        )
        self.assertEqual(cams["child_count"], 2)
        audio = next(g for g in groups if g["id"] == self.audio.id)
        self.assertEqual(audio["children"], [])

    def test_category_detail_children_have_product_ids(self):
        a = self.product("A", self.k4)
        b = self.product("B", self.photo)
        body = self.client.get(f"/api/categories/{self.cameras.id}/").json()
        self.assertEqual(
            [(c["id"], c["product_count"], c["product_ids"]) for c in body["children"]],
            [(self.video.id, 1, [a.id]), (self.photo.id, 1, [b.id])],
        )
        self.assertIn("child_count", body["children"][0])

    def test_section_detail_query_count_ignores_children(self):
        from catalog.models import Category

        self.product("A", self.k4)

        def get():
            return self.client.get(f"/api/sections/{self.section.id}/")

        self.count_queries(get)  # warm-up
        small, _ = self.count_queries(get)
        for i in range(4):
            sub = Category.objects.create(name=f"Extra{i}", parent=self.cameras, position=5 + i)
            self.product(f"P{i}", sub)
        large, body = self.count_queries(get)
        cams = next(g for g in body["categories"] if g["id"] == self.cameras.id)
        self.assertEqual(len(cams["children"]), 5)
        self.assertEqual(large, small, self._last)

    def test_section_detail_shop_order_dedup_and_daily_first(self):
        own_b = self.product("Own B", self.cameras)
        self.product("Own A", self.cameras)
        hourly = self.product("Hourly", self.cameras, lending_type="hours")
        self.product("In video", self.video)
        self.product("In 4K", self.k4, self.photo)
        self.product("In photo", self.photo)
        self.product("Both", self.cameras, self.video)
        self.cameras.product_order = [hourly.id, own_b.id]
        self.cameras.save()
        body = self.client.get(f"/api/sections/{self.section.id}/").json()
        cams = next(g for g in body["categories"] if g["id"] == self.cameras.id)
        # Own products (curated, then title), then Video subtree (Video, 4K),
        # then Photo; "Both" listed once; hourly after all daily ones.
        self.assertEqual(
            [p["title"] for p in cams["products"]],
            ["Own B", "Both", "Own A", "In video", "In 4K", "In photo", "Hourly"],
        )
        self.assertEqual(cams["product_count"], 7)

    def test_section_detail_hides_trashed_and_nested_categories(self):
        from catalog.models import Category

        trashed = Category.objects.create(name="Trashed")
        self.section.categories.add(trashed)
        trashed.soft_delete(None)
        # A sub-category put into a section by other means is ignored.
        Section.categories.through.objects.create(
            section_id=self.section.id, category_id=self.video.id
        )
        self.product("Cam", self.video)
        self.product("Mic", self.audio)
        body = self.client.get(f"/api/sections/{self.section.id}/").json()
        self.assertEqual([g["name"] for g in body["categories"]], ["Audio", "Cameras"])

    def test_section_detail_query_count_is_flat(self):
        from catalog.models import Category, ProductImage

        def add(start, stop):
            for i in range(start, stop):
                root = Category.objects.create(name=f"R{i}", position=10 + i)
                sub = Category.objects.create(name=f"S{i}", parent=root)
                self.section.categories.add(root)
                for j, cat in enumerate((root, sub)):
                    p = self.product(f"P{i}-{j}", cat, lending_type=("days", "hours")[j])
                    ProductImage.objects.create(product=p, image=f"x/{i}-{j}.png")

        def get():
            return self.client.get(f"/api/sections/{self.section.id}/")

        add(0, 1)
        self.count_queries(get)  # warm-up
        small, body = self.count_queries(get)
        self.assertEqual(len(body["categories"]), 1)  # empty ones hidden
        add(1, 5)
        large, body = self.count_queries(get)
        self.assertEqual(len(body["categories"]), 5)
        self.assertEqual(large, small, self._last)
        self.assertLessEqual(small, 12, self._last)

    def test_category_detail(self):
        own = self.product("Own", self.cameras)
        sub = self.product("Sub", self.k4)
        self.product("Photo cam", self.photo)
        self.cameras.description = "All cameras"
        self.cameras.save()
        body = self.client.get(f"/api/categories/{self.video.id}/").json()
        self.assertEqual(body["name"], "Video")
        self.assertEqual(body["parent"], self.cameras.id)
        self.assertEqual(body["ancestors"], [{"id": self.cameras.id, "name": "Cameras"}])
        self.assertEqual(body["sections"], [{"id": self.section.id, "title": "Recording"}])
        self.assertEqual(
            [(c["name"], c["product_count"]) for c in body["children"]], [("4K", 1)]
        )
        self.assertEqual([p["id"] for p in body["products"]], [sub.id])
        self.assertEqual(body["product_count"], 1)

        root = self.client.get(f"/api/categories/{self.cameras.id}/").json()
        self.assertEqual(root["ancestors"], [])
        self.assertEqual(root["parent"], None)
        self.assertEqual(
            [(c["name"], c["product_count"]) for c in root["children"]],
            [("Video", 1), ("Photo", 1)],
        )
        self.assertEqual(root["product_count"], 3)
        self.assertEqual(root["products"][0]["id"], own.id)

    def test_category_detail_404s(self):
        from catalog.models import Category

        self.assertEqual(self.client.get("/api/categories/999999/").status_code, 404)
        self.photo.soft_delete(None)
        self.assertEqual(
            self.client.get(f"/api/categories/{self.photo.id}/").status_code, 404
        )
        # A live category below a trashed parent is unreachable.
        orphan_parent = Category.objects.create(name="Gone")
        orphan = Category.objects.create(name="Orphan", parent=orphan_parent)
        orphan_parent.soft_delete(None)
        self.assertEqual(
            self.client.get(f"/api/categories/{orphan.id}/").status_code, 404
        )
        # No list route: the shop navigates via sections.
        self.assertEqual(self.client.get("/api/categories/").status_code, 404)

    def test_category_detail_query_count_is_flat(self):
        from catalog.models import Category

        def get():
            return self.client.get(f"/api/categories/{self.cameras.id}/")

        self.product("A", self.k4)
        self.count_queries(get)  # warm-up
        small, _ = self.count_queries(get)
        parent = self.k4
        for i in range(4):
            parent = Category.objects.create(name=f"Deep{i}", parent=parent)
            self.product(f"D{i}", parent)
            Category.objects.create(name=f"Side{i}", parent=self.cameras, position=5 + i)
        large, body = self.count_queries(get)
        self.assertEqual(body["product_count"], 5)
        self.assertEqual(large, small, self._last)

    def test_search_matches_categories_with_path(self):
        a = self.product("Sony", self.k4)
        res = self.client.get("/api/search/", {"q": "4k"}).json()
        self.assertEqual(set(res), {"sections", "categories", "products"})
        cats = res["categories"]
        self.assertEqual([c["name"] for c in cats], ["4K"])
        self.assertEqual(
            cats[0]["path"],
            [{"id": self.cameras.id, "name": "Cameras"}, {"id": self.video.id, "name": "Video"}],
        )
        self.assertEqual([p["id"] for p in cats[0]["products"]], [a.id])
        # Empty categories are left out; a matched section lists its categories.
        res = self.client.get("/api/search/", {"q": "e"}).json()
        self.assertEqual(
            [c["name"] for c in res["categories"]], ["Cameras", "Video"]
        )
        sec = self.client.get("/api/search/", {"q": "Record"}).json()["sections"]
        self.assertEqual([g["name"] for g in sec[0]["categories"]], ["Cameras"])

    def test_search_empty_query(self):
        res = self.client.get("/api/search/", {"q": ""})
        self.assertEqual(res.data, {"sections": [], "categories": [], "products": []})

    def test_search_query_count_is_flat(self):
        from catalog.models import Category

        def get():
            return self.client.get("/api/search/", {"q": "Rec"})

        self.product("A", self.video)
        self.count_queries(get)
        small, body = self.count_queries(get)
        self.assertEqual(len(body["sections"]), 1)
        for i in range(4):
            section = Section.objects.create(title=f"Rec {i}", position=i + 1)
            root = Category.objects.create(name=f"Rec root {i}")
            sub = Category.objects.create(name=f"Rec sub {i}", parent=root)
            section.categories.add(root)
            self.product(f"P{i}", sub)
        large, body = self.count_queries(get)
        self.assertEqual(len(body["sections"]), 5)
        self.assertEqual(len(body["categories"]), 8)
        self.assertEqual(large, small, self._last)

    def test_product_filters_by_category_subtree_and_section(self):
        from catalog.models import Category

        in_4k = self.product("4K cam", self.k4)
        in_audio = self.product("Mic", self.audio)
        other = Category.objects.create(name="Other")
        loose = self.product("Loose", other)

        def ids(params):
            res = self.client.get("/api/products/", params)
            self.assertEqual(res.status_code, 200)
            return {p["id"] for p in res.data["results"]}

        self.assertEqual(ids({"category": self.cameras.id}), {in_4k.id})
        self.assertEqual(ids({"category": self.photo.id}), set())
        self.assertEqual(ids({"section": self.section.id}), {in_4k.id, in_audio.id})
        self.assertEqual(ids({"category": "x"}), set())
        self.assertEqual(ids({"category": 999999}), set())
        self.assertIn(loose.id, ids({}))

    def test_pool_grouped_by_top_level_category(self):
        from catalog.models import Category

        self.audio.position = 0
        self.audio.save()
        self.cameras.position = 1
        self.cameras.save()
        lone = Category.objects.create(name="Empty root", position=5)
        both = self.product("Both", self.k4, self.audio)
        hourly = self.product("Hourly", self.photo, lending_type="hours")
        daily = self.product("Daily", self.photo)
        none = self.product("No category")
        locked = ResourcePool.objects.create(name="Else", pool_id="ELSE")
        self.product("Elsewhere", self.audio, pool=locked)
        groups = self.client.get(f"/api/pools/{self.pool.id}/products-grouped/").json()
        self.assertEqual(
            [g["category"] for g in groups],
            [
                {"id": self.audio.id, "name": "Audio"},
                {"id": self.cameras.id, "name": "Cameras"},
                None,
            ],
        )
        self.assertNotIn(lone.id, [g["category"] and g["category"]["id"] for g in groups])
        self.assertEqual([p["id"] for p in groups[0]["products"]], [both.id])
        self.assertEqual(
            [p["id"] for p in groups[1]["products"]], [both.id, daily.id, hourly.id]
        )
        self.assertEqual([p["id"] for p in groups[2]["products"]], [none.id])

    def test_pool_grouped_query_count_is_flat(self):
        from catalog.models import Category

        def get():
            return self.client.get(f"/api/pools/{self.pool.id}/products-grouped/")

        self.product("A", self.video)
        self.count_queries(get)
        small, _ = self.count_queries(get)
        for i in range(4):
            root = Category.objects.create(name=f"R{i}")
            self.product(f"P{i}", Category.objects.create(name=f"S{i}", parent=root))
        large, groups = self.count_queries(get)
        self.assertEqual(len(groups), 5)
        self.assertEqual(large, small, self._last)


class CategoryShopVisibilityTests(CategoryShopFixture, APITestCase):
    """Products in an AccessGroup-restricted pool stay hidden (and uncounted)
    for non-members in every category view (concept §3.4, #78)."""

    def setUp(self):
        from accounts.models import AccessGroup

        self.build()
        self.locked = ResourcePool.objects.create(name="Locked", pool_id="LOCK")
        group = AccessGroup.objects.create(name="Music")
        group.pools.add(self.locked)
        self.member = User.objects.create_user(username="member")
        group.members.add(self.member)
        self.outsider = User.objects.create_user(username="outsider")
        self.product("Open cam", self.video)
        self.product("Locked cam", self.k4, pool=self.locked)

    def _seen(self, user):
        self.client.logout()
        if user:
            self.client.force_login(user)
        listed = self.client.get("/api/sections/").json()["results"][0]
        detail = self.client.get(f"/api/sections/{self.section.id}/").json()
        cams = next(g for g in detail["categories"] if g["id"] == self.cameras.id)
        cat = self.client.get(f"/api/categories/{self.video.id}/").json()
        search = self.client.get("/api/search/", {"q": "4K"}).json()
        return {
            "list": listed["product_count"],
            "detail": [p["title"] for p in cams["products"]],
            "category": [p["title"] for p in cat["products"]],
            "children": [(c["name"], c["product_count"]) for c in cat["children"]],
            "search": [c["name"] for c in search["categories"]],
        }

    def test_non_members_do_not_see_restricted_products(self):
        for user in (None, self.outsider):
            self.assertEqual(
                self._seen(user),
                {"list": 1, "detail": ["Open cam"], "category": ["Open cam"],
                 "children": [], "search": []},
            )

    def test_section_list_counts_per_section_respect_eligibility(self):
        """#63: one grouped computation, still correct per section."""
        from catalog.models import Category

        locked_root = Category.objects.create(name="Synths")
        locked_section = Section.objects.create(title="Locked only", position=5)
        locked_section.categories.add(locked_root)
        self.product("Moog", locked_root, pool=self.locked)

        def counts(user):
            self.client.logout()
            if user:
                self.client.force_login(user)
            results = self.client.get("/api/sections/").json()["results"]
            return {s["title"]: s["product_count"] for s in results}

        for user in (None, self.outsider):
            self.assertEqual(counts(user), {"Recording": 1, "Locked only": 0})
        self.assertEqual(counts(self.member), {"Recording": 2, "Locked only": 1})

    def test_restricted_children_hidden_and_ids_not_leaked(self):
        for user in (None, self.outsider):
            self.client.logout()
            if user:
                self.client.force_login(user)
            detail = self.client.get(f"/api/sections/{self.section.id}/").json()
            cams = next(g for g in detail["categories"] if g["id"] == self.cameras.id)
            # 4K is only used in the locked pool: its subtree product is
            # Video's visible one only, and no chip for 4K at root level.
            self.assertEqual([c["name"] for c in cams["children"]], ["Video"])
            self.assertEqual(len(cams["children"][0]["product_ids"]), 1)
            cat = self.client.get(f"/api/categories/{self.cameras.id}/").json()
            self.assertEqual(
                [c["product_ids"] for c in cat["children"]],
                [c["product_ids"] for c in cams["children"]],
            )
        locked_id = Product.objects.get(title="Locked cam").id
        self.client.force_login(self.member)
        detail = self.client.get(f"/api/sections/{self.section.id}/").json()
        cams = next(g for g in detail["categories"] if g["id"] == self.cameras.id)
        self.assertIn(locked_id, cams["children"][0]["product_ids"])

    def test_restricted_only_child_is_hidden_for_borrowers(self):
        from catalog.models import Category

        secret = Category.objects.create(name="Secret", parent=self.cameras, position=9)
        self.product("Hidden", secret, pool=self.locked)
        self.client.force_login(self.outsider)
        detail = self.client.get(f"/api/sections/{self.section.id}/").json()
        cams = next(g for g in detail["categories"] if g["id"] == self.cameras.id)
        self.assertNotIn("Secret", [c["name"] for c in cams["children"]])
        self.assertNotIn("Secret", str(cams))

    def test_member_sees_restricted_products(self):
        self.assertEqual(
            self._seen(self.member),
            {"list": 2, "detail": ["Open cam", "Locked cam"],
             "category": ["Open cam", "Locked cam"], "children": [("4K", 1)],
             "search": ["4K"]},
        )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ManageCategoryApiTests(APITestCase):
    """Admin category management (#78): /api/manage/categories/."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from catalog.models import Category

        self.Category = Category
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        self.lender = User.objects.create_user(username="lena")
        PoolMembership.objects.create(user=self.lender, resource_pool=pool)
        self.borrower = User.objects.create_user(username="alice")
        self.root = Category.objects.create(name="Cameras", position=0)
        self.child = Category.objects.create(name="Video", parent=self.root, position=0)
        self.other = Category.objects.create(name="Audio", position=1)
        self.url = "/api/manage/categories/"

    def test_permissions(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.lender)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(
            self.client.get(f"{self.url}{self.root.id}/").status_code, 200
        )
        for method, url, data in (
            ("post", self.url, {"name": "X"}),
            ("patch", f"{self.url}{self.root.id}/", {"name": "X"}),
            ("delete", f"{self.url}{self.other.id}/", None),
            ("post", f"{self.url}reorder/", {"order": [self.other.id, self.root.id]}),
        ):
            res = getattr(self.client, method)(url, data, format="json")
            self.assertEqual(res.status_code, 403, (method, url))

    def test_list_is_flat_tree_with_path_and_depth(self):
        self.client.force_login(self.admin)
        rows = self.client.get(self.url).json()
        self.assertIsInstance(rows, list)  # not paginated
        self.assertEqual(
            [(r["name"], r["parent"], r["depth"], r["path"]) for r in rows],
            [
                ("Cameras", None, 0, ["Cameras"]),
                ("Video", self.root.id, 1, ["Cameras", "Video"]),
                ("Audio", None, 0, ["Audio"]),
            ],
        )
        for key in (
            "name_de", "name_en", "description_de", "description_en", "image",
            "position", "sections", "products", "product_order", "product_count",
            "child_count",
        ):
            self.assertIn(key, rows[0])
        self.assertEqual(rows[0]["child_count"], 1)

    def test_list_query_count_is_flat(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_login(self.admin)
        pt = ProductType.objects.create(name="T")

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.url)
            return len(ctx.captured_queries)

        small = count()
        for i in range(5):
            c = self.Category.objects.create(name=f"N{i}", parent=self.child)
            Product.objects.create(product_type=pt, title=f"P{i}").categories.add(c)
        self.assertEqual(count(), small)

    def test_search_keeps_paths(self):
        self.client.force_login(self.admin)
        rows = self.client.get(self.url, {"search": "vid"}).json()
        self.assertEqual([r["path"] for r in rows], [["Cameras", "Video"]])

    def test_create_appends_among_siblings_and_validates_parent(self):
        self.client.force_login(self.admin)
        res = self.client.post(
            self.url, {"name_de": "Foto", "parent": self.root.id}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["position"], 1)
        self.assertEqual(res.data["path"], ["Cameras", "Foto"])
        top = self.client.post(self.url, {"name": "Licht"}, format="json")
        self.assertEqual(top.data["position"], 2)
        # Self / descendant / trashed parent are refused.
        bad_self = self.client.patch(
            f"{self.url}{self.root.id}/", {"parent": self.root.id}, format="json"
        )
        self.assertEqual(bad_self.status_code, 400)
        bad_desc = self.client.patch(
            f"{self.url}{self.root.id}/", {"parent": self.child.id}, format="json"
        )
        self.assertEqual(bad_desc.status_code, 400)
        self.other.soft_delete(None)
        bad_trashed = self.client.patch(
            f"{self.url}{self.child.id}/", {"parent": self.other.id}, format="json"
        )
        self.assertEqual(bad_trashed.status_code, 400)

    def test_moving_appends_to_new_siblings(self):
        self.client.force_login(self.admin)
        res = self.client.patch(
            f"{self.url}{self.other.id}/", {"parent": self.root.id}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["position"], 1)
        self.assertEqual(res.data["depth"], 1)

    def test_sections_only_for_top_level(self):
        section = Section.objects.create(title="Rec")
        self.client.force_login(self.admin)
        ok = self.client.patch(
            f"{self.url}{self.root.id}/", {"sections": [section.id]}, format="json"
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(ok.data["sections"], [section.id])
        bad = self.client.patch(
            f"{self.url}{self.child.id}/", {"sections": [section.id]}, format="json"
        )
        self.assertEqual(bad.status_code, 400)
        # A category in a section can't get a parent.
        moved = self.client.patch(
            f"{self.url}{self.root.id}/", {"parent": self.other.id}, format="json"
        )
        self.assertEqual(moved.status_code, 400)
        both = self.client.patch(
            f"{self.url}{self.root.id}/",
            {"parent": self.other.id, "sections": []},
            format="json",
        )
        self.assertEqual(both.status_code, 200, both.data)

    def test_reorder_among_siblings(self):
        third = self.Category.objects.create(name="Licht", position=2)
        sub2 = self.Category.objects.create(name="Foto", parent=self.root, position=1)
        self.client.force_login(self.admin)
        res = self.client.post(
            f"{self.url}reorder/",
            {"parent": None, "order": [third.id, self.root.id, self.other.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        names = [r["name"] for r in self.client.get(self.url).json() if r["depth"] == 0]
        self.assertEqual(names, ["Licht", "Cameras", "Audio"])
        res = self.client.post(
            f"{self.url}reorder/",
            {"parent": self.root.id, "order": [sub2.id, self.child.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.child.refresh_from_db()
        sub2.refresh_from_db()
        self.assertEqual((sub2.position, self.child.position), (0, 1))
        for payload in (
            {"parent": self.root.id, "order": [sub2.id]},  # incomplete
            {"order": [self.child.id, sub2.id]},  # parent missing → top level
            {"parent": "x", "order": [sub2.id, self.child.id]},
        ):
            res = self.client.post(f"{self.url}reorder/", payload, format="json")
            self.assertEqual(res.status_code, 400, payload)

    def test_product_order(self):
        pt = ProductType.objects.create(name="T")
        p1 = Product.objects.create(product_type=pt, title="B")
        p2 = Product.objects.create(product_type=pt, title="A")
        foreign = Product.objects.create(product_type=pt, title="Z")
        p1.categories.add(self.root)
        p2.categories.add(self.root)
        self.client.force_login(self.admin)
        url = f"{self.url}{self.root.id}/"
        self.assertEqual(
            self.client.get(url).data["products"],
            [{"id": p2.id, "title": "A"}, {"id": p1.id, "title": "B"}],
        )
        res = self.client.patch(
            url, {"product_order": [p1.id, foreign.id, p1.id, 99999]}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["product_order"], [p1.id])
        self.assertEqual([p["id"] for p in res.data["products"]], [p1.id, p2.id])
        self.assertEqual(res.data["product_count"], 2)

    def test_image_upload(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (8, 8), (10, 120, 200)).save(buffer, format="PNG")
        upload = SimpleUploadedFile("c.png", buffer.getvalue(), content_type="image/png")
        self.client.force_login(self.admin)
        res = self.client.post(
            f"{self.url}{self.root.id}/image/", {"image": upload}, format="multipart"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("/categories/", res.data["image"])
        cleared = self.client.delete(f"{self.url}{self.root.id}/image/")
        self.assertIsNone(cleared.data["image"])
        # image is read-only in JSON
        res = self.client.patch(
            f"{self.url}{self.root.id}/", {"image": "x.png", "position": 9}, format="json"
        )
        self.root.refresh_from_db()
        self.assertFalse(self.root.image)
        self.assertEqual(self.root.position, 0)

    def test_destroy_refused_with_live_children(self):
        pt = ProductType.objects.create(name="T")
        product = Product.objects.create(product_type=pt, title="A")
        product.categories.add(self.child)
        self.client.force_login(self.admin)
        res = self.client.delete(f"{self.url}{self.root.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            self.client.delete(f"{self.url}{self.child.id}/").status_code, 204
        )
        self.assertTrue(self.Category.all_objects.get(pk=self.child.pk).is_trashed)
        # Trashed children don't block (purge order handles them).
        self.assertEqual(
            self.client.delete(f"{self.url}{self.root.id}/").status_code, 204
        )


class ManageSectionCategoryApiTests(APITestCase):
    """Sections pick and order top-level categories (#78)."""

    def setUp(self):
        from catalog.models import Category

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.a = Category.objects.create(name="A")
        self.b = Category.objects.create(name="B")
        self.sub = Category.objects.create(name="Sub", parent=self.a)

    def test_categories_and_order(self):
        res = self.client.post(
            "/api/manage/sections/",
            {"title": "S", "categories": [self.b.id, self.a.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["categories"], [self.b.id, self.a.id])
        self.assertEqual(res.data["category_count"], 2)
        section = Section.objects.get(pk=res.data["id"])
        self.assertEqual(section.category_order, [self.b.id, self.a.id])
        res = self.client.patch(
            f"/api/manage/sections/{section.id}/",
            {"categories": [self.a.id, self.b.id]},
            format="json",
        )
        self.assertEqual(res.data["categories"], [self.a.id, self.b.id])
        section.refresh_from_db()
        self.assertEqual(section.category_order, [self.a.id, self.b.id])

    def test_rejects_sub_category(self):
        res = self.client.post(
            "/api/manage/sections/",
            {"title": "S", "categories": [self.sub.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("categories", res.data)


class ManageProductCategoriesTests(APITestCase):
    """The product manage serializer carries ``categories`` (ids, #78)."""

    def test_round_trip(self):
        from catalog.models import Category

        admin = User.objects.create_user(username="boss", is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        a = Category.objects.create(name="A")
        b = Category.objects.create(name="B", parent=a)
        pt = ProductType.objects.create(name="T")
        res = self.client.post(
            "/api/manage/products/",
            {"title": "P", "product_type": pt.id, "categories": [b.id, a.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(sorted(res.data["categories"]), sorted([a.id, b.id]))
        pid = res.data["id"]
        res = self.client.patch(
            f"/api/manage/products/{pid}/", {"categories": [a.id]}, format="json"
        )
        self.assertEqual(res.data["categories"], [a.id])
        self.assertEqual(
            list(Product.objects.get(pk=pid).categories.all()), [a]
        )
        # Omitting categories leaves them untouched.
        self.client.patch(f"/api/manage/products/{pid}/", {"title": "Q"}, format="json")
        self.assertEqual(list(Product.objects.get(pk=pid).categories.all()), [a])

    def test_write_keeps_links_to_trashed_categories(self):
        from catalog.models import Category

        admin = User.objects.create_user(username="boss", is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        a = Category.objects.create(name="A")
        b = Category.objects.create(name="B")
        c = Category.objects.create(name="C")
        pt = ProductType.objects.create(name="T")
        product = Product.objects.create(title="P", product_type=pt)
        product.categories.set([a, b])
        b.soft_delete(admin)
        res = self.client.patch(
            f"/api/manage/products/{product.id}/", {"categories": [c.id]}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        linked = set(Category.all_objects.filter(products=product).values_list("id", flat=True))
        self.assertEqual(linked, {c.id, b.id})
        Category.all_objects.get(pk=b.pk).restore()
        res = self.client.get(f"/api/manage/products/{product.id}/")
        self.assertEqual(sorted(res.data["categories"]), sorted([b.id, c.id]))


class CategoryFixRound1Tests(CategoryShopFixture, APITestCase):
    """#78 fix round 1: empty categories hidden from borrowers, trashed
    ancestors, trashed sections in the filter, restore position."""

    def setUp(self):
        from accounts.models import AccessGroup

        self.build()
        self.locked = ResourcePool.objects.create(name="Locked", pool_id="LOCK")
        group = AccessGroup.objects.create(name="Music")
        group.pools.add(self.locked)
        self.member = User.objects.create_user(username="member")
        group.members.add(self.member)
        self.outsider = User.objects.create_user(username="outsider")
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="lena")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        self.product("Open cam", self.k4)
        # Audio and Photo only hold restricted products.
        self.product("Locked mic", self.audio, pool=self.locked)
        self.product("Locked photo", self.photo, pool=self.locked)

    def _views(self, user):
        self.client.logout()
        if user:
            self.client.force_login(user)
        listed = self.client.get("/api/sections/").json()["results"][0]
        detail = self.client.get(f"/api/sections/{self.section.id}/").json()
        cams = self.client.get(f"/api/categories/{self.cameras.id}/").json()
        audio = self.client.get(f"/api/categories/{self.audio.id}/")
        return {
            "category_count": listed["category_count"],
            "groups": [g["name"] for g in detail["categories"]],
            "children": [c["name"] for c in cams["children"]],
            "audio": audio.status_code,
        }

    def test_borrowers_do_not_see_empty_categories(self):
        for user in (None, self.outsider):
            self.assertEqual(
                self._views(user),
                {"category_count": 1, "groups": ["Cameras"],
                 "children": ["Video"], "audio": 404},
            )
        self.assertEqual(
            self._views(self.member),
            {"category_count": 2, "groups": ["Audio", "Cameras"],
             "children": ["Video", "Photo"], "audio": 200},
        )

    def test_staff_and_lenders_see_everything(self):
        from catalog.models import Category

        empty = Category.objects.create(name="Empty", position=9)
        self.section.categories.add(empty)
        for user in (self.admin, self.lender):
            seen = self._views(user)
            self.assertEqual(seen["category_count"], 3, user)
            self.assertEqual(seen["groups"], ["Audio", "Cameras", "Empty"], user)
            self.assertEqual(seen["children"], ["Video", "Photo"], user)
            self.assertEqual(seen["audio"], 200, user)
            self.assertEqual(
                self.client.get(f"/api/categories/{empty.id}/").status_code, 200
            )

    def test_trashed_ancestor_rejected_as_parent_and_product_category(self):
        from catalog.models import Category

        self.cameras.soft_delete(None)  # Video/4K stay live but unreachable
        with self.assertRaises(Exception):
            Category(name="X").validate_parent(self.video)
        self.client.force_login(self.admin)
        res = self.client.post(
            "/api/manage/categories/",
            {"name": "X", "parent": self.k4.id}, format="json",
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            "/api/manage/products/",
            {"title": "P", "product_type": self.pt.id, "categories": [self.video.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("categories", res.data)
        ok = self.client.post(
            "/api/manage/products/",
            {"title": "Q", "product_type": self.pt.id, "categories": [self.audio.id]},
            format="json",
        )
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_manage_list_paths_of_unreachable_rows_without_extra_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_login(self.admin)

        def get():
            with CaptureQueriesContext(connection) as ctx:
                rows = self.client.get("/api/manage/categories/").json()
            return len(ctx.captured_queries), rows

        small, _ = get()
        self.cameras.soft_delete(None)
        large, rows = get()
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["4K"]["path"], ["Cameras", "Video", "4K"])
        self.assertEqual(by_name["4K"]["depth"], 2)
        self.assertLessEqual(large, small)

    def test_section_filter_ignores_trashed_section(self):
        self.client.force_login(self.member)
        res = self.client.get("/api/products/", {"section": self.section.id})
        self.assertEqual(res.data["count"], 3)
        self.section.soft_delete(None)
        res = self.client.get("/api/products/", {"section": self.section.id})
        self.assertEqual(res.data["count"], 0)

    def test_restored_category_goes_to_end_of_siblings(self):
        from catalog.models import Category

        self.video.soft_delete(None)  # was position 0 among Cameras' children
        Category.objects.create(name="Drone", parent=self.cameras, position=0)
        video = Category.all_objects.get(pk=self.video.pk)
        video.restore()
        video.refresh_from_db()
        self.assertEqual(video.position, 2)  # after Photo (1) and Drone (0)
        # A restored ancestor is appended among its own siblings too.
        self.cameras.soft_delete(None)
        Category.objects.filter(pk=self.audio.pk).update(position=7)
        k4 = Category.all_objects.get(pk=self.k4.pk)
        k4.soft_delete(None)
        k4.restore()
        cameras = Category.all_objects.get(pk=self.cameras.pk)
        self.assertFalse(cameras.is_trashed)
        self.assertEqual(cameras.position, 8)


class CategoryUniqueNameTests(APITestCase):
    """Live sibling names (and live root names) are unique (#78 fix round 1):
    DB constraints, a clean 400 in the manage API, a conflict on restore, and
    migration 0054 renaming existing duplicates."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.root = self._make("Cameras")
        self.child = self._make("Video", parent=self.root)
        self.client.force_login(self.admin)

    @staticmethod
    def _make(name, **kwargs):
        return Category.objects.create(name=name, name_de=name, name_en=name, **kwargs)

    def test_db_rejects_live_duplicates(self):
        from django.db import IntegrityError, transaction

        for kwargs in ({"name": "Cameras"}, {"name": "Video", "parent": self.root}):
            with self.subTest(**kwargs):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Category.objects.create(**kwargs)

    def test_same_name_allowed_elsewhere_and_next_to_trashed(self):
        Category.objects.create(name="Video")  # root, other level
        Category.objects.create(name="Cameras", parent=self.root)
        self.child.soft_delete(None)
        Category.objects.create(name="Video", parent=self.root)
        self.assertEqual(Category.all_objects.filter(name="Video").count(), 3)

    def test_manage_api_returns_400_on_duplicate(self):
        url = "/api/manage/categories/"
        res = self.client.post(url, {"name_de": "Cameras"}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertTrue(any(key.startswith("name") for key in res.json()), res.json())
        res = self.client.post(
            url, {"name_de": "Video", "parent": self.root.id}, format="json"
        )
        self.assertEqual(res.status_code, 400, res.content)
        other = self._make("Audio")
        res = self.client.patch(f"{url}{other.id}/", {"name_de": "Cameras"}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        # Moving a category next to a sibling of the same name is refused too.
        video2 = self._make("Video")
        res = self.client.patch(f"{url}{video2.id}/", {"parent": self.root.id}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        # A distinct name still works, and a root's name is fine one level down.
        res = self.client.post(url, {"name_de": "Lights"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        res = self.client.post(
            url, {"name_de": "Cameras", "name_en": "Cameras", "parent": self.root.id},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        # Same name next to a trashed sibling is fine too.
        self.child.soft_delete(None)
        res = self.client.post(
            url, {"name_de": "Video", "parent": self.root.id}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)

    def test_restore_conflict_is_reported(self):
        self.child.soft_delete(None)
        Category.objects.create(name="Video", parent=self.root)
        res = self.client.post(f"/api/manage/trash/category/{self.child.id}/restore/")
        self.assertEqual(res.status_code, 409, res.content)
        self.assertIn("detail", res.json())
        self.assertTrue(Category.all_objects.get(pk=self.child.pk).is_trashed)

    def test_restore_conflict_of_trashed_ancestor_rolls_back(self):
        self.child.soft_delete(None)
        self.root.soft_delete(None)
        Category.objects.create(name="Cameras")
        res = self.client.post(f"/api/manage/trash/category/{self.child.id}/restore/")
        self.assertEqual(res.status_code, 409, res.content)
        self.assertTrue(Category.all_objects.get(pk=self.child.pk).is_trashed)
        self.assertTrue(Category.all_objects.get(pk=self.root.pk).is_trashed)

    def test_migration_renames_existing_duplicates(self):
        import importlib

        from django.apps import apps
        from django.db import connection

        module = importlib.import_module("catalog.migrations.0054_dedupe_category_names")
        # Dropped inside the test transaction (PostgreSQL DDL is
        # transactional), so the rollback brings them back.
        constraints = list(Category._meta.constraints)
        with connection.schema_editor() as editor:
            for constraint in constraints:
                editor.remove_constraint(Category, constraint)
        Category.objects.create(name="Cameras", position=5)
        Category.objects.create(name="Cameras (2)")  # suffix already taken
        third = Category.objects.create(name="Cameras", position=9)
        Category.objects.create(name="Video", parent=self.root)
        trashed = Category.objects.create(name="Video", parent=self.root)
        trashed.soft_delete(None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            module.forwards(apps, None)
        names = sorted(
            Category.all_objects.filter(parent__isnull=True)
            .rewrite(False).values_list("name", flat=True)
        )
        self.assertEqual(
            names, ["Cameras", "Cameras (2)", "Cameras (3)", "Cameras (4)"]
        )
        self.root.refresh_from_db()
        self.assertEqual(self.root.name, "Cameras")  # first by position wins
        third.refresh_from_db()
        self.assertEqual((third.name, third.name_en), ("Cameras (4)", "Cameras (4)"))
        self.assertEqual(
            sorted(
                Category.objects.filter(parent=self.root)
                .rewrite(False).values_list("name", flat=True)
            ),
            ["Video", "Video (2)"],
        )
        self.assertEqual(Category.all_objects.get(pk=trashed.pk).name, "Video")
        self.assertIn("Cameras (3)", out.getvalue())


class ProductRichTextTests(TestCase):
    """#98: product description and return info are rich HTML — sanitized on
    save and via the manage API, carried in the ZIP archive (rich images)
    and seen by ``cleanup_rich_images``."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.pt = ProductType.objects.create(name="Rich-Cam")

    def _png(self, colour=1):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (colour * 20, 10, 10)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_rich_fields_cover_all_language_columns(self):
        self.assertEqual(
            set(Product.rich_fields),
            {"description", "description_de", "description_en",
             "return_info", "return_info_de", "return_info_en"},
        )

    def test_model_save_sanitizes(self):
        product = Product.objects.create(
            product_type=self.pt, title="R1",
            description_de='<p onclick="x()">a</p><script>b</script>',
            return_info_en="<p>ok</p><script>bad()</script>",
        )
        product.refresh_from_db()
        self.assertEqual(product.description_de, "<p>a</p>")
        self.assertEqual(product.return_info_en, "<p>ok</p>")

    def test_manage_serializer_sanitizes(self):
        admin = User.objects.create_user(username="richadm", is_staff=True, is_superuser=True)
        product = Product.objects.create(product_type=self.pt, title="R2")
        self.client.force_login(admin)
        res = self.client.patch(
            f"/api/manage/products/{product.id}/",
            {"description_de": '<p>x</p><img src="x" onerror="y()">',
             "return_info_de": "<h2>Check</h2><script>z()</script>"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("onerror", res.json()["description_de"])
        self.assertEqual(res.json()["return_info_de"], "<h2>Check</h2>")

    def test_cleanup_keeps_images_referenced_by_products(self):
        from datetime import timedelta as _td
        import os

        from django.core.files.base import ContentFile

        Product.objects.create(
            product_type=self.pt, title="R3",
            description_en='<p><img src="/media/rich/prod.png"></p>',
            return_info_de='<p><img src="/media/rich/ret.png"></p>',
        )
        for name in ("prod.png", "ret.png", "orphan.png"):
            default_storage.save(f"rich/{name}", ContentFile(b"x"))
            ts = (timezone.now() - _td(days=30)).timestamp()
            os.utime(default_storage.path(f"rich/{name}"), (ts, ts))
        call_command("cleanup_rich_images", stdout=io.StringIO())
        self.assertTrue(default_storage.exists("rich/prod.png"))
        self.assertTrue(default_storage.exists("rich/ret.png"))
        self.assertFalse(default_storage.exists("rich/orphan.png"))

    def test_transfer_round_trip_carries_product_rich_images(self):
        import os
        import zipfile

        from django.core.files.base import ContentFile

        from catalog.transfer import build_archive, import_archive

        default_storage.save("rich/prod-de.png", ContentFile(self._png(1)))
        default_storage.save("rich/prod-ret.png", ContentFile(self._png(2)))
        Product.objects.create(
            product_type=self.pt, title="R4",
            description_de='<p>de</p><p><img src="/media/rich/prod-de.png" alt=""></p>',
            return_info_en='<p><img src="/media/rich/prod-ret.png" alt=""></p>',
        )
        archive = build_archive("full")
        names = set(zipfile.ZipFile(io.BytesIO(archive)).namelist())
        self.assertIn("media/rich/prod-de.png", names)
        self.assertIn("media/rich/prod-ret.png", names)

        shutil.rmtree(self.media_root)
        os.makedirs(self.media_root)
        import_archive(io.BytesIO(archive))
        self.assertTrue(default_storage.exists("rich/prod-de.png"))
        self.assertTrue(default_storage.exists("rich/prod-ret.png"))
        product = Product.objects.get(title="R4")
        self.assertIn('src="/media/rich/prod-de.png"', product.description_de)
        self.assertIn('src="/media/rich/prod-ret.png"', product.return_info_en)

    def test_transfer_import_renamed_image_rewrites_product_html(self):
        from django.core.files.base import ContentFile

        from catalog.transfer import build_archive, import_archive

        default_storage.save("rich/prod-x.png", ContentFile(self._png(3)))
        Product.objects.create(
            product_type=self.pt, title="R5",
            description_en='<p><img src="/media/rich/prod-x.png" alt=""></p>',
        )
        archive = build_archive("full")
        default_storage.delete("rich/prod-x.png")
        default_storage.save("rich/prod-x.png", ContentFile(b"different"))
        import_archive(io.BytesIO(archive))
        product = Product.objects.get(title="R5")
        self.assertNotIn("/media/rich/prod-x.png", product.description_en)
        self.assertIn('src="/media/rich/prod-x', product.description_en)

    def test_transfer_import_converts_plain_text_from_old_archive(self):
        import json
        import zipfile

        from catalog.transfer import build_archive, import_archive

        Product.objects.create(product_type=self.pt, title="R6")
        archive = build_archive("full")
        zin = zipfile.ZipFile(io.BytesIO(archive))
        manifest = json.loads(zin.read("manifest.json"))
        row = next(p for p in manifest["products"] if p["title"] == "R6")
        row["description_de"] = "Zeile 1\nZeile 2 & <b>"
        row["return_info_de"] = "Prüfen"
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zout:
            for item in zin.infolist():
                data = json.dumps(manifest) if item.filename == "manifest.json" else zin.read(item.filename)
                zout.writestr(item, data)
        import_archive(io.BytesIO(out.getvalue()))
        product = Product.objects.get(title="R6")
        self.assertEqual(product.description_de, "<p>Zeile 1<br>Zeile 2 &amp; &lt;b&gt;</p>")
        self.assertEqual(product.return_info_de, "<p>Prüfen</p>")


class ProductRichTextMigrationTests(TransactionTestCase):
    """#98: migration 0057 converts plain-text product descriptions and return
    info (bare + de/en columns) to HTML. Runs the real migration via the
    executor against historical models (no modeltranslation, no sanitizing
    save())."""

    BEFORE = ("catalog", "0056_remove_type_navigation")
    AFTER = ("catalog", "0057_product_rich_text")

    def _executor(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        return MigrationExecutor(connection)

    def _migrate(self, target):
        executor = self._executor()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            executor.migrate([target])
        return out.getvalue()

    def setUp(self):
        self._migrate(self.BEFORE)
        apps = self._executor().loader.project_state(self.BEFORE).apps
        self.Product = apps.get_model("catalog", "Product")
        PT = apps.get_model("catalog", "ProductType")
        self.pt = PT.objects.create(name="Migr-PT", name_de="Migr-PT")

    def tearDown(self):
        executor = self._executor()
        with contextlib.redirect_stdout(io.StringIO()):
            executor.migrate(executor.loader.graph.leaf_nodes())

    def _product(self, title, **fields):
        return self.Product.objects.create(
            product_type=self.pt, title=title, title_de=title, **fields
        ).pk

    def _row(self, pk):
        return self.Product._base_manager.filter(pk=pk).values(
            "description", "description_de", "description_en",
            "return_info", "return_info_de", "return_info_en",
        ).get()

    def test_converts_mixed_columns(self):
        html = "<p>Schon <strong>HTML</strong></p>"
        pk = self._product(
            "M1",
            description="Bare <b> & 'q' \"d\"",
            description_de="Achtung <script>alert(1)</script> & Co\nZeile 2\n\nAbsatz 2",
            description_en=html,
            return_info="",
            return_info_de="Deckel\nAkku",
            return_info_en=None,
        )
        out = self._migrate(self.AFTER)
        self.assertIn("Converted texts of 1 product(s)", out)
        row = self._row(pk)
        self.assertEqual(row["description"], self._expected_bare)
        self.assertEqual(
            row["description_de"],
            "<p>Achtung &lt;script&gt;alert(1)&lt;/script&gt; &amp; Co<br>Zeile 2</p>"
            "<p>Absatz 2</p>",
        )
        self.assertEqual(row["description_en"], html)  # existing HTML untouched
        self.assertEqual(row["return_info"], "")  # empty skipped
        self.assertEqual(row["return_info_de"], "<p>Deckel<br>Akku</p>")
        self.assertIsNone(row["return_info_en"])

    @property
    def _expected_bare(self):
        from catalog.richtext import plain_to_html

        return plain_to_html("Bare <b> & 'q' \"d\"")

    def test_trashed_rows_converted(self):
        pk = self._product("M2", description_en="Line\n\n\nPara", deleted_at=timezone.now())
        self._migrate(self.AFTER)
        self.assertEqual(self._row(pk)["description_en"], "<p>Line</p><p>Para</p>")

    def test_second_run_is_byte_identical(self):
        import importlib

        pk = self._product(
            "M3",
            description_de="Quotes 'single' \"double\" & amp <tag>\nnext",
            return_info_en="It's \"fine\" & <ok>\n\nPara 2",
            description="Bare 'x' & \"y\"",
        )
        self._migrate(self.AFTER)
        first = self._row(pk)
        self.assertIn("&amp;", first["description_de"])
        self.assertNotIn("<tag>", first["description_de"])
        mod = importlib.import_module("catalog.migrations.0057_product_rich_text")
        apps = self._executor().loader.project_state(self.AFTER).apps
        with contextlib.redirect_stdout(io.StringIO()) as out:
            mod.forwards(apps, None)
        self.assertEqual(self._row(pk), first)
        self.assertEqual(out.getvalue(), "")


class SuggestCategoriesTests(APITestCase):
    """#98: AI suggests up to 3 existing categories for a product."""

    url = "/api/manage/products/suggest-categories/"

    def setUp(self):
        self.admin = User.objects.create_user(
            username="sugcatadm", is_staff=True, is_superuser=True
        )
        self.video = Category.objects.create(name="Video")
        self.cams = Category.objects.create(name="Kameras", parent=self.video)
        self.audio = Category.objects.create(name="Audio")
        self.trashed = Category.objects.create(name="Alt")
        self.trashed.soft_delete()
        self.pt = ProductType.objects.create(name="Kamera-Typ")

    def _post(self, data=None, user=None):
        self.client.force_login(user or self.admin)
        return self.client.post(
            self.url,
            data if data is not None else {"title": "Canon EOS R6"},
            format="json",
        )

    @override_settings(AI_PROVIDER="none")
    def test_503_when_disabled(self):
        self.assertEqual(self._post().status_code, 503)

    @override_settings(**_AI_ON)
    def test_borrower_forbidden_and_lender_allowed(self):
        borrower = User.objects.create_user(username="sugcatb")
        self.assertEqual(self._post(user=borrower).status_code, 403)
        lender = User.objects.create_user(username="sugcatl")
        pool = ResourcePool.objects.create(name="SugPool", pool_id="sugpool")
        PoolMembership.objects.create(user=lender, resource_pool=pool)
        with patch("catalog.views.ai.chat_json", return_value={"suggestions": []}):
            self.assertEqual(self._post(user=lender).status_code, 200)

    def test_anonymous_rejected(self):
        res = self.client.post(self.url, {"title": "x"}, format="json")
        self.assertIn(res.status_code, (401, 403))

    @override_settings(**_AI_ON)
    def test_400_when_no_text(self):
        res = self._post({"title": " ", "description": "<p> </p>"})
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_400_unknown_product_type(self):
        res = self._post({"title": "Cam", "product_type": 999999})
        self.assertEqual(res.status_code, 400)

    @override_settings(**_AI_ON)
    def test_400_boolean_product_type(self):
        for value in (True, False):
            with patch("catalog.views.ai.chat_json") as chat:
                res = self._post({"title": "Cam", "product_type": value})
            self.assertEqual(res.status_code, 400, value)
            chat.assert_not_called()

    @override_settings(**_AI_ON)
    def test_valid_suggestions_with_paths(self):
        reply = {"suggestions": [
            {"id": self.cams.id, "reason": "Eine Kamera."},
            {"id": str(self.video.id), "reason": "Videotechnik"},
        ]}
        with patch("catalog.views.ai.chat_json", return_value=reply) as chat:
            res = self._post({
                "title": "Canon EOS R6",
                "short_description": "Vollformat",
                "description": "<p>Eine <strong>Kamera</strong></p>",
                "product_type": self.pt.id,
            })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"suggestions": [
            {"id": self.cams.id, "path": "Video › Kameras", "reason": "Eine Kamera."},
            {"id": self.video.id, "path": "Video", "reason": "Videotechnik"},
        ]})
        system, user = chat.call_args[0]
        self.assertIn("Video › Kameras", user)
        self.assertIn(str(self.cams.id), user)
        self.assertNotIn("Alt", user)  # trashed category not offered
        self.assertIn("Kamera-Typ", user)
        self.assertIn("Eine Kamera", user)
        self.assertNotIn("<strong>", user)  # HTML stripped to text

    @override_settings(**_AI_ON)
    def test_unknown_trashed_duplicate_dropped_and_capped(self):
        reply = {"suggestions": [
            {"id": 999999, "reason": "x"},
            {"id": self.trashed.id, "reason": "x"},
            {"id": self.cams.id, "reason": "a"},
            {"id": self.cams.id, "reason": "dup"},
            {"id": True, "reason": "bool"},
            {"id": self.video.id},
            {"id": self.audio.id, "reason": 5},
            {"id": self.audio.id, "reason": "late"},
        ]}
        extra = Category.objects.create(name="Licht")
        reply["suggestions"].append({"id": extra.id, "reason": "over cap"})
        with patch("catalog.views.ai.chat_json", return_value=reply):
            res = self._post()
        ids = [s["id"] for s in res.json()["suggestions"]]
        self.assertEqual(ids, [self.cams.id, self.video.id, self.audio.id])
        self.assertEqual(res.json()["suggestions"][1]["reason"], "")

    @override_settings(**_AI_ON)
    def test_malformed_output_gives_empty_list(self):
        for reply in (None, [], "text", {"suggestions": "x"}, {"suggestions": [1, "a", None]},
                      {"other": []}):
            with patch("catalog.views.ai.chat_json", return_value=reply):
                res = self._post()
            self.assertEqual(res.status_code, 200, reply)
            self.assertEqual(res.json(), {"suggestions": []}, reply)

    @override_settings(**_AI_ON)
    def test_502_on_ai_error(self):
        from basicbar_integrations.ai import AIError

        with patch("catalog.views.ai.chat_json", side_effect=AIError("boom")):
            self.assertEqual(self._post().status_code, 502)

    @override_settings(**_AI_ON)
    def test_no_categories_skips_ai(self):
        for c in (self.cams, self.video, self.audio):
            c.soft_delete()
        with patch("catalog.views.ai.chat_json") as chat:
            res = self._post()
        self.assertEqual(res.json(), {"suggestions": []})
        chat.assert_not_called()

    @override_settings(**_AI_ON)
    def test_input_is_capped(self):
        with patch("catalog.views.ai.chat_json", return_value={"suggestions": []}) as chat:
            res = self._post({"title": "T" * 5000, "description": "D" * 50000})
        self.assertEqual(res.status_code, 200)
        _, user = chat.call_args[0]
        self.assertLess(len(user), 10000)

    @override_settings(**_AI_ON)
    def test_reason_language_follows_request(self):
        with patch("catalog.views.ai.chat_json", return_value={"suggestions": []}) as chat:
            self.client.force_login(self.admin)
            self.client.post(self.url, {"title": "x"}, format="json", HTTP_ACCEPT_LANGUAGE="en")
        system, _ = chat.call_args[0]
        self.assertIn("English", system)


class ProductHtmlSearchTests(APITestCase):
    """#98: descriptions are HTML — search matches their visible text, not
    tag names or entity spellings (shop search, shop list, manage list)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="htmlsearch", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        pt = ProductType.objects.create(name="HS-PT")
        pool = ResourcePool.objects.create(name="HS-Pool", pool_id="hs-pool")
        self.tags = Product.objects.create(
            product_type=pt, title="Alpha",
            description_de="<ul><li>Zeile</li></ul><p>eins<br>zwei</p>",
            description_en="<ul><li>Line</li></ul><p>one<br>two</p>",
        )
        self.rnd = Product.objects.create(
            product_type=pt, title="Beta",
            description_de="<p>Für R&amp;D Labore</p>",
            description_en="<p>For R&amp;D labs</p>",
        )
        for i, product in enumerate((self.tags, self.rnd)):
            Resource.objects.create(
                product=product, resource_pool=pool,
                inventory_number=f"HS-{i}", qr_code_id=f"HS-QR-{i}",
            )

    def _ids(self, query):
        shop = {p["id"] for p in self.client.get("/api/search/", {"q": query}).json()["products"]}
        listed = self.client.get("/api/products/", {"search": query}).json()
        listed = listed["results"] if isinstance(listed, dict) else listed
        manage = self.client.get("/api/manage/products/", {"search": query}).json()["results"]
        return shop, {p["id"] for p in listed}, {p["id"] for p in manage}

    def test_tag_names_do_not_match(self):
        for query in ("br", "ul", "<p>"):
            with self.subTest(query=query):
                self.assertEqual(self._ids(query), (set(), set(), set()))

    def test_ampersand_matches_escaped_text(self):
        for found in self._ids("R&D"):
            self.assertEqual(found, {self.rnd.id})

    def test_words_and_titles_still_match(self):
        # Requests run in English (no LocaleMiddleware): the _en column.
        for found in self._ids("two"):
            self.assertEqual(found, {self.tags.id})
        for found in self._ids("Beta"):
            self.assertEqual(found, {self.rnd.id})

    def test_manage_search_requires_every_term(self):
        res = self.client.get("/api/manage/products/", {"search": "Alpha two"}).json()
        self.assertEqual([p["id"] for p in res["results"]], [self.tags.id])
        res = self.client.get("/api/manage/products/", {"search": "Alpha labs"}).json()
        self.assertEqual(res["results"], [])


class DurationLimitsShopTests(APITestCase):
    """Product detail exposes effective limits overall and per pool (#109)."""

    def setUp(self):
        self.pt = ProductType.objects.create(name="DurShopType", attribute_schema=[])
        self.pool_a = ResourcePool.objects.create(
            name="DigiLab", pool_id="DUR-A", default_max_days=7, position=0,
        )
        self.pool_b = ResourcePool.objects.create(
            name="Videostudio", pool_id="DUR-B", position=1,
        )
        self.product = Product.objects.create(
            product_type=self.pt, title="DurShopCam", lending_type="days",
        )
        self._n = 0

    def _unit(self, pool, **kwargs):
        self._n += 1
        return Resource.objects.create(
            product=self.product, resource_pool=pool,
            inventory_number=f"DS-{self._n}", qr_code_id=f"QR-DS-{self._n}", **kwargs,
        )

    def _detail(self):
        res = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(res.status_code, 200)
        return res.data

    def test_widest_range_and_per_pool_ranges(self):
        self._unit(self.pool_a)
        self._unit(self.pool_b)
        data = self._detail()
        # Videostudio has no limit → overall no limit.
        self.assertIsNone(data["effective_max_duration"])
        self.assertIsNone(data["effective_min_duration"])
        self.assertEqual(
            data["duration_limits_by_pool"],
            [
                {"pool_id": self.pool_a.id, "pool_name": "DigiLab", "min": None, "max": 7},
                {"pool_id": self.pool_b.id, "pool_name": "Videostudio", "min": None, "max": None},
            ],
        )

    def test_device_override_widens_its_pool(self):
        self.product.min_duration, self.product.max_duration = 2, 3
        self.product.save()
        self._unit(self.pool_a)
        self._unit(self.pool_a, max_duration=10, min_duration=1)
        data = self._detail()
        self.assertEqual(
            (data["effective_min_duration"], data["effective_max_duration"]), (1, 10)
        )
        self.assertEqual(
            data["duration_limits_by_pool"],
            [{"pool_id": self.pool_a.id, "pool_name": "DigiLab", "min": 1, "max": 10}],
        )

    def test_unbookable_units_are_ignored(self):
        self._unit(self.pool_a)
        self._unit(self.pool_b, status=Resource.Status.DEFECTIVE)
        data = self._detail()
        self.assertEqual(data["effective_max_duration"], 7)
        self.assertEqual(len(data["duration_limits_by_pool"]), 1)

    def test_hidden_pools_are_ignored(self):
        from accounts.models import AccessGroup

        self._unit(self.pool_a)
        self._unit(self.pool_b)
        group = AccessGroup.objects.create(name="Staff only")
        group.pools.add(self.pool_b)
        data = self._detail()  # anonymous → only DigiLab is visible
        self.assertEqual(data["effective_max_duration"], 7)
        self.assertEqual(
            [p["pool_id"] for p in data["duration_limits_by_pool"]], [self.pool_a.id]
        )

    def test_detail_query_count_independent_of_device_count(self):
        self._unit(self.pool_a)
        self._unit(self.pool_b)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as few:
            self._detail()
        for _ in range(15):
            self._unit(self.pool_a)
            self._unit(self.pool_b, max_duration=3)
        with CaptureQueriesContext(connection) as many:
            self._detail()
        self.assertEqual(len(many), len(few))


class DurationLimitsManageTests(APITestCase):
    """Manage product/resource expose inherited values and their source (#109)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="duradmin", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.pt = ProductType.objects.create(name="DurManType", attribute_schema=[])
        self.pool_a = ResourcePool.objects.create(
            name="DigiLab", pool_id="DM-A", default_max_days=7, default_min_days=1,
            default_max_hours=4, position=0,
        )
        self.pool_b = ResourcePool.objects.create(
            name="Videostudio", pool_id="DM-B", position=1,
        )
        self.product = Product.objects.create(
            product_type=self.pt, title="DurManCam", lending_type="days",
        )
        self.unit_a = Resource.objects.create(
            product=self.product, resource_pool=self.pool_a,
            inventory_number="DM-1", qr_code_id="QR-DM-1",
        )
        Resource.objects.create(
            product=self.product, resource_pool=self.pool_b,
            inventory_number="DM-2", qr_code_id="QR-DM-2",
        )

    def test_manage_product_lists_pool_defaults(self):
        data = self.client.get(f"/api/manage/products/{self.product.id}/").data
        self.assertEqual(
            data["pool_duration_defaults"],
            [
                {"pool_id": self.pool_a.id, "pool_name": "DigiLab", "min": 1, "max": 7},
                {"pool_id": self.pool_b.id, "pool_name": "Videostudio", "min": None, "max": None},
            ],
        )
        # The unit follows the product's lending type.
        self.product.lending_type = "hours"
        self.product.save()
        data = self.client.get(f"/api/manage/products/{self.product.id}/").data
        self.assertEqual(data["pool_duration_defaults"][0]["max"], 4)
        listed = self.client.get("/api/manage/products/").data["results"]
        self.assertEqual(listed[0]["pool_duration_defaults"][0]["max"], 4)

    def test_manage_resource_shows_effective_value_and_source(self):
        url = f"/api/manage/inventory/{self.unit_a.id}/"
        data = self.client.get(url).data
        self.assertEqual(data["lending_unit"], "days")
        self.assertEqual(
            (data["effective_max_duration"], data["effective_max_duration_source"]),
            (7, "pool"),
        )
        self.assertEqual(
            (data["inherited_max_duration"], data["inherited_max_duration_source"]),
            (7, "pool"),
        )
        self.product.max_duration = 5
        self.product.save()
        data = self.client.get(url).data
        self.assertEqual(
            (data["effective_max_duration"], data["effective_max_duration_source"]),
            (5, "product"),
        )
        res = self.client.patch(url, {"max_duration": 9}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            (res.data["effective_max_duration"], res.data["effective_max_duration_source"]),
            (9, "resource"),
        )
        self.assertEqual(
            (res.data["inherited_max_duration"], res.data["inherited_max_duration_source"]),
            (5, "product"),
        )
        self.assertEqual(res.data["max_duration"], 9)
        res = self.client.patch(url, {"max_duration": None}, format="json")
        self.assertEqual(res.data["effective_max_duration_source"], "product")
        unlimited = self.client.get(
            f"/api/manage/inventory/{Resource.objects.get(inventory_number='DM-2').id}/"
        ).data
        self.assertEqual(
            (unlimited["effective_min_duration"], unlimited["effective_min_duration_source"]),
            (None, "none"),
        )

    def test_manage_resource_rejects_min_above_max_and_zero(self):
        url = f"/api/manage/inventory/{self.unit_a.id}/"
        res = self.client.patch(url, {"min_duration": 5, "max_duration": 2}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.patch(url, {"max_duration": 0}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_resource_durations_round_trip_in_zip(self):
        from catalog.transfer import build_archive, import_archive

        self.unit_a.min_duration, self.unit_a.max_duration = 2, 6
        self.unit_a.save()
        archive = build_archive("full")
        Resource.objects.filter(pk=self.unit_a.pk).update(
            min_duration=None, max_duration=None
        )
        import_archive(io.BytesIO(archive))
        self.unit_a.refresh_from_db()
        self.assertEqual((self.unit_a.min_duration, self.unit_a.max_duration), (2, 6))
