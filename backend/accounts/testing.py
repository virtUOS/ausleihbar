# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Test helpers for accounts (role fixtures)."""
from .roles import ensure_pool_lender_group


def make_lender(user, pool):
    """Make ``user`` a lender of ``pool`` via the pool's system group."""
    ensure_pool_lender_group(pool).members.add(user)
    return user
