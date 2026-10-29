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


def borrowers_of_pools(pool_ids):
    """Users with a submitted (non-cart) booking in one of ``pool_ids`` —
    the borrowers a lender of those pools may look up and strike."""
    from lending.models import Booking

    return get_user_model().objects.filter(
        pk__in=Booking.objects.filter(resource_pool_id__in=pool_ids)
        .exclude(status=Booking.Status.CART)
        .values("borrower_id")
    )


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


def maintainable_group_ids(user) -> set[int]:
    """Access groups whose *manual* members ``user`` may maintain from the
    lending desk (#171): pure access groups — no ``lender_pools``, not
    ``is_admin``, no system group — that gate at least one of the user's
    pools (admins: any pool). Groups that hand out rights stay admin-only,
    even when they also gate one of the user's pools."""
    if not _authenticated(user):
        return set()
    if is_app_admin(user):
        gating = Q(pools__isnull=False)
    else:
        pools = managed_pool_ids(user)
        if not pools:
            return set()
        gating = Q(pools__in=pools)
    return set(
        AccessGroup.objects.filter(
            gating,
            is_admin=False,
            system_pool__isnull=True,
            system_admin=False,
            lender_pools__isnull=True,
        ).values_list("id", flat=True)
    )


def would_be_admin(user, manual_group_ids) -> bool:
    """Whether ``user`` would still be an app admin if their manual groups
    were exactly ``manual_group_ids`` (guards against self-lockout when an
    admin edits their own group memberships)."""
    if user.is_superuser or user.is_staff:
        return True
    return AccessGroup.objects.filter(pk__in=manual_group_ids, is_admin=True).exists()


def is_lender(user) -> bool:
    """Admin, or lender of at least one pool."""
    return is_app_admin(user) or bool(managed_pool_ids(user))


def _effective_member_ids(groups) -> set[int]:
    """IDs of the effective members (manual ∪ claim-matched) of ``groups``
    (an ``AccessGroup`` queryset)."""
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
        # Pre-filter in SQL (jsonb containment); claims_match decides.
        candidates = User.objects.filter(claim_rules_q(rules)).exclude(id__in=ids)
        for user_id, claims in candidates.values_list("id", "claims"):
            if user_id not in ids and any(
                claims_match(claims, key, values) for key, values in rules
            ):
                ids.add(user_id)
    return ids


def claim_rules_q(rules) -> Q:
    """SQL pre-filter for users whose stored ``claims`` may satisfy one of
    ``rules`` (``(claim_key, claim_values)`` pairs): jsonb containment per
    value, for list claims (``{key: [v]}``) and scalar claims (``{key: v}``).
    Numeric/boolean JSON values are included (``_json_variants``).
    Expressed as dict containment so odd claim keys (``__``) need no lookup
    path. Callers still confirm with ``claims_match`` (the authority)."""
    q = Q(pk__in=[])
    for key, values in rules:
        for value in values or []:
            for typed in _json_variants(value):
                q |= Q(claims__contains={key: [typed]}) | Q(claims__contains={key: typed})
    return q


def _json_variants(value):
    """``value`` (a rule's string) plus the JSON scalars whose ``str()`` equals
    it — ``claims_match`` compares as strings, so a numeric or boolean claim
    must survive the SQL pre-filter too."""
    variants = [value]
    if value in ("True", "False"):
        variants.append(value == "True")
    else:
        for cast in (int, float):
            try:
                typed = cast(value)
            except (TypeError, ValueError):
                continue
            if str(typed) == value:
                variants.append(typed)
    return variants


def pool_lender_ids(pool) -> set[int]:
    """IDs of the users who are lenders of ``pool`` (a pool or its id).

    Manual members of the pool's lender groups plus users whose stored login
    claims match one of those groups' claim rules. Admins are not included.
    """
    pool_id = getattr(pool, "pk", pool)
    return _effective_member_ids(AccessGroup.objects.filter(lender_pools=pool_id))


