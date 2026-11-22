# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing rights per department (pool).

- **admin pools**: pools the user lends (``roles.managed_pool_ids``), plus all
  desksharing-enabled pools for app admins.
- **assistant pools**: admin pools plus pools whose ``assistant_group`` the user
  is an effective member of.
- **member pools**: enabled pools whose access groups include the user (an open
  pool without groups never qualifies), plus enabled admin pools.
- **guest pools** (ADR-0018): enabled pools the user is not a member of but
  holds a group of one of their places' own access groups — the user sees and
  books only those places.

The system group "Alle Angemeldeten" (``AccessGroup.system_all``, ADR-0021)
never counts at department level (membership, ``member_user_ids``, assistants):
on a pool it opens lending only. On a room/place it makes every user a guest
of that place — without person data (``sees_people``, privacy (2)).

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
                # Never a rights group (refused on save; ORM writes too).
                .filter(
                    assistant_group_id__in=groups,
                    assistant_group__system_all=False,
                    assistant_group__system_course__isnull=True,
                )
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
                # LTI course groups and "Alle Angemeldeten" open a pool's
                # lending only, never desks (one filter(): same group row).
                .filter(
                    pool__access_groups__in=groups,
                    pool__access_groups__system_course__isnull=True,
                    pool__access_groups__system_all=False,
                )
                .values_list("pool_id", flat=True)
            )
        return via_groups | (admin_pool_ids(user) & enabled)

    return _memo(user, "desk_member_pool_ids", compute)


def _guest_places(user, *, real_only: bool = False) -> dict[int, frozenset[int]]:
    """Per enabled department the user is *not* a member of: the active places
    (active room and floor) whose access groups include one of the user's
    groups. ``real_only``: only through a group other than "Alle
    Angemeldeten" (such guests see people, ``sees_people``). One query per
    request for both variants (memoised); the single source of the guest
    sets below."""
    from .models import Place

    def compute():
        groups = roles.group_ids(user)
        if not groups:
            return {}, {}
        members = member_pool_ids(user)
        out: dict[int, set[int]] = {}
        real: dict[int, set[int]] = {}
        for pk, pool_id, via_all_users in (
            Place.objects.filter(
                pool__in=_enabled().values("pool_id"),
                is_active=True,
                room__is_active=True,
                room__floor__is_active=True,
                access_groups__in=groups,
            )
            # Of the matched group (same join as the filter): is it
            # "Alle Angemeldeten"? One row per matched group.
            .values_list("pk", "pool_id", "access_groups__system_all")
        ):
            if pool_id in members:
                continue
            out.setdefault(pool_id, set()).add(pk)
            if not via_all_users:
                real.setdefault(pool_id, set()).add(pk)
        return out, real

    # Not ``_memo`` (that freezes a set): same cache, dicts of frozensets.
    if not roles._authenticated(user):
        return {}
    cache = roles._cache(user)
    if "desk_guest_places" not in cache:
        out, real = compute()
        cache["desk_guest_places"] = {k: frozenset(v) for k, v in out.items()}
        cache["desk_real_guest_places"] = {k: frozenset(v) for k, v in real.items()}
    return cache["desk_real_guest_places" if real_only else "desk_guest_places"]


def guest_pool_ids(user) -> set[int]:
    """Enabled departments the user is *not* a member of but may book single
    places in (through the places' own access groups)."""
    return set(_guest_places(user))


def visible_pool_ids(user) -> set[int]:
    """Departments the user sees in the desk area: member plus guest pools."""
    return member_pool_ids(user) | guest_pool_ids(user)


def is_visible_pool(user, pool_id) -> bool:
    """``pool_id`` in ``visible_pool_ids`` — members don't pay the guest query."""
    return pool_id in member_pool_ids(user) or pool_id in _guest_places(user)


def guest_place_ids(user, pool_id) -> set[int] | None:
    """``None`` for members of the pool (no place filter); otherwise the ids of
    the pool's active places the user's groups open to them (maybe empty)."""
    if pool_id in member_pool_ids(user):
        return None
    return set(_guest_places(user).get(pool_id, ()))


def sees_people(user, place) -> bool:
    """Whether ``user`` may see person data (holders, bookers, comments,
    fixed owners) on ``place``: app admins, the department's members,
    assistants and admins, and guests through a place group other than
    "Alle Angemeldeten". Whoever reaches the place only through that group
    sees occupancy without names (privacy (2), ADR-0021). Memoised per
    request (no query per place)."""
    if not roles._authenticated(user):
        return False
    if roles.is_app_admin(user):
        return True
    pool_id = place.pool_id
    if pool_id is None:
        return False
    if pool_id in member_pool_ids(user) or pool_id in assistant_pool_ids(user):
        return True
    return place.pk in _guest_places(user, real_only=True).get(pool_id, ())


def can_book_place(user, place) -> bool:
    """A place without access groups needs department membership; one with
    groups opens to the members of those groups (guests, no membership
    needed) and to the department's admins."""
    pool_id = place.pool_id
    if pool_id is None or pool_id not in _memo(
        user, "desk_enabled_pool_ids", _enabled_pool_ids
    ):
        return False
    # ``.all()`` uses a prefetch (free place lists) when there is one.
    group_ids = {g.pk for g in place.access_groups.all()}
    if not group_ids:
        return pool_id in member_pool_ids(user)
    return pool_id in admin_pool_ids(user) or bool(group_ids & roles.group_ids(user))


def may_keep_booking(user, place, pool_id) -> bool:
    """Lost-rights rule for a booking made in department ``pool_id``
    (``Reservation.pool``): the holder keeps it while still a member there,
    and, while the place still belongs to that department, while allowed to
    book the place itself. A place moved elsewhere doesn't end the booking."""
    if place.pool_id == pool_id:
        return can_book_place(user, place)
    if pool_id is None:
        return False
    if pool_id in member_pool_ids(user):
        return True
    # A guest keeps it while still in one of the place's own groups.
    group_ids = {g.pk for g in place.access_groups.all()}
    return bool(group_ids & roles.group_ids(user))


def member_user_ids(pool_id: int, *, enabled_only: bool = True) -> set[int]:
    """Users who are members of an enabled department (the set form of
    ``member_pool_ids``): effective members (manual or claim) of the pool's
    access groups and lender groups, plus app admins. Empty when the
    department is not enabled (unless ``enabled_only=False``)."""
    from accounts.models import AccessGroup

    if enabled_only and pool_id not in _enabled_pool_ids():
        return set()
    # "Alle Angemeldeten" on the pool opens lending only: never a member
    # list (it has no stored members anyway).
    groups = AccessGroup.objects.filter(
        Q(pools__id=pool_id) | Q(lender_pools__id=pool_id)
    ).filter(system_all=False).distinct()
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
