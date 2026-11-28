# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""QR sticker of a place: ``<shop>/desks/q/<qr_token>`` (scan page of the SPA)."""
from django.conf import settings

from lending.qr import make_qr_png


def place_qr_url(place) -> str:
    return f"{settings.SHOP_BASE_URL.rstrip('/')}/desks/q/{place.qr_token}"


def room_qr_url(room) -> str:
    """Link on a door sign: the free places of the room (SPA page)."""
    return f"{settings.SHOP_BASE_URL.rstrip('/')}/desks?room={room.pk}"


def place_qr_png(place) -> bytes:
    return make_qr_png(place_qr_url(place))
