# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.urls import path

from . import views

urlpatterns = [
    path("lti/launch/", views.lti_launch, name="lti-launch"),
    path("lti/course/", views.course_page, name="lti-course"),
    path("lti/course/link/", views.course_link, name="lti-course-link"),
    path("lti/course/pool/", views.course_create_pool, name="lti-course-pool"),
]
