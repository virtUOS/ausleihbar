# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for the catalog app."""
import io
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone, translation
from rest_framework.test import APITestCase, APITransactionTestCase

from accounts.models import PoolMembership
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
        self.category = Category.objects.create(title="Video Cameras")
        self.category.products.add(self.product)
        self.section = Section.objects.create(title="Recording Technology")
        self.section.categories.add(self.category)
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        Resource.objects.create(
            product=self.product,
            resource_pool=self.pool,
            inventory_number="DigiLab-001",
            qr_code_id="QR-DigiLab-001",
        )

    def test_section_list(self):
        response = self.client.get("/api/sections/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["title"], "Recording Technology")
        self.assertEqual(response.data["results"][0]["category_count"], 1)

    def test_section_detail_nests_categories_and_products(self):
        response = self.client.get(f"/api/sections/{self.section.id}/")
        self.assertEqual(response.status_code, 200)
        category = response.data["categories"][0]
        self.assertEqual(category["product_count"], 1)
        self.assertEqual(category["products"][0]["title"], "Sony Alpha 7")

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
            "/api/manage/categories/",
            {"title_de": "Kameras", "title_en": "Cameras"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        cat = Category.objects.get(id=resp.data["id"])
        self.assertEqual(cat.title_de, "Kameras")
        self.assertEqual(cat.title_en, "Cameras")
        # Each language reads back its own value through the descriptor.
        with translation.override("de"):
            self.assertEqual(cat.title, "Kameras")
        with translation.override("en"):
            self.assertEqual(cat.title, "Cameras")

    def test_legacy_bare_field_still_accepted(self):
        resp = self.client.post(
            "/api/manage/categories/", {"title": "Camcorders"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_english_only_create_rejected(self):
        resp = self.client.post(
            "/api/manage/categories/", {"title_en": "Cameras"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("title_de", resp.data)

    def test_blank_translation_stored_as_null_without_collision(self):
        a = self.client.post(
            "/api/manage/categories/",
            {"title_de": "A", "title_en": ""},
            format="json",
        )
        b = self.client.post(
            "/api/manage/categories/",
            {"title_de": "B", "title_en": ""},
            format="json",
        )
        self.assertEqual((a.status_code, b.status_code), (201, 201), (a.data, b.data))
        self.assertIsNone(Category.objects.get(id=a.data["id"]).title_en)

    def test_update_one_language_leaves_the_other(self):
        cat = Category.objects.create(title_de="Alt", title_en="Old")
        resp = self.client.patch(
            f"/api/manage/categories/{cat.id}/", {"title_en": "New"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        cat.refresh_from_db()
        self.assertEqual(cat.title_en, "New")
        self.assertEqual(cat.title_de, "Alt")

    def test_clearing_canonical_on_update_is_a_clean_400(self):
        # Emptying the required canonical language must be rejected with a
        # validation error, not blow up as an IntegrityError (NOT NULL).
        cat = Category.objects.create(title_de="Alt", title_en="Old")
        resp = self.client.patch(
            f"/api/manage/categories/{cat.id}/", {"title_de": ""}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("title_de", resp.data)
        cat.refresh_from_db()
        self.assertEqual(cat.title_de, "Alt")  # unchanged


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
             "lending_type": "days", "attributes": attributes, "categories": []},
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


class ManageCategoryApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        self.p1 = Product.objects.create(product_type=pt, title="A7")
        self.p2 = Product.objects.create(product_type=pt, title="GoPro")

    def test_borrower_cannot_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/categories/").status_code, 403)

    def test_admin_crud_with_product_assignment(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/categories/",
            {"title": "Video Cameras", "products": [self.p1.id, self.p2.id]},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["product_count"], 2)
        cat_id = created.data["id"]

        # Reassign to a single product.
        patched = self.client.patch(
            f"/api/manage/categories/{cat_id}/",
            {"products": [self.p1.id]},
            format="json",
        )
        self.assertEqual(patched.data["product_count"], 1)
        self.assertEqual(patched.data["products"], [self.p1.id])

        self.assertEqual(
            self.client.delete(f"/api/manage/categories/{cat_id}/").status_code, 204
        )

    def test_create_without_products(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/manage/categories/", {"title": "Empty"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["product_count"], 0)

    def test_product_order_is_saved_and_returned(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/categories/",
            {"title": "Ordered", "products": [self.p2.id, self.p1.id]},
            format="json",
        )
        cat_id = created.data["id"]
        # Read back keeps the chosen order …
        self.assertEqual(created.data["products"], [self.p2.id, self.p1.id])
        from catalog.models import Category
        from catalog.serializers import order_by_ids

        cat = Category.objects.get(id=cat_id)
        self.assertEqual(cat.product_order, [self.p2.id, self.p1.id])
        self.assertEqual(
            [p.id for p in order_by_ids(cat.products.all(), cat.product_order)],
            [self.p2.id, self.p1.id],
        )
        # … and a reorder via PATCH updates it.
        self.client.patch(
            f"/api/manage/categories/{cat_id}/",
            {"products": [self.p1.id, self.p2.id]},
            format="json",
        )
        cat.refresh_from_db()
        self.assertEqual(cat.product_order, [self.p1.id, self.p2.id])


class ManageSectionApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.c1 = Category.objects.create(title="Video Cameras")
        self.c2 = Category.objects.create(title="Action Cameras")

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

    def test_category_and_set_order_is_saved_and_returned(self):
        from catalog.models import ProductSet, ResourcePool, Section

        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        s1 = ProductSet.objects.create(name="Kit A", resource_pool=pool)
        s2 = ProductSet.objects.create(name="Kit B", resource_pool=pool)
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/sections/",
            {
                "title": "Ordered",
                "categories": [self.c2.id, self.c1.id],
                "sets": [s2.id, s1.id],
            },
            format="json",
        )
        section_id = created.data["id"]
        # Read back keeps the chosen order for both lists …
        self.assertEqual(created.data["categories"], [self.c2.id, self.c1.id])
        self.assertEqual(created.data["sets"], [s2.id, s1.id])
        section = Section.objects.get(id=section_id)
        self.assertEqual(section.category_order, [self.c2.id, self.c1.id])
        self.assertEqual(section.set_order, [s2.id, s1.id])
        # … and a reorder via PATCH updates it.
        self.client.patch(
            f"/api/manage/sections/{section_id}/",
            {"categories": [self.c1.id, self.c2.id]},
            format="json",
        )
        section.refresh_from_db()
        self.assertEqual(section.category_order, [self.c1.id, self.c2.id])


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
        self.category = Category.objects.create(title="Video Cameras")
        self.section = Section.objects.create(title="Recording")
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
            ("categories", self.category.id, "categories/"),
            ("sections", self.section.id, "sections/"),
            ("pools", self.pool.id, "pools/"),
        ]
        for path, pk, prefix in cases:
            response = self.client.post(
                f"/api/manage/{path}/{pk}/image/",
                {"image": self._png(f"{path}.png")},
                format="multipart",
            )
            self.assertEqual(response.status_code, 200, path)
            self.assertTrue(response.data["image"], path)


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


class CatalogOrderingTests(APITestCase):
    """Manual position ordering for sections and categories (concept §1.6)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")

    def test_new_categories_are_appended_at_the_end(self):
        self.client.force_login(self.admin)
        ids = []
        for title in ("Bravo", "Alpha", "Charlie"):
            res = self.client.post(
                "/api/manage/categories/", {"title": title}, format="json"
            )
            self.assertEqual(res.status_code, 201)
            ids.append(res.json()["id"])
        # Positions follow creation order regardless of alphabetical title.
        positions = [Category.objects.get(pk=i).position for i in ids]
        self.assertEqual(positions, [0, 1, 2])

    def test_reorder_rewrites_positions_and_shop_order(self):
        c1 = Category.objects.create(title="Alpha", position=0)
        c2 = Category.objects.create(title="Bravo", position=1)
        c3 = Category.objects.create(title="Charlie", position=2)
        self.client.force_login(self.admin)
        res = self.client.post(
            "/api/manage/categories/reorder/",
            {"order": [c3.id, c1.id, c2.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        c1.refresh_from_db(); c2.refresh_from_db(); c3.refresh_from_db()
        self.assertEqual((c3.position, c1.position, c2.position), (0, 1, 2))
        # The shop list endpoint reflects the new order.
        shop = self.client.get("/api/categories/").json()
        titles = [c["title"] for c in shop["results"]]
        self.assertEqual(titles, ["Charlie", "Alpha", "Bravo"])

    def test_reorder_rejects_incomplete_id_list(self):
        c1 = Category.objects.create(title="Alpha", position=0)
        Category.objects.create(title="Bravo", position=1)
        self.client.force_login(self.admin)
        res = self.client.post(
            "/api/manage/categories/reorder/",
            {"order": [c1.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_reorder_requires_admin(self):
        c1 = Category.objects.create(title="Alpha", position=0)
        self.client.force_login(self.borrower)
        res = self.client.post(
            "/api/manage/categories/reorder/",
            {"order": [c1.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_section_categories_follow_position(self):
        c1 = Category.objects.create(title="Zeta", position=0)
        c2 = Category.objects.create(title="Alpha", position=1)
        section = Section.objects.create(title="Media", position=0)
        section.categories.add(c1, c2)
        body = self.client.get(f"/api/sections/{section.id}/").json()
        # Position (not title) drives the order within a section.
        self.assertEqual([c["title"] for c in body["categories"]], ["Zeta", "Alpha"])


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


class M2MAssignDirectionTests(APITestCase):
    """Category can pick its sections; Product can pick its categories
    (reverse-side M2M writes via the manage serializers)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.pt = ProductType.objects.create(name="Camera")
        self.section = Section.objects.create(title="Video", position=0)
        self.category = Category.objects.create(title="Cameras", position=0)
        self.product = Product.objects.create(product_type=self.pt, title="A7")

    def test_category_can_pick_sections(self):
        res = self.client.patch(
            f"/api/manage/categories/{self.category.id}/",
            {"sections": [self.section.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sections"], [self.section.id])
        # Visible from the section side too.
        self.assertIn(self.category, self.section.categories.all())

    def test_product_can_pick_categories(self):
        res = self.client.patch(
            f"/api/manage/products/{self.product.id}/",
            {"categories": [self.category.id]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["categories"], [self.category.id])
        self.assertIn(self.product, self.category.products.all())


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


class ProductCategoryFilterTests(APITestCase):
    """Admin product list filters by ?category=<id> and ?category=none."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(self.admin)
        self.pt = ProductType.objects.create(name="Camera")
        self.cat = Category.objects.create(title="Cameras", position=0)
        self.in_cat = Product.objects.create(product_type=self.pt, title="A7")
        self.cat.products.add(self.in_cat)
        self.uncat = Product.objects.create(product_type=self.pt, title="Loose item")

    def test_filter_by_category(self):
        res = self.client.get(f"/api/manage/products/?category={self.cat.id}")
        titles = [p["title"] for p in res.data["results"]]
        self.assertEqual(titles, ["A7"])

    def test_filter_no_category(self):
        res = self.client.get("/api/manage/products/?category=none")
        titles = [p["title"] for p in res.data["results"]]
        self.assertEqual(titles, ["Loose item"])

    def test_no_filter_returns_all(self):
        res = self.client.get("/api/manage/products/")
        self.assertEqual(res.data["count"], 2)


class WelcomePageTests(APITestCase):
    """Public welcome content + admin-editable Markdown text."""

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
    """Shop search across products, categories and sections (by name)."""

    def setUp(self):
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="Sony Alpha 7")
        self.category = Category.objects.create(title="Video Cameras")
        self.category.products.add(self.product)
        self.section = Section.objects.create(title="Recording Technology")
        self.section.categories.add(self.category)
        pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        Resource.objects.create(
            product=self.product, resource_pool=pool,
            inventory_number="D-1", qr_code_id="QR-D-1",
        )

    def test_category_name_returns_category_with_products(self):
        res = self.client.get("/api/search/", {"q": "Video"})
        self.assertEqual(res.status_code, 200)
        cats = res.data["categories"]
        self.assertEqual([c["title"] for c in cats], ["Video Cameras"])
        self.assertEqual([p["title"] for p in cats[0]["products"]], ["Sony Alpha 7"])

    def test_section_name_returns_section_with_content(self):
        res = self.client.get("/api/search/", {"q": "Recording"})
        secs = res.data["sections"]
        self.assertEqual([s["title"] for s in secs], ["Recording Technology"])
        self.assertEqual(secs[0]["categories"][0]["title"], "Video Cameras")
        self.assertEqual(
            [p["title"] for p in secs[0]["categories"][0]["products"]],
            ["Sony Alpha 7"],
        )

    def test_product_name_returns_product_only(self):
        res = self.client.get("/api/search/", {"q": "Sony"})
        self.assertEqual([p["title"] for p in res.data["products"]], ["Sony Alpha 7"])
        self.assertEqual(res.data["categories"], [])
        self.assertEqual(res.data["sections"], [])

    def test_empty_query_returns_empty(self):
        res = self.client.get("/api/search/", {"q": ""})
        self.assertEqual(res.data, {"sections": [], "categories": [], "products": []})


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
    """Borrower browse-by-pool, grouped by category (#14):
    /api/pools/<id>/products-grouped/."""

    def setUp(self):
        from accounts.models import AccessGroup

        pt = ProductType.objects.create(name="Camera")
        self.pool = ResourcePool.objects.create(name="Main", pool_id="MAIN")
        self.locked_pool = ResourcePool.objects.create(name="Locked", pool_id="LOCK")
        group = AccessGroup.objects.create(name="Music")
        group.pools.add(self.locked_pool)

        self.cat1 = Category.objects.create(title="C1", position=0)
        self.cat2 = Category.objects.create(title="C2", position=1)

        self.prod1 = Product.objects.create(product_type=pt, title="Prod 1")
        self.cat1.products.add(self.prod1)
        Resource.objects.create(
            product=self.prod1, resource_pool=self.pool,
            inventory_number="M-1", qr_code_id="QR-M-1",
        )

        self.prod2 = Product.objects.create(product_type=pt, title="Prod 2")
        self.cat2.products.add(self.prod2)
        Resource.objects.create(
            product=self.prod2, resource_pool=self.pool,
            inventory_number="M-2", qr_code_id="QR-M-2",
        )

        self.uncategorised = Product.objects.create(product_type=pt, title="Prod 3")
        Resource.objects.create(
            product=self.uncategorised, resource_pool=self.pool,
            inventory_number="M-3", qr_code_id="QR-M-3",
        )

        # A product elsewhere (not in this pool) must not leak into the groups.
        other_prod = Product.objects.create(product_type=pt, title="Elsewhere")
        self.cat1.products.add(other_prod)
        Resource.objects.create(
            product=other_prod, resource_pool=self.locked_pool,
            inventory_number="L-1", qr_code_id="QR-L-1",
        )

    def test_groups_ordered_by_category_position_with_trailing_other(self):
        res = self.client.get(f"/api/pools/{self.pool.id}/products-grouped/")
        self.assertEqual(res.status_code, 200)
        groups = res.json()
        self.assertEqual(len(groups), 3)

        self.assertEqual(groups[0]["category"], {"id": self.cat1.id, "title": "C1"})
        self.assertEqual([p["title"] for p in groups[0]["products"]], ["Prod 1"])

        self.assertEqual(groups[1]["category"], {"id": self.cat2.id, "title": "C2"})
        self.assertEqual([p["title"] for p in groups[1]["products"]], ["Prod 2"])

        self.assertIsNone(groups[2]["category"])
        self.assertEqual([p["title"] for p in groups[2]["products"]], ["Prod 3"])

    def test_product_in_two_categories_appears_in_both(self):
        self.cat2.products.add(self.prod1)
        groups = self.client.get(
            f"/api/pools/{self.pool.id}/products-grouped/"
        ).json()
        titles_by_cat = {
            g["category"]["title"] if g["category"] else "Other": [
                p["title"] for p in g["products"]
            ]
            for g in groups
        }
        self.assertIn("Prod 1", titles_by_cat["C1"])
        self.assertIn("Prod 1", titles_by_cat["C2"])

    def test_hidden_pool_404s(self):
        res = self.client.get(f"/api/pools/{self.locked_pool.id}/products-grouped/")
        self.assertEqual(res.status_code, 404)

    def test_empty_category_omitted(self):
        Category.objects.create(title="Empty cat", position=0)
        groups = self.client.get(
            f"/api/pools/{self.pool.id}/products-grouped/"
        ).json()
        titles = [g["category"]["title"] if g["category"] else None for g in groups]
        self.assertNotIn("Empty cat", titles)


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


class TransferTests(APITestCase):
    """Export → import round-trip of the catalog data set (catalog/transfer.py)."""

    def setUp(self):
        from catalog.models import ProductImage, ProductSet

        self.ptype = ProductType.objects.create(name="Camera")
        self.ptype.description_en = "Cameras"
        self.ptype.save()
        self.product = Product.objects.create(
            product_type=self.ptype, title="Alpha 7", lending_type="days",
            attributes={"mp": 24},
        )
        self.product.title_en = "Alpha 7"
        self.product.description_en = "A camera"
        self.product.save()
        self.p2 = Product.objects.create(product_type=self.ptype, title="GoPro")
        self.category = Category.objects.create(title="Cams")
        self.category.products.set([self.product, self.p2])
        self.category.product_order = [self.p2.id, self.product.id]
        self.category.save()
        self.section = Section.objects.create(title="Recording")
        self.section.categories.set([self.category])
        self.section.category_order = [self.category.id]
        self.section.save()
        self.set = ProductSet.objects.create(name="Video Kit")
        self.set.products.set([self.product])
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

    def test_full_roundtrip_recreates_data(self):
        import io
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        # Wipe the catalog, then import the archive back.
        Resource.objects.all().delete()
        Section.objects.all().delete()
        Category.objects.all().delete()
        ProductSet = __import__("catalog.models", fromlist=["ProductSet"]).ProductSet
        ProductSet.objects.all().delete()
        Product.objects.all().delete()
        ProductType.objects.all().delete()
        ResourcePool.objects.all().delete()

        summary = import_archive(io.BytesIO(archive))
        self.assertGreaterEqual(summary["created"].get("products", 0), 2)

        product = Product.objects.get(title="Alpha 7")
        self.assertEqual(product.title_en, "Alpha 7")
        self.assertEqual(product.attributes, {"mp": 24})
        self.assertEqual(product.product_type.name, "Camera")

        category = Category.objects.get(title="Cams")
        # product_order is remapped to the new ids, in the saved order (GoPro first).
        self.assertEqual(
            category.product_order,
            [Product.objects.get(title="GoPro").id, product.id],
        )
        section = Section.objects.get(title="Recording")
        self.assertEqual(section.category_order, [category.id])

        resource = Resource.objects.get(inventory_number="DL-1")
        self.assertEqual(resource.resource_pool.pool_id, "digilab")
        self.assertEqual(resource.product.title, "Alpha 7")
        self.assertEqual(resource.serial_number, "SN1")

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
        import io
        import json
        import zipfile
        from catalog.transfer import build_archive

        archive = build_archive("pool", pool=self.pool)
        manifest = json.loads(zipfile.ZipFile(io.BytesIO(archive)).read("manifest.json"))
        self.assertEqual([r["inventory_number"] for r in manifest["resources"]], ["DL-1"])
        self.assertEqual([p["title"] for p in manifest["products"]], ["Alpha 7"])
        self.assertEqual([p["pool_id"] for p in manifest["resource_pools"]], ["digilab"])
        # Pool scope carries no categories/sections.
        self.assertEqual(manifest["categories"], [])
        self.assertEqual(manifest["sections"], [])

    def test_dry_run_changes_nothing(self):
        import io
        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")
        Resource.objects.all().delete()
        summary = import_archive(io.BytesIO(archive), dry_run=True)
        self.assertTrue(summary.get("dry_run"))
        # Rolled back: the deleted resources were not recreated.
        self.assertEqual(Resource.objects.count(), 0)

    def test_import_restores_trashed_natural_key_match(self):
        # I2: an import whose live item's natural key matches a currently
        # TRASHED row must update+restore that row instead of trying (and
        # failing) to INSERT a duplicate and aborting the whole import.
        import io

        from catalog.transfer import build_archive, import_archive

        archive = build_archive("full")  # snapshot while "Cams" is alive.
        self.category.soft_delete(None)
        self.assertIsNone(Category.objects.filter(title="Cams").first())
        self.assertTrue(Category.all_objects.get(pk=self.category.pk).is_trashed)

        summary = import_archive(io.BytesIO(archive))

        self.assertNotIn("dry_run", summary)
        category = Category.objects.get(title="Cams")
        self.assertEqual(category.pk, self.category.pk)  # same row, restored
        self.assertFalse(category.is_trashed)
        self.assertIsNone(category.deleted_at)
        # Not duplicated.
        self.assertEqual(Category.all_objects.filter(title="Cams").count(), 1)
        self.assertEqual(summary["updated"].get("categories", 0), 1)

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
        c = Category.objects.create(title="Temp")
        c.soft_delete()
        self.assertFalse(Category.objects.filter(pk=c.pk).exists())      # hidden
        self.assertTrue(Category.all_objects.filter(pk=c.pk).exists())   # still there
        self.assertIsNotNone(Category.all_objects.get(pk=c.pk).deleted_at)

    def test_restore_makes_it_visible_again(self):
        c = Category.objects.create(title="Temp")
        c.soft_delete()
        Category.all_objects.get(pk=c.pk).restore()
        self.assertTrue(Category.objects.filter(pk=c.pk).exists())

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
        c = Category.objects.create(title="Temp2")
        c.soft_delete(user=user)
        trashed = Category.all_objects.get(pk=c.pk)
        self.assertEqual(trashed.deleted_by, user)
        self.assertTrue(trashed.is_trashed)

    def test_restore_clears_deleted_by(self):
        user = User.objects.create_user(username="deleter2", password="x")
        c = Category.objects.create(title="Temp3")
        c.soft_delete(user=user)
        restored = Category.all_objects.get(pk=c.pk)
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

    def test_delete_category_soft_deletes(self):
        category = Category.objects.create(title="Category-SD")
        resp = self.client.delete(f"/api/manage/categories/{category.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Category.objects.filter(pk=category.id).exists())
        self.assertTrue(Category.all_objects.filter(pk=category.id).exists())

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
        c = Category.objects.create(title="Gone")
        c.soft_delete(self.admin)
        rows = self.client.get("/api/manage/trash/").json()
        self.assertTrue(
            any(r["type"] == "category" and r["id"] == c.id for r in rows)
        )

    def test_restore_brings_it_back(self):
        c = Category.objects.create(title="Gone")
        c.soft_delete(self.admin)
        resp = self.client.post(f"/api/manage/trash/category/{c.id}/restore/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Category.objects.filter(pk=c.id).exists())

    def test_purge_one_hard_deletes(self):
        c = Category.objects.create(title="Gone")
        c.soft_delete(self.admin)
        resp = self.client.delete(f"/api/manage/trash/category/{c.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Category.all_objects.filter(pk=c.id).exists())

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
        resp = self.client.delete("/api/manage/trash/category/999999/")
        self.assertEqual(resp.status_code, 404)

    def test_empty_trash_purges_everything_caller_may_manage(self):
        c1 = Category.objects.create(title="Gone1")
        c1.soft_delete(self.admin)
        c2 = Category.objects.create(title="Gone2")
        c2.soft_delete(self.admin)
        resp = self.client.delete("/api/manage/trash/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Category.all_objects.filter(pk__in=[c1.id, c2.id]).exists())

    def test_purge_at_reflects_retention_days(self):
        from catalog.models import TrashSetting

        TrashSetting.load()
        setting = TrashSetting.objects.get(pk=1)
        setting.retention_days = 5
        setting.save()
        c = Category.objects.create(title="Gone")
        c.soft_delete(self.admin)
        rows = self.client.get("/api/manage/trash/").json()
        row = next(r for r in rows if r["type"] == "category" and r["id"] == c.id)
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

        other = Category.objects.create(title="Emptiable")
        other.soft_delete(self.admin)

        resp = self.client.delete("/api/manage/trash/")

        self.assertEqual(resp.status_code, 204)
        # Protected row survives, still in the trash.
        self.assertTrue(
            Resource.all_objects.filter(pk=protected_resource.pk).exists()
        )
        # Everything else was still purged.
        self.assertFalse(Category.all_objects.filter(pk=other.pk).exists())

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
        old = Category.objects.create(title="Old")
        old.soft_delete(self.admin)
        recent = Category.objects.create(title="Recent")
        recent.soft_delete(self.admin)
        # Backdate `old` beyond the 30-day window.
        Category.all_objects.filter(pk=old.pk).update(
            deleted_at=timezone.now() - timedelta(days=31)
        )
        call_command("purge_trash")
        self.assertFalse(Category.all_objects.filter(pk=old.pk).exists())
        self.assertTrue(Category.all_objects.filter(pk=recent.pk).exists())

    def test_dry_run_writes_nothing(self):
        c = Category.objects.create(title="Old")
        c.soft_delete(self.admin)
        Category.all_objects.filter(pk=c.pk).update(
            deleted_at=timezone.now() - timedelta(days=99)
        )
        call_command("purge_trash", "--dry-run")
        self.assertTrue(Category.all_objects.filter(pk=c.pk).exists())

    def test_respects_configured_retention_days(self):
        setting = TrashSetting.load()
        setting.retention_days = 5
        setting.save()
        c = Category.objects.create(title="Custom")
        c.soft_delete(self.admin)
        Category.all_objects.filter(pk=c.pk).update(
            deleted_at=timezone.now() - timedelta(days=6)
        )
        call_command("purge_trash")
        self.assertFalse(Category.all_objects.filter(pk=c.pk).exists())

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

        unprotected = Category.objects.create(title="Unprotected")
        unprotected.soft_delete(self.admin)
        Category.all_objects.filter(pk=unprotected.pk).update(deleted_at=cutoff)

        # Must not raise ProtectedError.
        call_command("purge_trash")

        self.assertTrue(
            Resource.all_objects.filter(pk=protected_resource.pk).exists()
        )
        self.assertFalse(Category.all_objects.filter(pk=unprotected.pk).exists())
