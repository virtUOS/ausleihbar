# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Test helpers for accounts (role fixtures)."""
from .roles import ensure_pool_lender_group


def make_lender(user, pool):
    """Make ``user`` a lender of ``pool`` via the pool's system group."""
    ensure_pool_lender_group(pool).members.add(user)
    return user


def open_pool(*pools):
    """Open ``pools`` to everyone by attaching "Alle Angemeldeten" (ADR-0021)."""
    from .roles import all_users_group

    group = all_users_group()
    group.pools.add(*pools)
    return pools[0] if len(pools) == 1 else pools


def close_pool(*pools):
    """Undo ``open_pool``: detach "Alle Angemeldeten" from ``pools``."""
    from .roles import all_users_group

    all_users_group().pools.remove(*pools)
