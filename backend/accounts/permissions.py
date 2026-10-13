# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Custom DRF permissions."""
from rest_framework.permissions import BasePermission

from . import roles


class IsAdmin(BasePermission):
    """Allow only app admins (``accounts.roles.is_app_admin``)."""

    message = "Only admins may access this."

    def has_permission(self, request, view):
        user = request.user
        return roles.is_app_admin(user)


class IsLenderOrAdmin(BasePermission):
    """Allow admins and lenders (who manage a pool) — ``roles.is_lender``."""

    message = "Only lenders or admins may access this."

    def has_permission(self, request, view):
        user = request.user
        return roles.is_lender(user)
