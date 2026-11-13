# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from .models import (
    Absence,
    DeskProfile,
    DeskSettings,
    Feature,
    Floor,
    Place,
    ReleaseRequest,
    Reservation,
    Room,
    Series,
    SwapRequest,
)


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


@admin.register(Absence)
class AbsenceAdmin(admin.ModelAdmin):
    list_display = ("user", "start_date", "end_date", "kind", "created_by")
    list_filter = ("kind",)
    raw_id_fields = ("user", "created_by")


@admin.register(SwapRequest)
class SwapRequestAdmin(admin.ModelAdmin):
    list_display = ("from_reservation", "to_reservation", "status", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("from_reservation", "to_reservation")


@admin.register(ReleaseRequest)
class ReleaseRequestAdmin(admin.ModelAdmin):
    list_display = ("reservation", "requester", "show_name", "status", "created_at")
    list_filter = ("status", "show_name")
    raw_id_fields = ("reservation", "requester")


@admin.register(DeskProfile)
class DeskProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "hide_name")
    list_filter = ("hide_name",)
    raw_id_fields = ("user",)
