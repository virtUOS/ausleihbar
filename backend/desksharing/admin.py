# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from .models import DeskSettings, Feature, Floor, Place, Reservation, Room, Series


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


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("place", "period", "holder", "status", "release_reason")
    list_filter = ("status", "release_reason")
    raw_id_fields = ("place", "holder", "booked_by")
    readonly_fields = ("group", "created_at")


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ("place", "holder", "weekdays", "valid_from", "valid_until", "cancelled_at")
    raw_id_fields = ("place", "holder", "booked_by")
