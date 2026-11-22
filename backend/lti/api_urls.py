# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Management API routes of the LTI app (mounted under ``api/``)."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from . import api

router = SimpleRouter()
router.register("manage/lti/platforms", api.LtiPlatformViewSet, basename="lti-platform")

urlpatterns = [
    path("manage/lti-setting/", api.LtiSettingView.as_view(), name="lti-setting"),
    path("manage/lti/tool/", api.LtiToolInfoView.as_view(), name="lti-tool-info"),
    path(
        "manage/pools/<int:pool_id>/courses/",
        api.PoolCoursesView.as_view(),
        name="pool-courses",
    ),
    path(
        "manage/pools/<int:pool_id>/courses/<int:link_id>/",
        api.PoolCourseDetailView.as_view(),
        name="pool-course-detail",
    ),
    *router.urls,
]
