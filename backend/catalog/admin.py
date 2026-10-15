# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Admin registrations for catalog models."""
from django.contrib import admin
from django.utils.html import format_html
from modeltranslation.admin import TranslationAdmin

from .models import (
    Category,
    Favorite,
    NotificationSetting,
    Page,
    Product,
    ProductImage,
    ProductSet,
    ProductSetImage,
    ProductSetItem,
    ProductType,
    Resource,
    ResourceDefect,
    ResourcePool,
    Section,
    ShopSetting,
    TrashSetting,
    WelcomeSetting,
)

class ReadOnlyImageMixin:
    """Shows the ``image`` field read-only (#119): uploads must go through the
    app, which validates and re-encodes them (``catalog.images``) — a raw
    admin upload would bypass that. Use with ``exclude``/``fields`` that leave
    out ``image`` and ``current_image`` in ``readonly_fields``."""

    @admin.display(description="image")
    def current_image(self, obj):
        note = "Images are uploaded and changed in the Ausleihbar app, not here."
        if obj is not None and obj.image:
            return format_html(
                '<a href="{}">{}</a><div class="help">{}</div>',
                obj.image.url, obj.image.name, note,
            )
        return format_html('–<div class="help">{}</div>', note)


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


class ProductImageInline(ReadOnlyImageMixin, admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("current_image", "position")
    readonly_fields = ("current_image",)

    def has_add_permission(self, request, obj=None):
        return False  # gallery images are added in the app (#119)


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
    filter_horizontal = ("complementary_products", "categories")
    readonly_fields = ("complementary_order",)


@admin.register(ResourcePool)
class ResourcePoolAdmin(ReadOnlyImageMixin, TranslationAdmin):
    list_display = ("name", "pool_id", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "pool_id")
    # Keep the defect-ticket token out of the admin form — it is write-only and
    # managed by lenders in the lending area. The image is read-only (#119).
    exclude = ("defect_gitlab_token", "image")
    readonly_fields = ("current_image",)


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
class CategoryAdmin(ReadOnlyImageMixin, TranslationAdmin):
    list_display = ("name", "parent", "position", "image")
    list_filter = ("parent",)
    search_fields = ("name",)
    # Curated in the admin UI's Categories page, not here; the image is
    # uploaded there too (#119).
    exclude = ("image",)
    readonly_fields = ("product_order", "current_image")


@admin.register(Section)
class SectionAdmin(ReadOnlyImageMixin, TranslationAdmin):
    list_display = ("title",)
    search_fields = ("title",)
    filter_horizontal = ("categories", "sets")
    exclude = ("image",)  # uploaded in the app (#119)
    readonly_fields = ("category_order", "current_image")


class ProductSetItemInline(admin.TabularInline):
    model = ProductSetItem
    extra = 0
    fields = ("product", "quantity", "position")
    autocomplete_fields = ("product",)


class ProductSetImageInline(ReadOnlyImageMixin, admin.TabularInline):
    model = ProductSetImage
    extra = 0
    fields = ("current_image", "position")
    readonly_fields = ("current_image",)

    def has_add_permission(self, request, obj=None):
        return False  # gallery images are added in the app (#119)


@admin.register(ProductSet)
class ProductSetAdmin(TranslationAdmin):
    list_display = ("name", "resource_pool")
    list_filter = ("resource_pool",)
    search_fields = ("name",)
    inlines = [ProductSetItemInline, ProductSetImageInline]
    filter_horizontal = ("categories",)
