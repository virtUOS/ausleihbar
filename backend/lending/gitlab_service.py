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
        with request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("GitLab issue creation failed for pool %s: %s", pool.pk, exc)
        return None
    return data.get("web_url")
