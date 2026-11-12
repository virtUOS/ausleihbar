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

urlpatterns = [
    path(
        "desks/manage/settings/<int:pool_id>/",
        views.DeskSettingsView.as_view(),
        name="desk-settings",
    ),
    *router.urls,
]
