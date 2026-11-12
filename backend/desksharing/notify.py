# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing notifications (completed in a later task)."""

BOOKED_FOR_YOU = "booked_for_you"
ADMIN_CHANGED = "admin_changed"


def notify(user, event: str, context: dict) -> None:
    """Send ``event`` to ``user`` through their preferred channel. No-op stub."""
    return None
