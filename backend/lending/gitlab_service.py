# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Optional GitLab issue creation for defect reports (per-pool, opt-in).

When a pool has a GitLab project URL + access token configured, marking one of
its resources defective opens an issue in that project. The project URL (server
included) and token live on the pool and may differ per pool. Uses the stdlib
``urllib`` so it adds no dependency, and is fully fail-soft: a GitLab outage or
misconfiguration must never break the defect-marking flow.
"""

import json
import logging
from urllib import error, parse, request

from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured(pool) -> bool:
    """Whether the pool has both a project URL and a token set."""
    return bool(pool and pool.defect_gitlab_url and pool.defect_gitlab_token)


def _api_base_and_project(url: str):
    """Split a project URL into (api base, project path).

    ``https://gitlab.example.com/group/sub/project`` →
    ``("https://gitlab.example.com", "group/sub/project")``. Returns
    ``(None, None)`` if the URL is unusable.
    """
    parts = parse.urlsplit((url or "").strip())
    if not parts.scheme or not parts.netloc:
        return None, None
    project = parts.path.strip("/")
    # Tolerate a pasted "…/-/issues" or trailing segments beyond the project.
    if "/-/" in project:
        project = project.split("/-/", 1)[0]
    if not project:
        return None, None
    return f"{parts.scheme}://{parts.netloc}", project


class _NoRedirectHandler(request.HTTPRedirectHandler):
    """Refuse every redirect: a 3xx surfaces as an ``HTTPError``.

    Following redirects would let the configured host bounce the request —
    ``PRIVATE-TOKEN`` header included — on to arbitrary (internal) URLs.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = request.build_opener(_NoRedirectHandler)


def _open(req, timeout=15):
    """Send ``req`` without following redirects (patched in tests)."""
    return _OPENER.open(req, timeout=timeout)


def _safe_issue_url(web_url, configured_url: str) -> str | None:
    """Return ``web_url`` only if it points at the configured GitLab host.

    The scheme must be ``https`` (or ``http`` when the configured URL itself is
    ``http``, for local test setups) and the host/port must match; anything
    else — e.g. ``javascript:`` or a foreign host — is rejected.
    """
    if not isinstance(web_url, str) or not web_url:
        return None
    configured = parse.urlsplit((configured_url or "").strip())
    parts = parse.urlsplit(web_url.strip())
    allowed = {"https"} | ({"http"} if configured.scheme.lower() == "http" else set())
    if parts.scheme.lower() not in allowed:
        return None
    if not parts.netloc or parts.netloc.lower() != configured.netloc.lower():
        return None
    return web_url.strip()


def create_defect_issue(pool, resource, note: str = "") -> str | None:
    """Open a GitLab issue for a defective resource; return its URL or ``None``.

    Never raises — logs and returns ``None`` on any problem so the caller's
    transaction/flow is unaffected.
    """
    if not is_configured(pool):
        return None
    base, project = _api_base_and_project(pool.defect_gitlab_url)
    if not base:
        logger.warning("Pool %s has an unusable GitLab URL; skipping issue.", pool.pk)
        return None

    title = f"Defect: {resource.product.title} ({resource.inventory_number})"
    description = [
        f"Pool: {pool.name}",
        f"Device: {resource.product.title} ({resource.inventory_number})",
    ]
    if getattr(resource, "serial_number", ""):
        description.append(f"Serial: {resource.serial_number}")
    if note:
        description += ["", f"Note: {note}"]
    # Deep link back so whoever resolves the ticket can return the device to
    # service in Ausleihbar.
    shop = settings.SHOP_BASE_URL.rstrip("/")
    description += [
        "",
        f"Return to service in Ausleihbar: {shop}/manage/inventory/{resource.id}",
    ]

    payload = {"title": title, "description": "\n".join(description)}
    api_url = f"{base}/api/v4/projects/{parse.quote(project, safe='')}/issues"
    req = request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "PRIVATE-TOKEN": pool.defect_gitlab_token,
        },
        method="POST",
    )
    try:
        with _open(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, ValueError, OSError) as exc:
        # A refused redirect lands here too (HTTPError for the 3xx).
        logger.warning("GitLab issue creation failed for pool %s: %s", pool.pk, exc)
        return None
    raw_url = data.get("web_url") if isinstance(data, dict) else None
    issue_url = _safe_issue_url(raw_url, pool.defect_gitlab_url)
    if raw_url and not issue_url:
        logger.warning(
            "GitLab returned an issue URL off the configured host for pool %s; "
            "not storing it.",
            pool.pk,
        )
    return issue_url
