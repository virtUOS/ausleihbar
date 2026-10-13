# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Roles derived from access groups (#80, ADR-0012).

The single place that answers "is this user an admin / a lender of which
pools?":

- **Admin** — ``is_superuser`` or ``is_staff`` (the Django toggle and the OIDC
  admin-group mapping set these at login), or a **manual** member of an
  ``is_admin`` group. Claim matches never grant admin rights.
- **Lender** — effective member (manual ∪ claim-matched) of a group with
  ``lender_pools``; every pool has a system group "Verleiher ‹Pool›" for the
  individual assignments.

Results are memoised on the user instance (``user._roles_cache``), so a
request asks the database once. The cache carries a process-wide generation
number that is bumped whenever group membership, group rights or a user's
claims change (see ``accounts.signals``), so a long-lived user instance (a
test client's ``force_authenticate`` user, a management command) never sees
stale rights. Caveats: the counter is bumped when the signal fires, i.e.
before the surrounding transaction commits, and ``QuerySet.update()`` /
``bulk_create`` on the groups' through tables send no signals. Both are
harmless in practice because request handling uses a fresh user instance per
request; code that bypasses signals and then re-checks the same instance must
call ``invalidate_cache()`` itself.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from modeltranslation.utils import build_localized_fieldname

from .eligibility import claims_match, user_group_ids
from .models import AccessGroup

ADMIN_GROUP_NAME = "Administratoren"
LENDER_GROUP_PREFIX = "Verleiher"

_generation = 0


def invalidate_cache():
    """Mark every memoised role result as stale (called from signals)."""
    global _generation
    _generation += 1


def _cache(user):
    cache = getattr(user, "_roles_cache", None)
    if cache is None or cache.get("_gen") != _generation:
        cache = {"_gen": _generation}
        user._roles_cache = cache
    return cache


def _authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def group_ids(user) -> set[int]:
    """IDs of the user's effective groups (manual ∪ claim-matched)."""
    if not _authenticated(user):
        return set()
    cache = _cache(user)
    if "group_ids" not in cache:
        cache["group_ids"] = frozenset(user_group_ids(user))
    return set(cache["group_ids"])


def managed_pool_ids(user) -> set[int]:
    """Pools the user is a lender of (incl. inactive and trashed pools)."""
    if not _authenticated(user):
        return set()
    cache = _cache(user)
    if "managed_pool_ids" not in cache:
        ids = group_ids(user)
        cache["managed_pool_ids"] = frozenset(
            AccessGroup.lender_pools.through.objects.filter(
                accessgroup_id__in=ids
            ).values_list("resourcepool_id", flat=True)
        ) if ids else frozenset()
    return set(cache["managed_pool_ids"])


def is_app_admin(user) -> bool:
    """Admin of the application (not to be confused with Django-admin access)."""
    if not _authenticated(user):
        return False
    if user.is_superuser or user.is_staff:
        return True
    cache = _cache(user)
    if "is_admin_member" not in cache:
        # Manual membership only — claim matches never grant admin.
        cache["is_admin_member"] = user.access_groups.filter(is_admin=True).exists()
    return cache["is_admin_member"]


def is_lender(user) -> bool:
    """Admin, or lender of at least one pool."""
    return is_app_admin(user) or bool(managed_pool_ids(user))


def pool_lender_ids(pool) -> set[int]:
    """IDs of the users who are lenders of ``pool`` (a pool or its id).

    Manual members of the pool's lender groups plus users whose stored login
    claims match one of those groups' claim rules. Admins are not included.
    """
    pool_id = getattr(pool, "pk", pool)
    groups = AccessGroup.objects.filter(lender_pools=pool_id)
    User = get_user_model()
    ids = set(
        User.objects.filter(access_groups__in=groups)
        .values_list("id", flat=True)
        .distinct()
    )
    rules = [
        (key, values)
        for key, values in groups.exclude(claim_key="").values_list(
            "claim_key", "claim_values"
        )
        if values
    ]
    if rules:
        # Pre-filter in SQL to users carrying one of the rules' claim keys;
        # claims_match decides (scalar vs. list values, string comparison).
        candidates = User.objects.filter(
            claims__has_any_keys=sorted({key for key, _ in rules})
        ).exclude(id__in=ids)
        for user_id, claims in candidates.values_list("id", "claims"):
            if user_id not in ids and any(
                claims_match(claims, key, values) for key, values in rules
            ):
                ids.add(user_id)
    return ids


def admin_user_ids() -> set[int]:
    """IDs of all app admins (``is_staff``/``is_superuser`` or manual members
    of an ``is_admin`` group)."""
    return set(
        get_user_model()
        .objects.filter(
            Q(is_staff=True) | Q(is_superuser=True) | Q(access_groups__is_admin=True)
        )
        .values_list("id", flat=True)
        .distinct()
    )


_NAME_MAX = AccessGroup._meta.get_field("name").max_length


def _free_name(base, exclude_pk=None):
    """``base``, or ``base (2)``, ``base (3)``… if a group already uses it,
    truncated so name plus suffix fit the column."""
    taken = AccessGroup.objects.exclude(pk=exclude_pk)
    name, n = base[:_NAME_MAX], 1
    while taken.filter(name=name).exists():
        n += 1
        suffix = f" ({n})"
        name = base[: _NAME_MAX - len(suffix)] + suffix
    return name


def _pool_name(pool):
    """The pool's name in the content default language (not the active one),
    so the system group's name doesn't depend on who saved the pool."""
    field = build_localized_fieldname("name", settings.MODELTRANSLATION_DEFAULT_LANGUAGE)
    return getattr(pool, field, None) or pool.name


def ensure_pool_lender_group(pool) -> AccessGroup:
    """Create or repair the system lender group of ``pool``.

    Keeps its name in sync with the pool (``Verleiher ‹Pool›``; a suffix is
    added if a regular group already took that name), its lender pools at
    exactly ``{pool}`` and its claim rule / admin flag cleared. Called on
    every pool save (``accounts.signals``).
    """
    base = f"{LENDER_GROUP_PREFIX} {_pool_name(pool)}"
    with transaction.atomic():
        group = AccessGroup.objects.filter(system_pool=pool).first()
        if group is None:
            group = AccessGroup.objects.create(name=_free_name(base), system_pool=pool)
        else:
            changed = []
            name = _free_name(base, exclude_pk=group.pk)
            if group.name != name:
                group.name = name
                changed.append("name")
            if group.claim_key or group.claim_values:
                group.claim_key, group.claim_values = "", []
                changed += ["claim_key", "claim_values"]
            if group.is_admin:
                group.is_admin = False
                changed.append("is_admin")
            if changed:
                group.save(update_fields=changed)
        if list(group.lender_pools.values_list("id", flat=True)) != [pool.pk]:
            group.lender_pools.set([pool])
    return group


def admin_group() -> AccessGroup:
    """The system group "Administratoren" (created on demand)."""
    group = AccessGroup.objects.filter(system_admin=True).first()
    if group is None:
        group = AccessGroup.objects.create(
            name=_free_name(ADMIN_GROUP_NAME), is_admin=True, system_admin=True
        )
    return group
