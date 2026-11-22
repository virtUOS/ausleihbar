# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Ausleihbar's LTI launch: an LMS course ↔ the pools it is opened to.

The generic machinery (platform registrations, OIDC login, JWKS, user
provisioning) comes from basicbar-lti; this module decides what a launch
means here:

- **Instructor** → the "Kurs verknüpfen" page (``lti-course``): the course's
  links, the lecturer's managed pools to link, and — when
  ``LtiSetting.instructors_create_pools`` is on — "create my own pool".
- **Learner** → joins the system access groups of the course's active links
  (instructors join them too, so co-teachers without lender rights see the
  linked pools),
  then lands on the pool page in the SPA (one pool) or a short chooser
  (several). No active link → a friendly "not linked yet" page.

The booking UI isn't meant for the LMS iframe: a framed launch
(``Sec-Fetch-Dest: iframe``) renders a page whose buttons open Ausleihbar in
a new tab instead of redirecting inside the frame.

The course the instructor pages act on comes from the session written by the
validated launch (``SESSION_KEY``), never from form fields.

The session set inside the LMS frame often doesn't reach the new tab
(SameSite cookies, blocked third-party cookies), so the framed page's links
go through a one-time hand-off (``lti-continue``): a random token in the
shared (database) cache, valid ``HANDOFF_TTL`` seconds. Its page asks
"Weiter als ‹name›"; the confirming POST deletes the token, logs the new tab
in as the launched user and restores the course session before redirecting
to the target.
"""
import logging
import secrets
from urllib.parse import urlsplit

from basicbar_lti.models import LtiPlatform
from basicbar_lti.provisioning import (
    CLAIM,
    is_instructor,
    launch_storage,
    platform_for,
    provision_user,
)
from basicbar_lti.tool_conf import build_tool_conf
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from pylti1p3.contrib.django import DjangoMessageLaunch
from pylti1p3.exception import LtiException

from accounts import roles
from catalog.models import ResourcePool

from . import services
from .models import LtiSetting

logger = logging.getLogger(__name__)

# Session entry written by a validated launch:
# {"platform": <pk>, "context_id": str, "title": str, "instructor": bool}
SESSION_KEY = "lti_course"
# Seconds pylti1p3 keeps a launch's id_token body in the cache.
LAUNCH_DATA_LIFETIME = 300
# One-time hand-off tokens of framed launches: lifetime and cache key prefix.
HANDOFF_TTL = 120
HANDOFF_PREFIX = "lti:handoff:"


def spa_url(path: str) -> str:
    """Absolute URL of an SPA route (``settings.SHOP_BASE_URL``)."""
    return settings.SHOP_BASE_URL.rstrip("/") + path


def pool_url(pool) -> str:
    return spa_url(f"/pools/{pool.pk}")


def _error(request, message, status):
    return render(request, "lti/error.html", {"message": message}, status=status)


def _is_framed(request) -> bool:
    return request.headers.get("Sec-Fetch-Dest", "").lower() in ("iframe", "frame")


def _safe_next(request, url) -> bool:
    """A hand-off target must stay on this site: a local path, this host or
    the SPA's host (``SHOP_BASE_URL``) — never an open redirect."""
    hosts = {request.get_host(), urlsplit(settings.SHOP_BASE_URL).netloc}
    return url_has_allowed_host_and_scheme(
        url, allowed_hosts=hosts, require_https=request.is_secure()
    )


def handoff_url(request, user, next_url, course) -> str:
    """Absolute single-use URL that logs a new tab in as ``user`` (with the
    launch's ``course`` session) and redirects to ``next_url``."""
    if not _safe_next(request, next_url):
        raise ValueError(f"Hand-off target off-site: {next_url!r}")
    token = secrets.token_urlsafe(32)
    cache.set(
        HANDOFF_PREFIX + token,
        {"user_id": user.pk, "next": next_url, "course": course},
        HANDOFF_TTL,
    )
    return request.build_absolute_uri(reverse("lti-continue", args=[token]))


def _handoff_expired(request):
    return _error(
        request,
        _("This link has expired or was already used. "
          "Please open Ausleihbar again from your course."),
        410,
    )


