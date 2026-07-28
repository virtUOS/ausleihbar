# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Optional per-deployment creation caps (set in the environment).

Each cap is ``None`` when unset, meaning unlimited. ``check_create_allowed``
raises a DRF validation error at API creation points; the user cap is enforced
separately in the OIDC backend (a non-DRF context).
"""

from rest_framework.exceptions import ValidationError


def is_reached(limit, current_count):
    """Whether a creation would exceed ``limit`` (``None`` = unlimited)."""
    return limit is not None and current_count >= limit


def check_create_allowed(limit, current_count, label):
    """Raise a 400 when the cap for ``label`` is reached; no-op if unlimited."""
    if is_reached(limit, current_count):
        raise ValidationError(
            f"The configured maximum number of {label} ({limit}) has been "
            "reached. Raise the limit in the server configuration to add more."
        )
