# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib import admin

from .models import DeskSettings


@admin.register(DeskSettings)
class DeskSettingsAdmin(admin.ModelAdmin):
    list_display = ("pool", "enabled", "assistant_group")
    list_filter = ("enabled",)