def _handoff_user(request, data):
    """The hand-off's (active) user if its target is still same-site."""
    if not data or not _safe_next(request, data.get("next") or ""):
        return None
    return get_user_model().objects.filter(pk=data.get("user_id"), is_active=True).first()


def _display_name(user) -> str:
    return user.get_full_name() or user.get_username()


@require_http_methods(["GET", "POST"])
def lti_continue(request, token):
    """Hand-off of a framed launch (see ``handoff_url``).

    GET only shows a confirmation page "Weiter als ‹name›" — it never logs
    in or touches the session, so a link sent to someone else can't sign
    them in unnoticed (login CSRF). The page's POST button (CSRF-protected,
    same origin) consumes the token, logs in, restores the course session
    and redirects. Unknown, used or expired → friendly page."""
    key = HANDOFF_PREFIX + token
    data = cache.get(key) if len(token) <= 64 else None
    user = _handoff_user(request, data)
    if user is None:
        return _handoff_expired(request)
    if request.method == "GET":
        current = request.user if request.user.is_authenticated else None
        return render(
            request,
            "lti/handoff.html",
            {
                "name": _display_name(user),
                "other": (
                    _display_name(current)
                    if current is not None and current.pk != user.pk else ""
                ),
            },
        )
    # ``delete`` reports whether this request removed the row: of two
    # concurrent uses only one wins.
    if not cache.delete(key):
        return _handoff_expired(request)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if data.get("course"):
        request.session[SESSION_KEY] = data["course"]
    return redirect(data["next"])

@csrf_exempt
@require_POST
def lti_launch(request):
    """Message launch (resource link) from a registered platform."""
    try:
        message_launch = DjangoMessageLaunch(
            request, build_tool_conf(), launch_data_storage=launch_storage()
        )
        # pylti1p3 keeps the id_token body (name, e-mail, roles, course) in
        # the cache for later ``from_cache`` use, which this tool never needs:
        # keep it minutes, not the default day.
        message_launch.set_launch_data_lifetime(LAUNCH_DATA_LIFETIME)
        launch_data = message_launch.get_launch_data()
    except LtiException as exc:
        logger.warning("LTI launch rejected: %s", exc)
        return _error(
            request,
            _("The launch from your learning platform could not be verified. "
              "Please open Ausleihbar again from your course."),
            400,
        )
    except Exception as exc:  # noqa: BLE001 — pylti1p3 raises bare Exception
        # for an issuer without (active) registration.
        logger.warning("LTI launch failed: %s", exc, exc_info=True)
        return _error(request, _("Unknown platform registration."), 403)

    platform = platform_for(launch_data)
    if platform is None:
        return _error(request, _("Unknown platform registration."), 403)
    if message_launch.is_deep_link_launch():
        return _error(request, _("Ausleihbar does not offer content selection."), 400)
    if not launch_data.get("sub"):
        return _error(
            request, _("Ausleihbar needs a personal launch (no anonymous access)."), 400
        )
    context = launch_data.get(f"{CLAIM}context") or {}
    context_id = str(context.get("id") or "")[:255]
    if not context_id:
        return _error(request, _("The launch does not contain a course."), 400)
    title = str(context.get("title") or context.get("label") or "")[:255]

    instructor = is_instructor(launch_data)
    services.refresh_course_title(platform, context_id, title)
    if not instructor and not services.has_open_links(platform, context_id):
        # No account for learners of a course that isn't linked (yet).
        return render(request, "lti/not_linked.html", {"title": title}, status=404)

    user = provision_user(platform, launch_data)
    if not user.is_active:
        return _error(request, _("Your Ausleihbar account is deactivated."), 403)
    # Everyone launching from the course joins its active links' groups —
    # instructors too, so co-teachers without lender rights can open the
    # linked pools (lenders don't need it, it does no harm).
    pools = services.join_course_groups(
        user=user, platform=platform, context_id=context_id
    )
    if not instructor:
        if not pools:
            return render(request, "lti/not_linked.html", {"title": title}, status=404)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    course = {
        "platform": platform.pk,
        "context_id": context_id,
        "title": title,
        "instructor": instructor,
    }
    request.session[SESSION_KEY] = course

    if instructor:
        entries = [(_("Link course"), request.build_absolute_uri(reverse("lti-course")))]
    else:
        entries = [(p.name, pool_url(p)) for p in pools]
    if _is_framed(request):
        # The frame's session may not reach the new tab: one-time hand-off
        # links per button.
        return render(
            request, "lti/continue.html",
            {
                "title": title,
                "entries": [
                    (label, handoff_url(request, user, url, course))
                    for label, url in entries
                ],
            },
        )
    if len(entries) == 1:
        return redirect(entries[0][1])
    return render(request, "lti/pools.html", {"title": title, "entries": entries})


