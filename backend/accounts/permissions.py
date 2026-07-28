# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Custom DRF permissions."""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Allow only admins (Django staff/superusers) — for catalog management."""

    message = "Only admins may access this."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (user.is_staff or user.is_superuser)
        )


class IsLenderOrAdmin(BasePermission):
    """Allow admins (staff/superuser) and lenders (who manage a pool)."""

    message = "Only lenders or admins may access this."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser or user.pool_memberships.exists())
        )
