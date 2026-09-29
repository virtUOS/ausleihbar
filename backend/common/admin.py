# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from .models import CspViolation


@admin.register(CspViolation)
class CspViolationAdmin(admin.ModelAdmin):
    """Aggregated CSP reports (issue #44) — read-only; delete once fixed."""

    list_display = ("directive", "blocked", "page", "count", "first_seen", "last_seen")
    list_filter = ("directive",)
    search_fields = ("blocked", "page")
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
