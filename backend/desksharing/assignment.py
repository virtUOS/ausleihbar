# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Assigning rooms and places to departments (``ResourcePool``).

Only app admins assign. Existing reservations are never touched — bookings run
on after a place changes department.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts import roles
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
    return Place.objects.filter(room_id__in=room_ids, pool_overridden=False).exclude(
        pool=pool
    ).update(pool=pool)


@transaction.atomic
def assign_places(places, pool, *, actor, follow_room: bool = False) -> int:
    """Give places a department of their own (``pool_overridden``) or, with
    ``follow_room``, let them take their room's department again."""
    _require_admin(actor)
    place_ids = [place.pk for place in places]
    queryset = Place.objects.filter(pk__in=place_ids)
    if not follow_room:
        return queryset.update(pool=pool, pool_overridden=True)
    changed = 0
    for place in queryset.select_related("room"):
        place.pool_id = place.room.pool_id
        place.pool_overridden = False
        place.save(update_fields=["pool", "pool_overridden"])
        changed += 1
    return changed


@transaction.atomic
def add_department_groups(pool, *, access_group_ids, admin_group_ids, actor) -> None:
    """Add-only: make the groups access groups (``pools``) or department
    admins (``lender_pools``) of ``pool``. Nothing is ever removed, so the
    requesting admin can't lock themselves out here."""
    _require_admin(actor)
    access_ids, admin_ids = set(access_group_ids), set(admin_group_ids)
    found = {g.pk: g for g in AccessGroup.objects.filter(pk__in=access_ids | admin_ids)}
    if set(found) != access_ids | admin_ids:
        raise ValidationError({"access_group_ids": "Unknown access group."})
    for group_id in admin_ids:
        group = found[group_id]
        if group.is_system:  # rights of system groups are locked
            raise ValidationError(
                {"admin_group_ids": "This field can't be changed on a system group."}
            )
        if group.is_admin and group.claim_key:  # same rule as AccessGroup.clean
            raise ValidationError(
                {"admin_group_ids": "Admin rights can't come from a login rule — "
                                    "remove the claim rule first."}
            )
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
    if not pool.access_groups.exists():
        raise ValidationError(
            {"pool": "Desksharing needs at least one access group on the pool."}
        )
    settings.enabled = True
    settings.save(update_fields=["enabled"])
