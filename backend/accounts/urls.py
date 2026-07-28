# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""URL routes for the accounts management API."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ManageAccessGroupViewSet,
    ManageBorrowerViewSet,
    ManageStrikeViewSet,
    ManageUserViewSet,
    RetentionSettingView,
    StrikeSettingView,
)

router = DefaultRouter()
router.register("manage/users", ManageUserViewSet, basename="manage-user")
router.register(
    "manage/borrower-profiles", ManageBorrowerViewSet, basename="manage-borrower"
)
router.register(
    "manage/access-groups", ManageAccessGroupViewSet, basename="manage-access-group"
)
router.register("manage/strikes", ManageStrikeViewSet, basename="manage-strike")

urlpatterns = [
    path(
        "manage/strike-setting/",
        StrikeSettingView.as_view(),
        name="strike-setting",
    ),
    path(
        "manage/retention-setting/",
        RetentionSettingView.as_view(),
        name="retention-setting",
    ),
] + router.urls
