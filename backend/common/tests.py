# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

# The former AI-client tests moved with the code into the shared
# ``basicbar-integrations`` package (basicbar repo) and run in its CI.
"""Tests for the shared app."""
import json

from django.contrib import admin
from django.core.cache import cache
from django.test import Client, TestCase

from common import csp
from common.models import CspViolation

URL = "/api/csp-report/"

LEGACY = {
    "csp-report": {
        "document-uri": "https://ausleihbar.example.org/products/5?q=secret#x",
        "effective-directive": "script-src-elem",
        "violated-directive": "script-src-elem",
        "blocked-uri": "https://evil.example:8443/x.js?token=1",
        "script-sample": "alert(document.cookie)",
    }
}


def reporting_api(*bodies, extra_type=False):
    reports = [{"type": "csp-violation", "age": 1, "url": "x", "body": b} for b in bodies]
    if extra_type:
        reports.append({"type": "deprecation", "body": {"id": "x"}})
    return reports


class NormaliseReportTests(TestCase):
    def test_legacy_fields(self):
        self.assertEqual(
            csp.normalise_report(LEGACY["csp-report"]),
            ("script-src-elem", "https://evil.example:8443", "/products/5"),
        )

    def test_reporting_api_fields(self):
        body = {
            "documentURL": "https://h/bookings?x=1",
            "effectiveDirective": "style-src-attr",
            "blockedURL": "inline",
            "sample": "color:red",
        }
        self.assertEqual(csp.normalise_report(body), ("style-src-attr", "inline", "/bookings"))

    def test_scheme_only_urls_become_scheme(self):
        body = {"document-uri": "https://h/", "effective-directive": "img-src",
                "blocked-uri": "data:image/png;base64,AAAA"}
        self.assertEqual(csp.normalise_report(body)[1], "data")

    def test_falls_back_to_first_token_of_violated_directive(self):
        body = {"document-uri": "https://h/a", "violated-directive": "script-src 'self'",
                "blocked-uri": "eval"}
        self.assertEqual(csp.normalise_report(body), ("script-src", "eval", "/a"))

    def test_truncates_and_defaults(self):
        body = {"document-uri": "https://h/" + "p" * 500, "effective-directive": "d" * 300}
        directive, blocked, page = csp.normalise_report(body)
        self.assertEqual(len(directive), 100)
        self.assertEqual(blocked, "")
        self.assertEqual(len(page), 200)

    def test_origin_drops_credentials_and_keeps_port(self):
        body = {"document-uri": "https://h/", "effective-directive": "img-src",
                "blocked-uri": "https://user:pw@host:8443/x?y=1"}
        self.assertEqual(csp.normalise_report(body)[1], "https://host:8443")

    def test_ipv6_origin_keeps_brackets(self):
        body = {"document-uri": "https://h/", "effective-directive": "img-src",
                "blocked-uri": "http://[::1]:8080/x"}
        self.assertEqual(csp.normalise_report(body)[1], "http://[::1]:8080")

    def test_malformed_urls_are_dropped(self):
        for field in ("document-uri", "blocked-uri"):
            body = {"document-uri": "https://h/", "effective-directive": "img-src",
                    "blocked-uri": "https://h/", field: "http://[x"}
            self.assertIsNone(csp.normalise_report(body), field)

    def test_nul_bytes_are_stripped(self):
        body = {"document-uri": "https://h/a\x00b", "effective-directive": "img\x00-src",
                "blocked-uri": "in\x00line"}
        self.assertEqual(csp.normalise_report(body), ("img-src", "inline", "/ab"))

    def test_lone_surrogate_is_made_encodable(self):
        body = {"effective-directive": "img-src", "blocked-uri": "a\ud800b"}
        blocked = csp.normalise_report(body)[1]
        self.assertEqual(blocked, "a?b")
        blocked.encode("utf-8")  # must not raise

    def test_missing_page_is_root_and_non_dict_is_none(self):
        self.assertEqual(csp.normalise_report({"effective-directive": "img-src"})[2], "/")
        self.assertIsNone(csp.normalise_report("nope"))
        self.assertIsNone(csp.normalise_report({"document-uri": "https://h/"}))  # no directive


