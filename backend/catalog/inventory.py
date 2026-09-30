# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Inventory helpers (issue #50)."""
from .models import Resource


def default_qr_code_id(inventory_number):
    """QR code ID for a new resource when none is given: ``QR-<inventory
    number>``, or ``QR-<inventory number>-<n>`` with the lowest free n ≥ 2
    if that is taken. Matches the ``suggest-number`` proposal for suggested
    inventory numbers. Printed labels encode this ID, so it is only ever
    assigned once and never recomputed.

    Trashed (soft-deleted) resources keep their ``qr_code_id`` in the table,
    where it is still unique, so the scan uses ``all_objects``."""
    base = f"QR-{inventory_number}"
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
