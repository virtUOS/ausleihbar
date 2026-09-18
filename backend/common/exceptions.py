# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)
"""Shared DRF exception handling.

Soft-deleted rows keep their DB ``UNIQUE`` slot occupied (trash Rule B —
intentional, so a restore can't collide with something created in the
meantime). But lookups that only see the default (alive-only) manager — e.g.
DRF's auto-generated ``UniqueValidator`` — don't know that, so recreating an
object with the same unique value as a trashed one sails through validation
and then blows up on the INSERT with an unhandled ``IntegrityError`` (HTTP
500). Translate that into a clean, helpful 400 instead.
"""
from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

INTEGRITY_ERROR_DETAIL = (
    "This value is already in use — it may belong to an item in the trash. "
    "Restore or permanently delete that item first."
)


def exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER``: defer to the default handler first, then
    translate an otherwise-unhandled ``IntegrityError`` into a 400."""
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, IntegrityError):
        return Response({"detail": INTEGRITY_ERROR_DETAIL}, status=400)
    return response
