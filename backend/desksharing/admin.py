# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from . import privacy

from .models import (
    Absence,
    Building,
    DeskAdminSetting,
    DeskProfile,
    FavoritePlace,
    DeskSettings,
    Feature,
    FeatureImage,
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
    fieldsets = (
        (None, {"fields": ("pool", "enabled", "assistant_group", "business_hours")}),
        ("Grace and release", {"fields": (
            "desk_grace_normal_min", "desk_grace_short_min", "desk_scarcity_free_below",
            "room_grace_normal_min", "room_grace_short_min", "room_scarcity_free_below",
        )}),
        ("Booking window", {"fields": (
            "cycle_months", "transition_weeks", "advance_months", "advance_days",
            "advance_places",
        )}),
        ("Privacy", {"fields": ("retention_days",)}),
    )


@admin.register(DeskAdminSetting)
class DeskAdminSettingAdmin(admin.ModelAdmin):
    list_display = ("place_name_pattern",)


class FeatureImageInline(admin.TabularInline):
    model = FeatureImage
    extra = 0


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name", "description")
    inlines = [FeatureImageInline]


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description", "address")


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("name", "building", "position")
    list_select_related = ("building",)


@admin.register(FloorTemplate)
class FloorTemplateAdmin(admin.ModelAdmin):
    list_display = ("floor", "content_type", "updated_at")
    readonly_fields = ("floor", "content_type", "updated_at")
    exclude = ("data",)

    def get_queryset(self, request):
        return super().get_queryset(request).defer("data")


GROUPS_NOTE = (
    "Access groups are edited in the app (Places workspace): a room's groups are "
    "handed down to the places that follow it."
)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "floor", "pool", "kind")
    list_select_related = ("floor__building", "pool")
    # Departments change only through the assignment (/manage/assign/);
    # access groups only through the app (room form, /manage/place-groups/),
    # which hands them down to the following places.
    readonly_fields = ("pool", "access_groups", "groups_note")

    @admin.display(description="note")
    def groups_note(self, obj):
        return GROUPS_NOTE


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "room", "pool", "pool_overridden", "groups_overridden", "kind", "is_active",
    )
    list_select_related = ("room__floor__building", "pool")
    list_filter = ("kind", "is_active", "pool_overridden", "groups_overridden")
    # Departments change only through the assignment (/manage/assign/);
    # access groups only through the app, which keeps a following place's set
    # equal to its room's (ADR-0019).
    readonly_fields = (
        "qr_token", "pool", "pool_overridden", "access_groups", "groups_overridden", "groups_note",
    )

    @admin.display(description="note")
    def groups_note(self, obj):
        return GROUPS_NOTE


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
    # The department it was made in; set on creation only.
    readonly_fields = ("pool",)

    @admin.display(description="holder")
    def holder_display(self, obj):
        if obj.holder_id is None:
            return "-"
        return HIDDEN_LABEL if privacy.series_hidden(obj) else str(obj.holder)
    raw_id_fields = ("place", "holder", "booked_by")


@admin.register(Absence)
class AbsenceAdmin(admin.ModelAdmin):
    list_display = ("user", "start_date", "end_date", "created_by")
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
    list_filter = ("status", "show_name", "limits_waived")
    raw_id_fields = ("reservation", "requester", "result", "series")


@admin.register(DeskProfile)
class DeskProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "hide_name")
    list_filter = ("hide_name",)
    raw_id_fields = ("user",)


@admin.register(FavoritePlace)
class FavoritePlaceAdmin(admin.ModelAdmin):
    list_display = ("user", "place", "created_at")
    raw_id_fields = ("user", "place")
    list_select_related = ("user", "place")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "channel")
    list_filter = ("event", "channel")
    raw_id_fields = ("user",)