class CspReportEndpointTests(TestCase):
    def setUp(self):
        cache.clear()

    def post(self, payload, content_type="application/csp-report", **extra):
        data = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
        return self.client.post(URL, data=data, content_type=content_type, **extra)

    def test_legacy_report_is_stored_without_personal_data(self):
        self.assertEqual(self.post(LEGACY).status_code, 204)
        row = CspViolation.objects.get()
        self.assertEqual(
            (row.directive, row.blocked, row.page, row.count),
            ("script-src-elem", "https://evil.example:8443", "/products/5", 1),
        )
        stored = " ".join([row.directive, row.blocked, row.page])
        self.assertNotIn("secret", stored)
        self.assertNotIn("cookie", stored)

    def test_reporting_api_batch_ignores_other_types(self):
        body = {"documentURL": "https://h/x", "effectiveDirective": "img-src", "blockedURL": "blob"}
        resp = self.post(reporting_api(body, extra_type=True), "application/reports+json")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(CspViolation.objects.count(), 1)

    def test_plain_json_is_accepted(self):
        self.assertEqual(self.post(LEGACY, "application/json").status_code, 204)
        self.assertEqual(CspViolation.objects.count(), 1)

    def test_repeated_report_bumps_count(self):
        self.post(LEGACY)
        first = CspViolation.objects.get().last_seen
        self.post(LEGACY)
        row = CspViolation.objects.get()
        self.assertEqual(row.count, 2)
        self.assertGreaterEqual(row.last_seen, first)

    def test_wrong_content_type(self):
        self.assertEqual(self.post(LEGACY, "text/plain").status_code, 415)

    def test_too_large(self):
        big = json.dumps({"csp-report": {"effective-directive": "x", "pad": "a" * 17000}})
        self.assertEqual(self.post(big).status_code, 413)

    def test_invalid_json_and_shape(self):
        self.assertEqual(self.post(b"{nope").status_code, 400)
        self.assertEqual(self.post({"foo": 1}).status_code, 400)  # dict without csp-report

    def test_malformed_url_is_not_a_server_error(self):
        for field in ("document-uri", "blocked-uri"):
            report = {"effective-directive": "img-src", field: "http://[x"}
            self.assertEqual(self.post({"csp-report": report}).status_code, 204)
        self.assertEqual(CspViolation.objects.count(), 0)

    def test_nul_byte_is_not_a_server_error(self):
        report = {"effective-directive": "img-src", "blocked-uri": "a\u0000b",
                  "document-uri": "https://h/x\u0000y"}
        self.assertEqual(self.post({"csp-report": report}).status_code, 204)
        row = CspViolation.objects.get()
        self.assertEqual((row.blocked, row.page), ("ab", "/xy"))

    def test_lone_surrogate_is_not_a_server_error(self):
        body = json.dumps({"csp-report": {"effective-directive": "img-src",
                                          "blocked-uri": "\ud800",
                                          "document-uri": "https://h/x\udfff"}})
        self.assertIn("\\ud800", body)  # sent as a JSON escape
        self.assertEqual(self.post(body).status_code, 204)
        row = CspViolation.objects.get()
        self.assertEqual((row.blocked, row.page), ("?", "/x"))  # the "?" then splits off as query

    def test_deeply_nested_json_is_400(self):
        self.assertEqual(self.post("[" * 16000).status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_no_csrf_token_needed(self):
        client = Client(enforce_csrf_checks=True)
        resp = client.post(URL, data=json.dumps(LEGACY), content_type="application/csp-report")
        self.assertEqual(resp.status_code, 204)

    def test_cap_drops_new_keys_but_counts_existing(self):
        CspViolation.objects.bulk_create(
            CspViolation(directive="img-src", blocked="", page=f"/p{i}")
            for i in range(csp.MAX_ROWS)
        )
        self.post(LEGACY)  # new key → dropped
        self.assertEqual(CspViolation.objects.count(), csp.MAX_ROWS)
        self.post({"csp-report": {"document-uri": "https://h/p0", "effective-directive": "img-src"}})
        self.assertEqual(CspViolation.objects.get(page="/p0").count, 2)

    def test_throttle(self):
        for _ in range(csp.RATE_LIMIT):
            self.assertEqual(self.post(LEGACY).status_code, 204)
        self.assertEqual(self.post(LEGACY).status_code, 429)

    def test_throttle_uses_forwarded_client(self):
        for _ in range(csp.RATE_LIMIT):
            self.post(LEGACY, HTTP_X_FORWARDED_FOR="203.0.113.1")
        self.assertEqual(self.post(LEGACY, HTTP_X_FORWARDED_FOR="203.0.113.1").status_code, 429)
        self.assertEqual(self.post(LEGACY, HTTP_X_FORWARDED_FOR="203.0.113.2").status_code, 204)

    def test_processes_at_most_max_reports(self):
        bodies = [{"documentURL": f"https://h/{i}", "effectiveDirective": "img-src"}
                  for i in range(csp.MAX_REPORTS_PER_REQUEST + 5)]
        self.post(reporting_api(*bodies), "application/reports+json")
        self.assertEqual(CspViolation.objects.count(), csp.MAX_REPORTS_PER_REQUEST)


class CspViolationAdminTests(TestCase):
    def test_registered_read_only(self):
        model_admin = admin.site._registry[CspViolation]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
