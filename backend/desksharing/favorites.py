# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Personal favourite places and meeting rooms.

Only the person sees their favourites. A favourite of a place the person may
no longer book (lost rights, deactivated place/room/floor) disappears
silently: it is skipped and deleted when the list is read.
"""
from .models import FavoritePlace, Place
from . import rights


def _usable(user, place) -> bool:
    return place.is_bookable and rights.can_book_place(user, place)


def favorite_place_ids(user) -> list[int]:
    """Ids of the user's usable favourites (oldest first); prunes the rest."""
    rows = list(
        FavoritePlace.objects.filter(user=user)
        .select_related("place__room__floor")
        .prefetch_related("place__access_groups")
    )
    keep, stale = [], []
    for row in rows:
        (keep if _usable(user, row.place) else stale).append(row)
    if stale:
        FavoritePlace.objects.filter(pk__in=[r.pk for r in stale]).delete()
    return [r.place_id for r in keep]


def add_favorite(user, place: Place) -> bool:
    """Mark ``place``; False when the user may not book it."""
    if not _usable(user, place):
        return False
    FavoritePlace.objects.get_or_create(user=user, place=place)
    return True


def remove_favorite(user, place_id: int) -> None:
    FavoritePlace.objects.filter(user=user, place_id=place_id).delete()
