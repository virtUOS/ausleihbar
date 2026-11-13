# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing notifications (completed in a later task)."""

BOOKED_FOR_YOU = "booked_for_you"
ADMIN_CHANGED = "admin_changed"
SWAP_REQUEST = "swap_request"
SWAP_ANSWER = "swap_answer"
RELEASE_REQUEST = "release_request"
RELEASE_ANSWER = "release_answer"


def notify(user, event: str, context: dict) -> None:
    """Send ``event`` to ``user`` through their preferred channel. No-op stub."""
    return None
