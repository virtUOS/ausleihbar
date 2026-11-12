# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from modeltranslation.translator import TranslationOptions, register

from .models import Feature, Floor, Place, Room


@register(Feature)
class FeatureTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Floor)
class FloorTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Room)
class RoomTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Place)
class PlaceTranslationOptions(TranslationOptions):
    fields = ("name",)
