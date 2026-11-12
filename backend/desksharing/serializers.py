# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from numbers import Real

from rest_framework import serializers

from . import rights
from .models import DeskSettings, Feature, Floor, Place, Room

SHAPE_TYPES = {"room", "wall", "door", "label"}


def _is_num(v) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool)


def validate_plan(plan, room_ids=None) -> dict:
    """Plan JSON: ``{"shapes": [{id, type, points, text, room_id}]}``."""
    if not isinstance(plan, dict) or not isinstance(plan.get("shapes"), list):
        raise serializers.ValidationError('Plan must be {"shapes": [...]}.')
    for shape in plan["shapes"]:
        if not isinstance(shape, dict):
            raise serializers.ValidationError("Every shape must be an object.")
        if not isinstance(shape.get("id"), str) or not shape["id"]:
            raise serializers.ValidationError("Shape id must be a string.")
        if shape.get("type") not in SHAPE_TYPES:
            raise serializers.ValidationError(f"Unknown shape type: {shape.get('type')!r}.")
        points = shape.get("points")
        if points is not None:
            if not isinstance(points, list) or not all(
                isinstance(p, (list, tuple)) and len(p) == 2 and all(_is_num(c) for c in p)
                for p in points
            ):
                raise serializers.ValidationError("Shape points must be [[x, y], ...].")
        text = shape.get("text")
        if text is not None and not isinstance(text, str):
            raise serializers.ValidationError("Shape text must be a string.")
        room_id = shape.get("room_id")
        if room_id is not None:
            if not isinstance(room_id, int) or isinstance(room_id, bool):
                raise serializers.ValidationError("Shape room_id must be an integer.")
            if room_ids is not None and room_id not in room_ids:
                raise serializers.ValidationError("Shape room_id is not a room of this floor.")
    return plan


def validate_business_hours(value) -> dict:
    if not isinstance(value, dict) or set(value) != {str(d) for d in range(7)}:
        raise serializers.ValidationError('Business hours need the keys "0" to "6".')
    for hours in value.values():
        if hours is None:
            continue
        if (
            not isinstance(hours, (list, tuple))
            or len(hours) != 2
            or not all(isinstance(h, int) and not isinstance(h, bool) for h in hours)
            or not (6 <= hours[0] < hours[1] <= 20)
        ):
            raise serializers.ValidationError(
                "Hours must be null or [start, end] with 6 <= start < end <= 20."
            )
    return value


class AdminPoolMixin:
    """Writes are limited to the requesting user's admin pools."""

    def _check_pool(self, pool_id):
        user = self.context["request"].user
        if pool_id not in rights.admin_pool_ids(user):
            raise serializers.ValidationError("You do not administer this department.")


class FeatureSerializer(AdminPoolMixin, serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["id", "pool", "name"]

    def validate_pool(self, pool):
        self._check_pool(pool.pk)
        return pool


class FloorSerializer(AdminPoolMixin, serializers.ModelSerializer):
    has_template = serializers.SerializerMethodField()
    template_url = serializers.SerializerMethodField()

    class Meta:
        model = Floor
        fields = [
            "id", "pool", "building", "name", "position",
            "has_template", "template_url", "scale_px_per_m", "plan",
        ]
        read_only_fields = ["plan"]

    def validate_pool(self, pool):
        self._check_pool(pool.pk)
        return pool

    def get_has_template(self, floor) -> bool:
        return bool(floor.template_content_type)

    def get_template_url(self, floor):
        if not floor.template_content_type:
            return None
        return f"/api/desks/manage/floors/{floor.pk}/template/"


class FloorPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = ["plan"]

    def validate_plan(self, plan):
        room_ids = set(self.instance.rooms.values_list("pk", flat=True))
        return validate_plan(plan, room_ids)


class RoomSerializer(AdminPoolMixin, serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "floor", "name", "kind"]

    def validate_floor(self, floor):
        self._check_pool(floor.pool_id)
        return floor


class PlaceSerializer(AdminPoolMixin, serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "id", "room", "kind", "name", "capacity", "features", "access_groups",
            "is_special", "fixed_owner", "plan_symbol", "qr_token", "is_active",
        ]
        read_only_fields = ["qr_token"]

    def validate_room(self, room):
        self._check_pool(room.floor.pool_id)
        return room

    def validate_plan_symbol(self, value):
        if value is None:
            return value
        ok = isinstance(value, dict) and all(
            _is_num(value.get(k)) for k in ("x", "y", "rotation")
        )
        if not ok:
            raise serializers.ValidationError('Symbol must be {"x", "y", "rotation"}.')
        return {k: value[k] for k in ("x", "y", "rotation")}

    def validate(self, attrs):
        inst = self.instance
        kind = attrs.get("kind", inst.kind if inst else Place.Kind.DESK)
        capacity = attrs.get("capacity", inst.capacity if inst else None)
        if kind == Place.Kind.MEETING_ROOM and not capacity:
            raise serializers.ValidationError(
                {"capacity": "A meeting room needs a capacity."}
            )
        room = attrs.get("room") or (inst.room if inst else None)
        features = attrs.get("features")
        if room is not None and features:
            if any(f.pool_id != room.floor.pool_id for f in features):
                raise serializers.ValidationError(
                    {"features": "Features must belong to the place's department."}
                )
        return attrs


class DeskSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeskSettings
        fields = [
            "pool", "enabled", "assistant_group", "business_hours",
            "desk_grace_normal_min", "desk_grace_short_min", "desk_scarcity_free_below",
            "room_grace_normal_min", "room_grace_short_min", "room_scarcity_free_below",
            "retention_days",
        ]
        read_only_fields = ["pool"]

    def validate_business_hours(self, value):
        return validate_business_hours(value)

    def validate(self, attrs):
        enabled = attrs.get("enabled", self.instance.enabled)
        if enabled and not self.instance.pool.access_groups.exists():
            raise serializers.ValidationError(
                {"enabled": "Desksharing needs at least one access group on the pool."}
            )
        return attrs