def lender_user_ids() -> set[int]:
    """IDs of all users who are lenders of at least one pool (admins not
    included unless they are lenders too). Use as ``filter(id__in=…)``."""
    return _effective_member_ids(
        AccessGroup.objects.filter(lender_pools__isnull=False).distinct()
    )


def admin_user_q(prefix="") -> Q:
    """A ``Q`` on the user model (or on a relation via ``prefix``, e.g.
    ``"borrower__"``) matching app admins — the SQL form of ``is_app_admin``."""
    admin_members = AccessGroup.members.through.objects.filter(
        accessgroup__is_admin=True
    ).values("user_id")
    return (
        Q(**{f"{prefix}is_staff": True})
        | Q(**{f"{prefix}is_superuser": True})
        | Q(**{f"{prefix}pk__in": admin_members})
    )


def admin_user_ids() -> set[int]:
    """IDs of all app admins (``is_staff``/``is_superuser`` or manual members
    of an ``is_admin`` group)."""
    return set(
        get_user_model().objects.filter(admin_user_q()).values_list("id", flat=True)
    )


def lender_grants_by_user(users) -> dict[int, dict[int, set[int]]]:
    """For many users at once (instances with ``claims`` loaded): which groups
    make them a lender of which pool — ``{user_id: {pool_id: {group_id, …}}}``
    (manual and claim-matched groups; a few queries in total)."""
    users = list(users)
    result = {u.pk: {} for u in users}
    if not users:
        return result
    through = AccessGroup.members.through
    lender_pools = AccessGroup.lender_pools.through
    pools_by_group = {}
    for group_id, pool_id in lender_pools.objects.values_list(
        "accessgroup_id", "resourcepool_id"
    ):
        pools_by_group.setdefault(group_id, set()).add(pool_id)
    if not pools_by_group:
        return result

    def grant(user_id, group_id):
        for pool_id in pools_by_group[group_id]:
            result[user_id].setdefault(pool_id, set()).add(group_id)

    for user_id, group_id in through.objects.filter(
        user_id__in=result.keys(), accessgroup_id__in=pools_by_group.keys()
    ).values_list("user_id", "accessgroup_id"):
        grant(user_id, group_id)
    rules = [
        (gid, key, values)
        for gid, key, values in AccessGroup.objects.filter(
            id__in=pools_by_group.keys()
        )
        .exclude(claim_key="")
        .values_list("id", "claim_key", "claim_values")
    ]
    if rules:
        for user in users:
            claims = getattr(user, "claims", None) or {}
            if not claims:
                continue
            for gid, key, values in rules:
                if claims_match(claims, key, values):
                    grant(user.pk, gid)
    return result


def managed_pool_ids_by_user(users) -> dict[int, set[int]]:
    """``managed_pool_ids`` for many users at once (a list of user instances
    with ``claims`` loaded) — a few queries instead of several per user."""
    return {
        user_id: set(grants)
        for user_id, grants in lender_grants_by_user(users).items()
    }


def effective_members(group):
    """The effective members of ``group`` with the source of their membership:
    a list of ``(user, source)`` where source is ``"manual"``, ``"claim"``
    (stored login claims match the group's rule) or, for the system group
    "Administratoren" only, ``"system_admin"`` (``is_staff``/``is_superuser``
    users who aren't manual members). Ordered by name."""
    User = get_user_model()
    found = {u.pk: (u, "manual") for u in group.members.all()}
    if group.claim_key and group.claim_values:
        candidates = User.objects.filter(
            claim_rules_q([(group.claim_key, group.claim_values)])
        ).exclude(pk__in=found.keys())
        for user in candidates:
            if claims_match(user.claims, group.claim_key, group.claim_values):
                found[user.pk] = (user, "claim")
    if group.system_admin:
        for user in User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True)
        ).exclude(pk__in=found.keys()):
            found[user.pk] = (user, "system_admin")
    return sorted(
        found.values(),
        key=lambda pair: (
            (pair[0].get_full_name() or pair[0].username).casefold(),
            pair[0].username,
        ),
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
