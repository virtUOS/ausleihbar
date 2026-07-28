# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""QR-code helpers for the device-handout flow (concept §6.2).

Two kinds of code are used:
- the borrower's **pickup code** (the booking code, e.g. ``R-00042``) shown in
  the confirmation email and scanned by the lender to open the handout;
- the **device code** printed on each resource — a URL ``<shop>/r/<qr_id>`` so a
  normal QR reader lands on the product page (manuals etc.), while the lender's
  app recognises it as a unit to hand out.
"""
import io

import qrcode
from django.conf import settings


def make_qr_png(data: str) -> bytes:
    """Render ``data`` as a PNG QR code and return the raw bytes."""
    image = qrcode.make(data)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def device_qr_url(resource) -> str:
    """The URL encoded on a resource's QR sticker."""
    base = settings.SHOP_BASE_URL.rstrip("/")
    return f"{base}/r/{resource.qr_code_id}"


def pickup_qr_url(booking) -> str:
    """The URL encoded on the borrower's pickup QR.

    Scanned by a normal reader it opens the booking overview (for the signed-in
    borrower); the lending desk's scanner extracts the code from it.
    """
    base = settings.SHOP_BASE_URL.rstrip("/")
    return f"{base}/bookings/{booking.code}"
