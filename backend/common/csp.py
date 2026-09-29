# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Content-Security-Policy violation reports (issue #44).

Browsers POST reports to ``/api/csp-report/`` in two formats: the legacy
``report-uri`` one (``{"csp-report": {...}}``, kebab-case keys) and the
Reporting API one (a list of ``{"type": "csp-violation", "body": {...}}``,
camelCase keys). Both are reduced to ``(directive, blocked, page)`` without
personal data and aggregated in ``CspViolation``.
"""
from urllib.parse import urlsplit

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import CspViolation

MAX_BODY_BYTES = 16 * 1024
MAX_ROWS = 1000
MAX_REPORTS_PER_REQUEST = 20
RATE_LIMIT = 60  # requests per client and window
RATE_WINDOW_SECONDS = 60


def _first(body, *keys):
    for key in keys:
        value = body.get(key)
        if isinstance(value, str):
            value = value.replace("\x00", "")  # Postgres rejects NUL in text
            if value:
                return value
    return ""


def _blocked(value):
    """Keywords (``inline``, ``eval``, …) stay; URLs shrink to their origin
    (scheme, host, port — never credentials), scheme-only URLs (``data:…``,
    ``blob:…``) to the scheme. Raises ``ValueError`` for malformed URLs."""
    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        host = parts.hostname or ""
        if ":" in host:  # IPv6 literal
            host = f"[{host}]"
        port = f":{parts.port}" if parts.port is not None else ""
        return f"{parts.scheme}://{host}{port}"[:200]
    if parts.scheme and ":" in value:
        return parts.scheme[:200]
    return value[:200]


def normalise_report(body):
    """Return ``(directive, blocked, page)`` for one report body, or ``None``
    when it is not a usable CSP report (including malformed URLs)."""
    if not isinstance(body, dict):
        return None
    directive = _first(body, "effective-directive", "effectiveDirective",
                       "violated-directive", "violatedDirective").split(" ")[0]
    if not directive:
        return None
    try:
        blocked = _blocked(_first(body, "blocked-uri", "blockedURL"))
        page = urlsplit(_first(body, "document-uri", "documentURL")).path or "/"
    except ValueError:  # e.g. "http://[x" — crafted input, drop the report
        return None
    return directive[:100], blocked, page[:200]


def record_violations(entries):
    """Upsert each ``(directive, blocked, page)``: bump known rows; create new
    ones only while the table is below ``MAX_ROWS``."""
    now = timezone.now()
    for directive, blocked, page in entries:
        key = {"directive": directive, "blocked": blocked, "page": page}
        if CspViolation.objects.filter(**key).update(count=F("count") + 1, last_seen=now):
            continue
        if CspViolation.objects.count() >= MAX_ROWS:
            continue
        try:
            with transaction.atomic():
                CspViolation.objects.create(**key, last_seen=now)
        except IntegrityError:  # created concurrently — count this one too
            CspViolation.objects.filter(**key).update(count=F("count") + 1, last_seen=now)
