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
    list_display = ("name", "claim_key")
    search_fields = ("name",)
    filter_horizontal = ("members", "pools")


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
