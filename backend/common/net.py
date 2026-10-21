# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Client address helper for throttles (never stored)."""


def client_ip(request):
    """The requesting client's IP, for throttle keys only.

    Behind Caddy the real client is the *last* X-Forwarded-For entry: Caddy
    (>= 2.5, no ``trusted_proxies``) discards client-sent values and appends
    the peer it saw, so earlier entries are attacker-controlled. Without the
    header (dev, tests) ``REMOTE_ADDR`` is used. Behind an additional load
    balancer all clients would share one bucket. In production the backend is
    reachable only through Caddy (``expose``, no published port), so the
    header cannot be forged by bypassing the proxy.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")
