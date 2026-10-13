# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Serializers for the admin user-management API."""
from rest_framework import serializers

from catalog.models import ResourcePool

from . import roles
from .models import (
    AccessGroup,
    RetentionSetting,
    Strike,
    StrikeSetting,
    User,
)


class StrikeSerializer(serializers.ModelSerializer):
    """A strike on a user's account."""

    issued_by = serializers.CharField(
        source="issued_by.username", read_only=True, default=None
    )
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Strike
        fields = ["id", "reason", "issued_by", "created_at", "expires_at", "is_active"]


class BorrowerProfileSerializer(serializers.ModelSerializer):
    """Read-only borrower profile for the lending desk (lenders + admins).

    Exposes the person's identity, suspension status and strikes so a lender can
    look up who they're lending to — but none of the admin-only role/pool
    controls. Strikes are read-only here; issuing one goes through the strike
    endpoint, deleting/unblocking stays admin-only.
    """

    full_name = serializers.SerializerMethodField()
    strikes = StrikeSerializer(many=True, read_only=True)
    active_strikes = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "full_name", "strikes", "active_strikes",
            "is_blocked", "blocked_until", "blocked_permanently", "date_joined",
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_active_strikes(self, obj):
        return sum(1 for s in obj.strikes.all() if s.is_active)

    def get_is_blocked(self, obj):
        return obj.is_blocked()


def _pool_names(pool_ids):
    """``{id: name}`` (in the active language) incl. trashed pools."""
    if not pool_ids:
        return {}
    return {p.pk: p.name for p in ResourcePool.all_objects.filter(pk__in=pool_ids)}


class UserManageListSerializer(serializers.ListSerializer):
    """Computes the users' roles for a whole page at once (a few queries
    instead of several per user) and hands them to the item serializer."""

    def to_representation(self, data):
        users = list(data.all() if hasattr(data, "all") else data)
        self.child.context["managed_pool_ids_by_user"] = (
            roles.managed_pool_ids_by_user(users)
        )
        self.child.context["admin_user_ids"] = roles.admin_user_ids()
        pool_ids = set().union(*self.child.context["managed_pool_ids_by_user"].values())
        self.child.context["pool_names"] = _pool_names(pool_ids)
        return super().to_representation(users)


class UserGroupBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessGroup
        fields = ["id", "name"]


class UserManageSerializer(serializers.ModelSerializer):
    """Read representation of a user with derived roles for the admin UI."""

    full_name = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()
    admin_via_oidc = serializers.SerializerMethodField()
    is_lender = serializers.SerializerMethodField()
    managed_pools = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    strikes = StrikeSerializer(many=True, read_only=True)
    active_strikes = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "full_name", "is_admin", "admin_via_oidc",
            "is_lender", "is_active", "managed_pools", "groups", "strikes",
            "active_strikes", "is_blocked", "blocked_until", "blocked_permanently",
            "verified_at", "date_joined", "last_login",
        ]
        list_serializer_class = UserManageListSerializer

    def _managed_pool_ids(self, obj):
        by_user = self.context.get("managed_pool_ids_by_user")
        if by_user is not None and obj.pk in by_user:
            return by_user[obj.pk]
        return roles.managed_pool_ids(obj)

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_groups(self, obj):
        # Pools' system lender groups show up as ``managed_pools`` instead
        # (``access_groups`` is prefetched; filter in Python).
        groups = [g for g in obj.access_groups.all() if g.system_pool_id is None]
        return UserGroupBriefSerializer(groups, many=True).data

    def get_is_admin(self, obj):
        admin_ids = self.context.get("admin_user_ids")
        if admin_ids is not None:
            return obj.pk in admin_ids
        return roles.is_app_admin(obj)

    def get_managed_pools(self, obj):
        # Shape kept from the PoolMembership era ("id" is now the pool id);
        # Task 3 of #80 replaces it with the per-group "via" shape.
        ids = sorted(self._managed_pool_ids(obj))
        names = self.context.get("pool_names")
        if names is None or not set(ids) <= names.keys():
            # Trashed pools count too, as their memberships did.
            names = _pool_names(ids)
        return [
            {"id": pk, "resource_pool": pk, "pool_name": names.get(pk), "role": "manager"}
            for pk in ids
        ]

    def get_admin_via_oidc(self, obj):
        # Admin rights granted by the IdP group can't be edited here.
        from basicbar_auth.oidc import is_oidc_admin

        return is_oidc_admin(obj)

    def get_is_lender(self, obj):
        return bool(self._managed_pool_ids(obj))

    def get_active_strikes(self, obj):
        return sum(1 for s in obj.strikes.all() if s.is_active)

    def get_is_blocked(self, obj):
        return obj.is_blocked()


class UserRoleUpdateSerializer(serializers.Serializer):
    """Writable role flags. ``is_admin`` maps to is_staff + is_superuser."""

    is_admin = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class UserPoolsUpdateSerializer(serializers.Serializer):
    """The full set of pools whose system lender group the user should be a
    manual member of."""

    pool_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True
    )


class UserGroupsUpdateSerializer(serializers.Serializer):
    """The full set of access groups a user should be a (manual) member of."""

    group_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True
    )


class AccessGroupSerializer(serializers.ModelSerializer):
    """Admin CRUD for access groups (the pool eligibility rules)."""

    pool_names = serializers.SerializerMethodField()
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = AccessGroup
        fields = [
            "id", "name", "description", "claim_key", "claim_values",
            "pools", "pool_names", "member_count",
        ]

    def get_pool_names(self, obj):
        return [p.name for p in obj.pools.all()]

    def validate_pools(self, value):
        # PrimaryKeyRelatedField already validates existence; keep order stable.
        return value


class RetentionSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetentionSetting
        fields = ["enabled", "retention_days"]

    def validate_retention_days(self, value):
        if value < 30:
            raise serializers.ValidationError(
                "The retention window must be at least 30 days."
            )
        return value


class StrikeSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = StrikeSetting
        fields = ["strike_expiry_days", "thresholds"]

    def validate_thresholds(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list of steps.")
        cleaned = []
        for step in value:
            try:
                count = int(step["count"])
                block_days = int(step.get("block_days", 0) or 0)
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError(
                    "Each step needs an integer 'count' and 'block_days'."
                )
            if count < 1:
                raise serializers.ValidationError("'count' must be at least 1.")
            cleaned.append({"count": count, "block_days": block_days})
        return sorted(cleaned, key=lambda s: s["count"])
