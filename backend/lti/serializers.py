# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Management API shapes of the LTI course pools."""
from rest_framework import serializers

from .models import LtiCourseLink, LtiSetting


def _person(user):
    if user is None:
        return None
    return {"id": user.pk, "name": user.get_full_name() or user.get_username()}


class LtiSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LtiSetting
        fields = ["instructors_create_pools"]


class PoolCourseSerializer(serializers.ModelSerializer):
    """A course linked to a pool, for the pool's "Kurse" list. Only
    ``is_active`` is writable (switching off keeps the course members)."""

    platform = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    # Manual members of the link's system access group (learners who
    # launched from the course); annotated by the view.
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = LtiCourseLink
        fields = [
            "id", "title", "context_id", "platform", "is_active",
            "member_count", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "title", "context_id", "created_at", "updated_at",
        ]

    def get_platform(self, obj):
        return {"id": obj.platform_id, "name": obj.platform.name}

    def get_created_by(self, obj):
        return _person(obj.created_by)


class PoolCourseUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=True)
