# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Access groups of rooms and places.

A room's groups are the default of its places: a place follows them (its set
equals the room's) unless ``Place.groups_overridden`` — then it keeps exactly
its own. Only the rows whose set really changes are written, so the
lost-rights signal on ``Place.access_groups`` stays minimal.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import AccessGroup

from . import rights
from .models import Place, Room

SYSTEM_GROUP_MESSAGE = "System and admin groups cannot restrict a place."


def is_ordinary(group) -> bool:
    return not (group.system_pool_id or group.system_admin or group.is_admin)


def _ids(groups) -> set[int]:
    return {g.pk for g in groups}


def _set_groups(manager, target: set[int], current: set[int]) -> bool:
    """Make ``manager`` hold exactly ``target``; touches only the difference."""
    if target == current:
        return False
    if current - target:
        manager.remove(*(current - target))
    if target - current:
        manager.add(*(target - current))
    return True


def set_place_groups(place, group_ids, *, overridden: bool) -> bool:
    """Give ``place`` exactly ``group_ids`` and the override flag. Returns
    whether the groups or the flag changed."""
    current = {g.pk for g in place.access_groups.all()}
    changed = _set_groups(place.access_groups, set(group_ids), current)
    if place.groups_overridden != overridden:
        Place.objects.filter(pk=place.pk).update(groups_overridden=overridden)
        place.groups_overridden = overridden
        changed = True
    return changed


def sync_from_room(place) -> bool:
    """Copy the room's groups to ``place`` (it follows its room)."""
    return set_place_groups(
        place, _ids(place.room.access_groups.all()), overridden=False
    )


def set_room_groups(room, groups) -> bool:
    """Set a room's default groups; returns whether they changed."""
    return _set_groups(
        room.access_groups, {g.pk for g in groups}, _ids(room.access_groups.all())
    )


def hand_down(room) -> set[int]:
    """Copy ``room``'s groups to the places that follow it; returns the ids
    of the places whose set changed."""
    target = _ids(room.access_groups.all())
    changed = set()
    for place in room.places.filter(groups_overridden=False).prefetch_related("access_groups"):
        current = {g.pk for g in place.access_groups.all()}
        if _set_groups(place.access_groups, target, current):
            changed.add(place.pk)
    return changed


def _groups(ids, field) -> dict[int, AccessGroup]:
    found = {g.pk: g for g in AccessGroup.objects.filter(pk__in=ids)}
    if set(ids) - set(found):
        raise ValidationError({field: "Unknown access group."})
    return found


@transaction.atomic
def apply(*, actor, rooms=(), places=(), add_ids=(), remove_ids=(), follow_room=False) -> int:
    """Change groups of rooms and places in one transaction; returns the
    number of places changed.

    Rooms: their set ∪ ``add_ids`` − ``remove_ids``, handed down to the places
    that follow. Places: ``follow_room`` takes the room's groups again
    (``add_ids``/``remove_ids`` ignored for them); otherwise their own set ∪
    add − remove and the place is overridden. A place named explicitly gets
    the place treatment even when its room is selected too. Rights are
    checked up front for the whole selection (nothing changes on refusal).
    """
    add, remove = set(add_ids), set(remove_ids)
    rooms, places = list(rooms), list(places)
    if not rooms and not places:
        raise ValidationError({"room_ids": "Choose rooms or places."})
    if not add and not remove and not (follow_room and places):
        raise ValidationError({"add_ids": "Choose groups to add or remove."})
    found = _groups(add, "add_ids")
    _groups(remove, "remove_ids")
    if any(not is_ordinary(g) for g in found.values()):
        raise ValidationError({"add_ids": SYSTEM_GROUP_MESSAGE})
    if any(not rights.can_admin_room(actor, room) for room in rooms) or any(
        not rights.can_admin_place(actor, place) for place in places
    ):
        raise PermissionDenied("You do not administer this department.")

    changed: set[int] = set()
    if add or remove:
        for room in rooms:
            target = (_ids(room.access_groups.all()) | add) - remove
            _set_groups(room.access_groups, target, _ids(room.access_groups.all()))
            changed |= hand_down(room)
    for place in Place.objects.filter(pk__in=[p.pk for p in places]).select_related("room"):
        if follow_room:
            if sync_from_room(place):
                changed.add(place.pk)
        else:
            own = {g.pk for g in place.access_groups.all()}
            if set_place_groups(place, (own | add) - remove, overridden=True):
                changed.add(place.pk)
    return len(changed)
