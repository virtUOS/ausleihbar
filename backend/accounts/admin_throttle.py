# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Brute-force throttle for the Django admin password login.

The break-glass superuser signs in at ``/django-admin/login/`` via
``ModelBackend``. Failed attempts are counted per (client IP, lower-cased
username) and per client IP alone; once a budget is used up, further POSTs to
the login view are refused with HTTP 429 until the window (counted from the
first failure) has passed. A successful admin login resets both counters.
GET of the form and the OIDC login are never affected.

Limitation: counters live in Django's default cache. Without a ``CACHES``
setting that is a per-process LocMemCache, so with N gunicorn workers an
attacker gets up to N times the budget, and a restart resets it. That still
caps guessing to a handful of tries per window; the reverse proxy's IP
allowlist for ``/django-admin/`` remains the primary control.
"""
import hashlib
import math
import unicodedata

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.http import HttpResponse
from django.urls import reverse
from django.utils.translation import ngettext

from common.net import client_ip

# The IP-only budget is this many times the per-(IP, username) budget, so one
# mistyped account doesn't lock out colleagues behind the same NAT while
# username spraying from one address is still capped.
IP_LIMIT_FACTOR = 4

_PREFIX = "admin-login-fail"


def _max_attempts():
    return max(1, settings.ADMIN_LOGIN_MAX_ATTEMPTS)


def _window():
    return max(1, settings.ADMIN_LOGIN_WINDOW_SECONDS)


def _is_admin_login(request):
    return request is not None and request.path == reverse("admin:login")


def _keys(request, username):
    ip = client_ip(request)
    # Hashed: keeps cache keys short/safe and the username out of the cache.
    # NFKC like Django's UsernameField, so the raw POST value checked by the
    # middleware and the normalized one from the auth signals share a key.
    name = unicodedata.normalize("NFKC", (username or "").strip()).lower()
    user_hash = hashlib.sha256(name.encode()).hexdigest()[:32]
    return f"{_PREFIX}:ip:{ip}", f"{_PREFIX}:user:{ip}:{user_hash}"


def _bump(key):
    # Fixed window from the first failure: add() sets the expiry once, incr()
    # keeps it (LocMem/Redis/Memcached).
    cache.add(key, 0, _window())
    try:
        cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, _window())


def is_blocked(request, username):
    ip_key, user_key = _keys(request, username)
    limit = _max_attempts()
    return (
        cache.get(user_key, 0) >= limit
        or cache.get(ip_key, 0) >= limit * IP_LIMIT_FACTOR
    )


@receiver(user_login_failed, dispatch_uid="admin_login_throttle_failed")
def _count_failure(sender, credentials, request=None, **kwargs):
    if _is_admin_login(request):
        for key in _keys(request, credentials.get("username")):
            _bump(key)


@receiver(user_logged_in, dispatch_uid="admin_login_throttle_success")
def _reset(sender, request, user, **kwargs):
    if _is_admin_login(request):
        cache.delete_many(_keys(request, user.get_username()))


class AdminLoginThrottleMiddleware:
    """Refuse POSTs to the admin login while the client is throttled.

    Placed after ``ActiveLanguageMiddleware`` so the message is localized.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and _is_admin_login(request):
            if is_blocked(request, request.POST.get("username", "")):
                minutes = math.ceil(_window() / 60)
                message = ngettext(
                    "Too many failed sign-in attempts. Please wait %(minutes)d minute.",
                    "Too many failed sign-in attempts. Please wait %(minutes)d minutes.",
                    minutes,
                ) % {"minutes": minutes}
                return HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
        return self.get_response(request)
