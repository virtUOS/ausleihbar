# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Endpoint receiving browser CSP violation reports (issue #44)."""
import json

from django.core.cache import cache
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import csp

_LEGACY = "application/csp-report"
_REPORTING = "application/reports+json"
_JSON = "application/json"


def _client_key(request):
    """Throttle key only — never stored. Behind Caddy the real client is the
    last X-Forwarded-For entry (Caddy ignores client-sent values)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    client = forwarded.split(",")[-1].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return f"csp-report:{client}"


def _throttled(request):
    key = _client_key(request)
    cache.add(key, 0, csp.RATE_WINDOW_SECONDS)
    try:
        hits = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, csp.RATE_WINDOW_SECONDS)
        hits = 1
    return hits > csp.RATE_LIMIT


def _bodies(payload):
    """Report bodies from either format, or ``None`` for an unknown shape."""
    if isinstance(payload, dict) and "csp-report" in payload:
        return [payload["csp-report"]]
    if isinstance(payload, list):
        return [r.get("body") for r in payload
                if isinstance(r, dict) and r.get("type") == "csp-violation"]
    return None


@csrf_exempt
@require_POST
def csp_report(request):
    if request.content_type not in (_LEGACY, _REPORTING, _JSON):
        return HttpResponse(status=415)
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > csp.MAX_BODY_BYTES:
        return HttpResponse(status=413)
    raw = request.read(csp.MAX_BODY_BYTES + 1)
    if len(raw) > csp.MAX_BODY_BYTES:
        return HttpResponse(status=413)
    if _throttled(request):
        return HttpResponse(status=429)
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):  # deep nesting
        return HttpResponse(status=400)
    bodies = _bodies(payload)
    if bodies is None:
        return HttpResponse(status=400)
    entries = [e for e in map(csp.normalise_report, bodies[: csp.MAX_REPORTS_PER_REQUEST]) if e]
    csp.record_violations(entries)
    return HttpResponse(status=204)
