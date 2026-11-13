# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from . import privacy

from .models import (
    Absence,
    DeskProfile,
    DeskSettings,
    Feature,
    Floor,
    FloorTemplate,
    NotificationPreference,
    Place,
    ReleaseRequest,
    Reservation,
    Room,
    Series,
    SwapRequest,
)


# Opt-out also in the operators' lists: hidden desk holders and anonymous
# requesters appear as in the app. (Not access control: the detail forms and
# the database still hold the person, as they must for mails and check-in.)
HIDDEN_LABEL = "Person (verborgen)"


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


@admin.register(FloorTemplate)
class FloorTemplateAdmin(admin.ModelAdmin):
    list_display = ("floor", "content_type", "updated_at")
    readonly_fields = ("floor", "content_type", "updated_at")
    exclude = ("data",)

    def get_queryset(self, request):
        return super().get_queryset(request).defer("data")


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
    list_display = ("place", "period", "holder_display", "status", "release_reason")
    list_select_related = ("place", "holder")

    @admin.display(description="holder")
    def holder_display(self, obj):
        if obj.holder_id is None:
            return "-"
        return HIDDEN_LABEL if privacy.is_hidden(obj) else str(obj.holder)
    list_filter = ("status", "release_reason")
    raw_id_fields = ("place", "holder", "booked_by")
    readonly_fields = ("group", "created_at")


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = (
        "place", "holder_display", "weekdays", "valid_from", "valid_until", "cancelled_at"
    )
    list_select_related = ("place", "holder")

    @admin.display(description="holder")
    def holder_display(self, obj):
        if obj.holder_id is None:
            return "-"
        return HIDDEN_LABEL if privacy.series_hidden(obj) else str(obj.holder)
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
    list_display = ("reservation", "requester_display", "show_name", "status", "created_at")
    list_select_related = ("requester",)

    @admin.display(description="requester")
    def requester_display(self, obj):
        return str(obj.requester) if obj.show_name else HIDDEN_LABEL
    list_filter = ("status", "show_name")
    raw_id_fields = ("reservation", "requester")


@admin.register(DeskProfile)
class DeskProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "hide_name")
    list_filter = ("hide_name",)
    raw_id_fields = ("user",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "channel")
    list_filter = ("event", "channel")
    raw_id_fields = ("user",)