def _course_session(request):
    """``(platform, course dict)`` of the instructor's launch, or ``None``."""
    data = request.session.get(SESSION_KEY)
    if not (request.user.is_authenticated and data and data.get("instructor")):
        return None
    platform = LtiPlatform.objects.filter(pk=data["platform"], is_active=True).first()
    if platform is None:
        return None
    return platform, data


def _no_session(request):
    return _error(
        request,
        _("Your session has expired. Please open Ausleihbar again from your course."),
        403,
    )


def _render_course(request, platform, data, *, error="", pool_name="", status=200):
    user = request.user
    links = list(services.course_links(platform, data["context_id"]))
    managed = roles.managed_pool_ids(user)
    linked_ids = {link.pool_id for link in links}
    linkable = ResourcePool.objects.filter(pk__in=managed - linked_ids).order_by("name")
    managed_links = [link for link in links if link.pool_id in managed]
    return render(
        request,
        "lti/course.html",
        {
            "title": data["title"] or data["context_id"],
            "links": [
                {
                    "link": link,
                    "url": pool_url(link.pool),
                    "manageable": link.pool_id in managed,
                }
                for link in links
            ],
            "linkable": linkable,
            "can_create": LtiSetting.load().instructors_create_pools,
            # One manageable linked pool → its course list, else the pools overview.
            "manage_url": spa_url(
                f"/manage/pools/{managed_links[0].pool_id}/courses"
                if len(managed_links) == 1
                else "/manage/pools"
            ),
            "error": error,
            "pool_name": pool_name,
        },
        status=status,
    )


@require_GET
def course_page(request):
    """The instructor's "Kurs verknüpfen" page (session from the launch)."""
    found = _course_session(request)
    if found is None:
        return _no_session(request)
    return _render_course(request, *found)


@require_POST
def course_link(request):
    """Link the launched course to one of the instructor's managed pools
    (or switch an existing link back on)."""
    found = _course_session(request)
    if found is None:
        return _no_session(request)
    platform, data = found
    raw = request.POST.get("pool", "")
    pool = ResourcePool.objects.filter(pk=int(raw)).first() if raw.isdigit() else None
    if pool is None:
        return _error(request, _("You are not a lender of this pool."), 403)
    try:
        services.link_course(
            user=request.user, platform=platform, context_id=data["context_id"],
            pool=pool, title=data["title"],
        )
    except PermissionDenied:
        return _error(request, _("You are not a lender of this pool."), 403)
    return redirect("lti-course")


@require_POST
def course_create_pool(request):
    """Create the instructor's own pool and link the course to it (only
    while ``LtiSetting.instructors_create_pools`` is on)."""
    found = _course_session(request)
    if found is None:
        return _no_session(request)
    platform, data = found
    if not LtiSetting.load().instructors_create_pools:
        return _error(request, _("Creating your own pool is not enabled."), 403)
    name = request.POST.get("name", "")
    try:
        pool = services.create_personal_pool(user=request.user, name=name)
    except ValidationError as exc:
        return _render_course(
            request, platform, data, error=" ".join(exc.messages),
            pool_name=name, status=400,
        )
    services.link_course(
        user=request.user, platform=platform, context_id=data["context_id"],
        pool=pool, title=data["title"],
    )
    return redirect("lti-course")
