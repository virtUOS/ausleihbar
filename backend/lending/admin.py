# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Admin registrations for lending models."""
from django.contrib import admin

from .models import Block, Booking, BookingItem, BookingReminder, CartSetting


class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0


class BookingReminderInline(admin.TabularInline):
    model = BookingReminder
    extra = 0
    readonly_fields = ("recipient", "overdue_pickups", "overdue_returns", "created_at")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id", "code", "borrower", "status", "resource_pool", "checkout_id",
        "expires_at", "created_at",
    )
    list_filter = ("status", "resource_pool")
    search_fields = ("code", "checkout_id", "borrower__username")
    readonly_fields = ("resource_pool", "checkout_id")
    inlines = [BookingItemInline, BookingReminderInline]


@admin.register(BookingReminder)
class BookingReminderAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "recipient", "overdue_pickups", "overdue_returns", "created_at")
    search_fields = ("booking__code", "recipient")


@admin.register(BookingItem)
class BookingItemAdmin(admin.ModelAdmin):
    list_display = ("id", "resource", "period", "is_active")
    list_filter = ("is_active",)


@admin.register(CartSetting)
class CartSettingAdmin(admin.ModelAdmin):
    list_display = ("hold_minutes",)


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("id", "scope", "period", "reason", "resource_pool", "product", "resource")
    list_filter = ("resource_pool", "product")
    search_fields = ("reason",)
    autocomplete_fields = ("resource_pool", "product", "resource")
