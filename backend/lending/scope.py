# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Default pool scope of the lending area ("My pools" for admins).

An admin who is also assigned as a lender (``PoolMembership``) sees only those
pools in the lending area by default; the request header ``X-Pool-Scope: all``
widens the view to every active pool (support view).

This is a **view filter, not a permission**: it only sets the default set of
pools that lists, counters and choices show. Authorization checks keep using
the unscoped helpers (an admin may still open or act on any pool, and an
explicit ``?pool=<id>`` filter still works). The header is ignored for
non-admins, so it can never widen what a lender sees.
"""
from catalog.models import ResourcePool

SCOPE_HEADER = "HTTP_X_POOL_SCOPE"


def _is_admin(user):
    return bool(user.is_staff or user.is_superuser)


def admin_membership_pool_ids(user):
    """Active pools an admin is assigned to as lender, or ``None``.

    ``None`` means the admin has no (active) lender assignment — no "My pools"
    scope exists for them (and no switch is offered). Always ``None`` for
    non-admins.
    """
    if not _is_admin(user):
        return None
    ids = set(
        ResourcePool.objects.filter(memberships__user=user, is_active=True)
        .values_list("id", flat=True)
    )
    return ids or None


def wants_all_pools(request):
    """Whether the request asks for the widened support view."""
    return (request.META.get(SCOPE_HEADER) or "").strip().lower() == "all"


def admin_scope_pool_ids(request):
    """The narrowing an admin's lending-area lists get, or ``None`` for none.

    Returns the admin's active membership pools unless the request carries
    ``X-Pool-Scope: all``. ``None`` (= keep today's unrestricted admin view) for
    non-admins, admins without memberships, and the support view. Lender
    narrowing stays where it is (their own membership filter).
    """
    user = request.user
    if not _is_admin(user) or wants_all_pools(request):
        return None
    return admin_membership_pool_ids(user)


def lending_scope_pool_ids(request):
    """Pool ids the lending area shows by default for this request.

    - non-admin → their membership pools (the header is ignored);
    - admin with memberships, no ``X-Pool-Scope: all`` → those pools ∩ active;
    - otherwise (support view, admin without memberships) → all active pools.
    """
    user = request.user
    if not _is_admin(user):
        return set(
            ResourcePool.objects.filter(memberships__user=user)
            .values_list("id", flat=True)
        )
    scoped = admin_scope_pool_ids(request)
    if scoped is not None:
        return scoped
    return set(
        ResourcePool.objects.filter(is_active=True).values_list("id", flat=True)
    )
