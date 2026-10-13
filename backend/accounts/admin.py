# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Admin registrations for accounts."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AccessGroup, PoolMembership, Strike, StrikeSetting, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "is_staff", "is_superuser", "verified_at")


@admin.register(AccessGroup)
class AccessGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "claim_key", "is_admin", "system_pool", "system_admin")
    list_filter = ("is_admin", "system_admin")
    search_fields = ("name",)
    filter_horizontal = ("members", "pools", "lender_pools")
    readonly_fields = ("system_pool", "system_admin")
    # Locked on system groups (pool lender groups, "Administratoren"): only
    # members, description and access pools stay editable.
    system_locked_fields = (
        "name", "claim_key", "claim_values", "lender_pools", "is_admin",
        "system_pool", "system_admin",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.is_system:
            return self.system_locked_fields
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        # Bulk "delete selected" skips has_delete_permission(obj): keep system
        # groups out of it.
        super().delete_queryset(
            request, queryset.filter(system_pool__isnull=True, system_admin=False)
        )


@admin.register(Strike)
class StrikeAdmin(admin.ModelAdmin):
    list_display = ("user", "booking", "issued_by", "created_at", "expires_at")
    search_fields = ("user__username",)
    raw_id_fields = ("user", "booking", "issued_by")


@admin.register(StrikeSetting)
class StrikeSettingAdmin(admin.ModelAdmin):
    list_display = ("strike_expiry_days",)


@admin.register(PoolMembership)
class PoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "resource_pool", "role")
    list_filter = ("role", "resource_pool")
    search_fields = ("user__username",)
