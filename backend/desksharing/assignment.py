# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Assigning rooms and places to departments (``ResourcePool``).

Only app admins assign. Existing reservations are never touched — bookings run
on after a place changes department.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery

from accounts import roles
from accounts.serializers import SYSTEM_GROUP_LOCKED
from accounts.models import AccessGroup

from .models import DeskSettings, Place, Room


def _require_admin(actor) -> None:
    if not roles.is_app_admin(actor):
        raise PermissionDenied("Only administrators may assign departments.")


@transaction.atomic
def assign_rooms(rooms, pool, *, actor) -> int:
    """Set ``Room.pool``; hand it down to the places that follow their room.
    ``pool=None`` unassigns (places with their own department stay).
    Returns the number of places changed."""
    _require_admin(actor)
    room_ids = [room.pk for room in rooms]
    Room.objects.filter(pk__in=room_ids).update(pool=pool)
    changed = Place.objects.filter(room_id__in=room_ids, pool_overridden=False).exclude(
        pool=pool
    ).update(pool=pool)
    _resync_groups(room_ids)
    return changed


def _resync_groups(room_ids) -> None:
    """Places that now share their room's department take its groups again
    (only followers; see ``place_groups``)."""
    from . import place_groups

    for room in Room.objects.filter(pk__in=set(room_ids)).prefetch_related("access_groups"):
        place_groups.hand_down(room)


@transaction.atomic
def assign_places(places, pool, *, actor, follow_room: bool = False) -> int:
    """Give places a department of their own (``pool_overridden``) or, with
    ``follow_room``, let them take their room's department again."""
    _require_admin(actor)
    queryset = Place.objects.filter(pk__in=[place.pk for place in places])
    room_ids = list(queryset.values_list("room_id", flat=True))
    if not follow_room:
        changed = queryset.exclude(pool=pool, pool_overridden=True).update(
            pool=pool, pool_overridden=True
        )
    else:
        room_pool = Subquery(Room.objects.filter(pk=OuterRef("room_id")).values("pool_id")[:1])
        changed = queryset.exclude(
            pool_overridden=False, pool_id=room_pool
        ).update(pool=room_pool, pool_overridden=False)
    _resync_groups(room_ids)
    return changed


@transaction.atomic
def add_department_groups(pool, *, access_group_ids, admin_group_ids, actor) -> None:
    """Add-only: make the groups access groups (``pools``) or department
    admins (``lender_pools``) of ``pool``. Nothing is ever removed, so the
    requesting admin can't lock themselves out here."""
    _require_admin(actor)
    access_ids, admin_ids = set(access_group_ids), set(admin_group_ids)
    found = {g.pk: g for g in AccessGroup.objects.filter(pk__in=access_ids | admin_ids)}
    for field, ids in (("access_group_ids", access_ids), ("admin_group_ids", admin_ids)):
        if ids - set(found):
            raise ValidationError({field: "Unknown access group."})
    for group_id in admin_ids:
        if found[group_id].is_system:  # rights of system groups are locked
            raise ValidationError({"admin_group_ids": SYSTEM_GROUP_LOCKED})
    for group_id in access_ids:
        if found[group_id].is_course_group:  # gates its course link's pool only
            raise ValidationError({"access_group_ids": SYSTEM_GROUP_LOCKED})
    for group_id in access_ids:
        found[group_id].pools.add(pool)
    for group_id in admin_ids:
        found[group_id].lender_pools.add(pool)


@transaction.atomic
def ensure_desksharing_enabled(pool) -> None:
    """Switch desksharing on for the department; it needs an access group."""
    settings = DeskSettings.for_pool(pool)
    if settings.enabled:
        return
    # LTI course groups and "Alle Angemeldeten" don't count (they only open
    # the pool's lending).
    if not pool.access_groups.filter(system_course__isnull=True, system_all=False).exists():
        raise ValidationError(
            {"pool": "Desksharing needs at least one access group on the pool."}
        )
    settings.enabled = True
    settings.save(update_fields=["enabled"])
