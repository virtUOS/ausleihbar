# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from .models import DeskSettings, Feature, Floor, Place, Room


@admin.register(DeskSettings)
class DeskSettingsAdmin(admin.ModelAdmin):
    list_display = ("pool", "enabled", "assistant_group")
    list_filter = ("enabled",)


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("name", "pool")


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("name", "building", "pool", "position")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "floor", "kind")


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "room", "kind", "is_active")
    list_filter = ("kind", "is_active")
    readonly_fields = ("qr_token",)
