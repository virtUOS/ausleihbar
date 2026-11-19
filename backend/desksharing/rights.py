# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing rights per department (pool).

- **admin pools**: pools the user lends (``roles.managed_pool_ids``), plus all
  desksharing-enabled pools for app admins.
- **assistant pools**: admin pools plus pools whose ``assistant_group`` the user
  is an effective member of.
- **member pools**: enabled pools whose access groups include the user (an open
  pool without groups never qualifies), plus enabled admin pools.

Results are memoised on the user's roles cache (``accounts.roles``), so they
share its per-request lifetime and invalidation.
"""
from django.db.models import Q

from accounts import roles

from .models import DeskSettings


def _enabled():
    """Settings of departments with desksharing on (an inactive pool never counts)."""
    return DeskSettings.objects.filter(enabled=True, pool__is_active=True)


def _enabled_pool_ids() -> set[int]:
    return set(_enabled().values_list("pool_id", flat=True))


def _memo(user, key, compute) -> set[int]:
    if not roles._authenticated(user):
        return set()
    cache = roles._cache(user)
    if key not in cache:
        cache[key] = frozenset(compute())
    return set(cache[key])


def admin_pool_ids(user) -> set[int]:
    def compute():
        ids = roles.managed_pool_ids(user)
        if roles.is_app_admin(user):
            ids |= _enabled_pool_ids()
        return ids

    return _memo(user, "desk_admin_pool_ids", compute)


def assistant_pool_ids(user) -> set[int]:
    def compute():
        ids = admin_pool_ids(user)
        groups = roles.group_ids(user)
        if groups:
            ids |= set(
                _enabled()
                .filter(assistant_group_id__in=groups)
                .values_list("pool_id", flat=True)
            )
        return ids

    return _memo(user, "desk_assistant_pool_ids", compute)


def member_pool_ids(user) -> set[int]:
    def compute():
        enabled = _enabled_pool_ids()
        groups = roles.group_ids(user)
        via_groups = set()
        if groups:
            via_groups = set(
                _enabled()
                .filter(pool__access_groups__in=groups)
                .values_list("pool_id", flat=True)
            )
        return via_groups | (admin_pool_ids(user) & enabled)

    return _memo(user, "desk_member_pool_ids", compute)


def can_book_place(user, place) -> bool:
    """Pool membership, plus the place's own access groups when it has any
    (department admins always qualify)."""
    pool_id = place.pool_id
    if pool_id not in member_pool_ids(user):
        return False
    # ``.all()`` uses a prefetch (free place lists) when there is one.
    group_ids = {g.pk for g in place.access_groups.all()}
    if not group_ids:
        return True
    return pool_id in admin_pool_ids(user) or bool(group_ids & roles.group_ids(user))


def may_keep_booking(user, place, pool_id) -> bool:
    """Lost-rights rule for a booking made in department ``pool_id``
    (``Reservation.pool``): the holder keeps it while still a member there,
    and, while the place still belongs to that department, while allowed to
    book the place itself. A place moved elsewhere doesn't end the booking."""
    if place.pool_id == pool_id:
        return can_book_place(user, place)
    return pool_id is not None and pool_id in member_pool_ids(user)


def member_user_ids(pool_id: int, *, enabled_only: bool = True) -> set[int]:
    """Users who are members of an enabled department (the set form of
    ``member_pool_ids``): effective members (manual or claim) of the pool's
    access groups and lender groups, plus app admins. Empty when the
    department is not enabled (unless ``enabled_only=False``)."""
    from accounts.models import AccessGroup

    if enabled_only and pool_id not in _enabled_pool_ids():
        return set()
    groups = AccessGroup.objects.filter(
        Q(pools__id=pool_id) | Q(lender_pools__id=pool_id)
    ).distinct()
    return roles._effective_member_ids(groups) | roles.admin_user_ids()


def can_admin_pool(user, pool_id) -> bool:
    """App admins administer every department (and unassigned objects,
    ``pool_id=None``); department admins their own."""
    if roles.is_app_admin(user):
        return True
    return pool_id is not None and pool_id in admin_pool_ids(user)


def can_admin_room(user, room) -> bool:
    """May edit the room (its default department ``Room.pool``) and add
    places to it."""
    return can_admin_pool(user, room.pool_id)


def can_admin_place(user, place) -> bool:
    """May edit or delete the place (its effective department ``Place.pool``)."""
    return can_admin_pool(user, place.pool_id)
