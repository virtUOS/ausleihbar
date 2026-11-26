# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views, views_admin, views_display, views_display_admin

router = DefaultRouter()
router.register("desks/manage/buildings", views.BuildingViewSet, basename="desk-building")
router.register("desks/manage/features", views.FeatureViewSet, basename="desk-feature")
router.register("desks/manage/floors", views.FloorViewSet, basename="desk-floor")
router.register("desks/manage/rooms", views.RoomViewSet, basename="desk-room")
router.register("desks/manage/places", views.PlaceViewSet, basename="desk-place")
router.register("desks/series", views.SeriesViewSet, basename="desk-series")
router.register("desks/swap-requests", views.SwapRequestViewSet, basename="desk-swap-request")
router.register(
    "desks/release-requests", views.ReleaseRequestViewSet, basename="desk-release-request"
)
router.register("desks/reservations", views.ReservationViewSet, basename="desk-reservation")

urlpatterns = [
    path("displays/frame/", views_display.FrameView.as_view(), name="display-frame"),
    path("displays/event/", views_display.EventView.as_view(), name="display-event"),
    path(
        "desks/manage/displays/", views_display_admin.DisplayListView.as_view(),
        name="desk-display-list",
    ),
    path(
        "desks/manage/displays/resources/",
        views_display_admin.DisplayResourceSearchView.as_view(),
        name="desk-display-resources",
    ),
    path(
        "desks/manage/displays/claim/", views_display_admin.DisplayClaimView.as_view(),
        name="desk-display-claim",
    ),
    path(
        "desks/manage/displays/<int:pk>/", views_display_admin.DisplayDetailView.as_view(),
        name="desk-display-detail",
    ),
    path(
        "desks/manage/displays/<int:pk>/preview.png",
        views_display_admin.DisplayPreviewView.as_view(), name="desk-display-preview",
    ),
    path(
        "desks/manage/rooms/<int:pk>/door-preview.png",
        views_display_admin.RoomDoorPreviewView.as_view(), name="desk-room-door-preview",
    ),
    path("desks/manage/rooms/batch/", views_admin.RoomBatchView.as_view(), name="desk-room-batch"),
    path("desks/manage/places/batch/", views_admin.PlaceBatchView.as_view(), name="desk-place-batch"),
    path(
        "desks/manage/places/name-suggestions/",
        views_admin.PlaceNameSuggestionsView.as_view(),
        name="desk-place-name-suggestions",
    ),
    path("desks/manage/assign/", views_admin.AssignView.as_view(), name="desk-assign"),
    path(
        "desks/manage/place-groups/",
        views_admin.PlaceGroupsView.as_view(),
        name="desk-place-groups",
    ),
    path(
        "desks/manage/admin-setting/",
        views_admin.AdminSettingView.as_view(),
        name="desk-admin-setting",
    ),
    path(
        "desks/manage/settings/<int:pool_id>/",
        views.DeskSettingsView.as_view(),
        name="desk-settings",
    ),
    path(
        "desks/manage/reservations/",
        views.ManageReservationsView.as_view(),
        name="desk-manage-reservations",
    ),
    path("desks/manage/people/", views.PeopleSearchView.as_view(), name="desk-people"),
    path(
        "desks/manage/access-groups/",
        views.ManageAccessGroupsView.as_view(),
        name="desk-manage-access-groups",
    ),
    path("desks/manage/stats/", views.StatsView.as_view(), name="desk-stats"),
    path("desks/manage/stats.csv", views.StatsCsvView.as_view(), name="desk-stats-csv"),
    path("desks/absences/", views.AbsencesView.as_view(), name="desk-absences"),
    path("desks/absences/<int:pk>/", views.AbsencesView.as_view(), name="desk-absence"),
    path(
        "desks/manage/absences/",
        views.ManageAbsencesView.as_view(),
        name="desk-manage-absences",
    ),
    path(
        "desks/manage/absences/<int:pk>/",
        views.ManageAbsencesView.as_view(),
        name="desk-manage-absence",
    ),
    path("desks/requests/mine/", views.MyRequestsView.as_view(), name="desk-requests-mine"),
    path("desks/scan/", views.ScanView.as_view(), name="desk-scan"),
    path(
        "desks/places/<int:pk>/check-in/",
        views.PlaceCheckInView.as_view(),
        name="desk-place-checkin",
    ),
    path("desks/free-now/", views.FreeNowView.as_view(), name="desk-free-now"),
    path("desks/window/", views.WindowView.as_view(), name="desk-window"),
    path("desks/availability/", views.AvailabilityView.as_view(), name="desk-availability"),
    path("desks/places/<int:pk>/days/", views.PlaceDaysView.as_view(), name="desk-place-days"),
    path("desks/features/", views.PoolFeaturesView.as_view(), name="desk-pool-features"),
    path("desks/floors/", views.PoolFloorsView.as_view(), name="desk-pool-floors"),
    path("desks/hours/", views.HoursView.as_view(), name="desk-hours"),
    path("desks/closed-days/", views.ClosedDaysView.as_view(), name="desk-closed-days"),
    path("desks/overview/", views.OverviewView.as_view(), name="desk-overview"),
    path("desks/room-popularity/", views.RoomPopularityView.as_view(), name="desk-room-popularity"),
    path(
        "desks/notification-preferences/",
        views.NotificationPreferencesView.as_view(),
        name="desk-notification-preferences",
    ),
    path("desks/actions/context/", views.ActionContextView.as_view(), name="desk-actions-context"),
    path("desks/actions/", views.ActionView.as_view(), name="desk-actions"),
    path("desks/profile/", views.ProfileView.as_view(), name="desk-profile"),
    path("desks/favorites/", views.FavoritesView.as_view(), name="desk-favorites"),
    path("desks/favorites/<int:place_id>/", views.FavoritesView.as_view(), name="desk-favorite"),
    *router.urls,
]
