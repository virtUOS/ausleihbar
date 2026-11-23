# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Small catalog-level helpers shared by the API and management commands."""
from accounts import roles


def apply_default_access(pool) -> None:
    """Make a newly created pool open to everyone: attach the system group
    "Alle Angemeldeten" (ADR-0021). A pool is open exactly when it carries
    that group; other groups (e.g. LTI course groups) stay untouched."""
    roles.all_users_group().pools.add(pool)
