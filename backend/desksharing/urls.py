# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
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
    path("desks/free/", views.FreePlacesView.as_view(), name="desk-free"),
    path("desks/free-now/", views.FreeNowView.as_view(), name="desk-free-now"),
    path("desks/features/", views.PoolFeaturesView.as_view(), name="desk-pool-features"),
    path("desks/hours/", views.HoursView.as_view(), name="desk-hours"),
    path("desks/overview/", views.OverviewView.as_view(), name="desk-overview"),
    path(
        "desks/notification-preferences/",
        views.NotificationPreferencesView.as_view(),
        name="desk-notification-preferences",
    ),
    path("desks/actions/", views.ActionView.as_view(), name="desk-actions"),
    path("desks/profile/", views.ProfileView.as_view(), name="desk-profile"),
    *router.urls,
]
