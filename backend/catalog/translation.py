# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Translatable catalog fields (django-modeltranslation, issue #6).

Registering a model here makes django-modeltranslation add per-language columns
(e.g. ``title_de`` / ``title_en``) and turn the plain attribute (``obj.title``)
into a language-aware accessor based on the active request language. Only
free-text fields shown to borrowers are translated; identifiers, numbers and
structural fields stay single-valued.

Note: dynamic labels inside ``ProductType.attribute_schema`` (e.g. "Hersteller")
live in a JSON field and cannot be handled here — they get their own per-key
translation handling in a later phase.
"""

from modeltranslation.translator import TranslationOptions, register

from .models import (
    Category,
    NotificationSetting,
    Page,
    Product,
    ProductSet,
    ProductType,
    ResourcePool,
    Section,
)


@register(ProductType)
class ProductTypeTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ("title", "description", "short_description", "return_info")


@register(ResourcePool)
class ResourcePoolTranslationOptions(TranslationOptions):
    fields = ("name", "description", "address", "room", "directions", "email_note")


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ("title", "description")


@register(Section)
class SectionTranslationOptions(TranslationOptions):
    fields = ("title", "description")


@register(ProductSet)
class ProductSetTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(Page)
class PageTranslationOptions(TranslationOptions):
    fields = ("title", "body")


@register(NotificationSetting)
class NotificationSettingTranslationOptions(TranslationOptions):
    fields = (
        "reservation_intro",
        "reservation_footer",
        "rescheduled_note",
        "cancellation_note",
        "reminder_note",
        "defect_note",
    )
