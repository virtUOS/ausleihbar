# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Admin registrations for LTI course pools (platforms, tool key and user
links are registered by basicbar-lti)."""
from django.contrib import admin

from .models import LtiCourseLink, LtiSetting


@admin.register(LtiCourseLink)
class LtiCourseLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "context_id", "platform", "pool", "is_active", "created_at")
    list_filter = ("is_active", "platform")
    search_fields = ("title", "context_id", "pool__name")
    raw_id_fields = ("pool", "created_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LtiSetting)
class LtiSettingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "instructors_create_pools")

    def has_add_permission(self, request):
        return not LtiSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
