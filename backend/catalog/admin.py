# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Admin registrations for catalog models."""
from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from .models import (
    Category,
    Favorite,
    NotificationSetting,
    Page,
    Product,
    ProductImage,
    ProductSet,
    ProductType,
    Resource,
    ResourceDefect,
    ResourcePool,
    Section,
    ShopSetting,
    TrashSetting,
    WelcomeSetting,
)

admin.site.register(WelcomeSetting)
admin.site.register(ShopSetting)
admin.site.register(TrashSetting)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__username", "product__title")


@admin.register(NotificationSetting)
class NotificationSettingAdmin(TranslationAdmin):
    pass


@admin.register(Page)
class PageAdmin(TranslationAdmin):
    list_display = ("title", "slug", "is_published", "show_in_footer", "footer_order")
    list_filter = ("is_published", "show_in_footer")
    search_fields = ("title", "slug", "body")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ProductType)
class ProductTypeAdmin(TranslationAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(TranslationAdmin):
    list_display = (
        "title", "product_type", "lending_type", "min_duration", "max_duration",
        "min_gap", "missing_notice_lead",
    )
    list_filter = ("lending_type", "product_type")
    search_fields = ("title",)
    inlines = [ProductImageInline]
    # Complementary devices (#23): a plain M2M widget would list every product;
    # `complementary_order` is curated via the Verleihtheke form, not here.
    filter_horizontal = ("complementary_products",)
    readonly_fields = ("complementary_order",)


@admin.register(ResourcePool)
class ResourcePoolAdmin(TranslationAdmin):
    list_display = ("name", "pool_id", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "pool_id")
    # Keep the defect-ticket token out of the admin form — it is write-only and
    # managed by lenders in the lending area.
    exclude = ("defect_gitlab_token",)


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = (
        "inventory_number", "product", "resource_pool", "status", "qr_code_id",
        "condition_rating",
    )
    list_filter = ("status", "resource_pool")
    search_fields = ("inventory_number", "qr_code_id")


@admin.register(ResourceDefect)
class ResourceDefectAdmin(admin.ModelAdmin):
    list_display = ("resource", "note", "created_at", "resolved_at")
    list_filter = ("resolved_at",)
    search_fields = ("resource__inventory_number", "note")


@admin.register(Category)
class CategoryAdmin(TranslationAdmin):
    list_display = ("title",)
    search_fields = ("title",)
    filter_horizontal = ("products",)


@admin.register(Section)
class SectionAdmin(TranslationAdmin):
    list_display = ("title",)
    search_fields = ("title",)
    filter_horizontal = ("categories", "sets")


@admin.register(ProductSet)
class ProductSetAdmin(TranslationAdmin):
    list_display = ("name", "resource_pool")
    list_filter = ("resource_pool",)
    search_fields = ("name",)
    filter_horizontal = ("products",)
