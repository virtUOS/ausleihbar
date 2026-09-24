# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Pool eligibility: which resource pools a user may see and book.

Implements concept §3.4. A pool with no access groups is open to all
authenticated users (and to anonymous visitors browsing the shop). A pool that
lists access groups is restricted to members of those groups, plus the pool's
own lenders and any admin.
"""
from django.db.models import Exists, OuterRef

from catalog.models import Resource, ResourcePool

from .models import AccessGroup


def user_group_ids(user):
    """IDs of the access groups a user belongs to (manual + claim-matched)."""
    if not user or not user.is_authenticated:
        return set()
    ids = set(user.access_groups.values_list("id", flat=True))
    claims = getattr(user, "claims", None) or {}
    if claims:
        claim_groups = AccessGroup.objects.exclude(claim_key="").values_list(
            "id", "claim_key", "claim_values"
        )
        for group_id, claim_key, claim_values in claim_groups:
            if group_id in ids or not claim_values:
                continue
            raw = claims.get(claim_key)
            if raw is None:
                continue
            have = {str(v) for v in (raw if isinstance(raw, (list, tuple)) else [raw])}
            if have & {str(v) for v in claim_values}:
                ids.add(group_id)
    return ids


def eligible_pool_ids(user):
    """Set of active pool IDs the given user may access in the shop."""
    active = set(
        ResourcePool.objects.filter(is_active=True).values_list("id", flat=True)
    )
    restricted = set(
        ResourcePool.objects.filter(
            is_active=True, access_groups__isnull=False
        ).values_list("id", flat=True)
    )
    open_ids = active - restricted

    if not user or not user.is_authenticated:
        return open_ids
    if user.is_staff or user.is_superuser:
        return active

    eligible = set(open_ids)
    # Lenders always reach the pools they manage.
    eligible |= (
        set(user.pool_memberships.values_list("resource_pool_id", flat=True)) & active
    )
    # Restricted pools the user is eligible for via group membership.
    group_ids = user_group_ids(user)
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
