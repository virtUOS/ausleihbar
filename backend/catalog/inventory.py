# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Inventory helpers (issue #50)."""
import re
import uuid

from .models import Resource

# qr_code_id max_length is 255; leave room for the "-<n>" clash suffix.
_MAX_BASE_LENGTH = 240


def default_qr_code_id(inventory_number):
    """QR code ID for a new resource when none is given: ``QR-<slug>``, or
    ``QR-<slug>-<n>`` with the lowest free n ≥ 2 if that is taken. ``<slug>``
    is the inventory number reduced to URL-safe characters (anything outside
    ``A-Za-z0-9._~-`` becomes ``-``), because stickers encode
    ``<shop>/r/<qr_code_id>`` unescaped and the scanner/route expect a single
    path segment. If nothing usable remains a short random token is used; the
    base is capped so the result always fits the 255-character column.
    Matches the ``suggest-number`` proposal for typical inventory numbers.
    Printed labels encode this ID, so it is only ever assigned once and never
    recomputed.

    Trashed (soft-deleted) resources keep their ``qr_code_id`` in the table,
    where it is still unique, so the scan uses ``all_objects``."""
    slug = re.sub(r"[^A-Za-z0-9._~-]+", "-", inventory_number or "").strip("-")
    slug = slug[: _MAX_BASE_LENGTH - len("QR-")].strip("-")
    if not slug:
        slug = uuid.uuid4().hex[:8]
    base = f"QR-{slug}"
    taken = set(
        Resource.all_objects.filter(qr_code_id__startswith=base).values_list(
            "qr_code_id", flat=True
        )
    )
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"
