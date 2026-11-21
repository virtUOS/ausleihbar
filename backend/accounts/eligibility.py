# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Pool eligibility: which resource pools a user may see and book.

Implements concept §3.4. A pool with no access groups is open to all
authenticated users (and to anonymous visitors browsing the shop). A pool that
lists access groups is restricted to members of those groups, plus the pool's
own lenders and any admin.

LTI course pools: course groups (``AccessGroup.system_course``) never decide
whether a pool is open — they only *add* eligibility for their members. A pool
is open iff it has no ordinary (non-course) access group and no ``owner``;
personal pools are always restricted. So linking a course to an open pool
doesn't close it, and switching off the last course link of a personal pool
doesn't open it.
"""
from django.db.models import Exists, OuterRef, Q

from catalog.models import Resource, ResourcePool

from .models import AccessGroup


def user_group_ids(user):
    """IDs of the access groups a user belongs to (manual + claim-matched)."""
    if not user or not user.is_authenticated:
        return set()
    ids = set(user.access_groups.values_list("id", flat=True))
    claims = idp_claims(user)
    if claims:
        claim_groups = AccessGroup.objects.exclude(claim_key="").values_list(
            "id", "claim_key", "claim_values"
        )
        for group_id, claim_key, claim_values in claim_groups:
            if group_id not in ids and claims_match(claims, claim_key, claim_values):
                ids.add(group_id)
    return ids


LTI_SUBJECT_PREFIX = "lti:"


def idp_claims(user):
    """The user's stored login claims for claim rules — IdP (OIDC) claims only.

    LTI-native accounts (``subject`` "lti:…") carry the LMS launch payload in
    ``claims`` (``basicbar_lti.provision_user``). A platform controls that
    payload, so it must never grant group membership (nor lender rights through
    a claim group): those users have no claims here."""
    if (getattr(user, "subject", "") or "").startswith(LTI_SUBJECT_PREFIX):
        return {}
    return getattr(user, "claims", None) or {}


def claims_match(claims, claim_key, claim_values):
    """Whether a claims snapshot satisfies a group's claim rule.

    True if the claim ``claim_key`` (a scalar or a list) contains any of
    ``claim_values``. An empty key or value list never matches.
    """
    if not claims or not claim_key or not claim_values:
        return False
    raw = claims.get(claim_key)
    if raw is None:
        return False
    have = {str(v) for v in (raw if isinstance(raw, (list, tuple)) else [raw])}
    return bool(have & {str(v) for v in claim_values})


def eligible_pool_ids(user):
    """Set of active pool IDs the given user may access in the shop."""
    active = set(
        ResourcePool.objects.filter(is_active=True).values_list("id", flat=True)
    )
    restricted = set(
        ResourcePool.objects.filter(
            Q(owner__isnull=False)
            # One filter() call: both conditions apply to the same group row,
            # so a course group next to an ordinary group still restricts.
            | Q(access_groups__isnull=False, access_groups__system_course__isnull=True),
            is_active=True,
        )
        .distinct()
        .values_list("id", flat=True)
    )
    open_ids = active - restricted

    if not user or not user.is_authenticated:
        return open_ids
    from . import roles  # roles imports this module

    if roles.is_app_admin(user):
        return active

    eligible = set(open_ids)
    # Lenders always reach the pools they manage.
    eligible |= roles.managed_pool_ids(user) & active
    # Restricted pools the user is eligible for via group membership.
    group_ids = roles.group_ids(user)  # memoised per request
    if group_ids:
        eligible |= set(
            ResourcePool.objects.filter(
                is_active=True, access_groups__in=group_ids
            ).values_list("id", flat=True)
        )
    return eligible


def visible_products(product_qs, user, pool_ids=None):
    """Restrict a Product queryset to products the user may see in the shop.

    A product is shown only if it has at least one *bookable* resource — status
    AVAILABLE — in a pool the user can access. Hidden therefore are products
    with no resources, with only blocked/defective/retired ones, or with
    resources only in pools the user can't reach: none of these can be borrowed.

    ``pool_ids`` lets a caller that already computed ``eligible_pool_ids(user)``
    (e.g. once per serializer, for several products) pass it in instead of
    recomputing it here; omit it to compute it as before.
    """
    if pool_ids is None:
        pool_ids = eligible_pool_ids(user)
    has_bookable = Exists(
        Resource.objects.filter(
            product=OuterRef("pk"),
            resource_pool_id__in=pool_ids,
            status=Resource.Status.AVAILABLE,
        )
    )
    return product_qs.annotate(_has_bookable=has_bookable).filter(_has_bookable=True)
