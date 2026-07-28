# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Serializers for bookings (ADR-0006)."""
from datetime import datetime, time, timedelta

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone
from rest_framework import serializers

from catalog.models import ResourcePool
from catalog.serializers import _cover_url

from .models import (
    Block,
    Booking,
    BookingItem,
    BookingReminder,
    CartSetting,
    HolidaySetting,
)


class BookingItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(
        source="resource.product", read_only=True
    )
    product_title = serializers.CharField(source="resource.product.title", read_only=True)
    inventory_number = serializers.CharField(source="resource.inventory_number", read_only=True)
    qr_code_id = serializers.CharField(source="resource.qr_code_id", read_only=True)
    pool = serializers.CharField(source="resource.resource_pool.name", read_only=True)
    pool_id = serializers.PrimaryKeyRelatedField(
        source="resource.resource_pool", read_only=True
    )
    image = serializers.SerializerMethodField()
    resource = serializers.PrimaryKeyRelatedField(read_only=True)
    resource_status = serializers.CharField(source="resource.status", read_only=True)
    defect_note = serializers.CharField(source="resource.defect_note", read_only=True)
    # Lets the client format the period correctly: a day booking shows an
    # inclusive date range (the stored upper bound is the exclusive next day),
    # an hourly booking shows real times.
    lending_type = serializers.CharField(
        source="resource.product.lending_type", read_only=True
    )
    start = serializers.SerializerMethodField()
    end = serializers.SerializerMethodField()

    class Meta:
        model = BookingItem
        fields = [
            "id", "product", "product_title", "inventory_number", "qr_code_id",
            "pool", "pool_id", "image", "resource", "resource_status",
            "defect_note", "lending_type",
            "start", "end", "handed_out_at", "returned_at",
        ]

    def get_image(self, obj):
        return _cover_url(obj.resource.product, self.context.get("request"))

    def get_start(self, obj):
        return obj.period.lower.isoformat() if obj.period and obj.period.lower else None

    def get_end(self, obj):
        return obj.period.upper.isoformat() if obj.period and obj.period.upper else None


class BookingSerializer(serializers.ModelSerializer):
    items = BookingItemSerializer(many=True, read_only=True)
    groups = serializers.SerializerMethodField()
    has_strike = serializers.SerializerMethodField()
    strike_reason = serializers.SerializerMethodField()
    note_required = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "code", "status", "note", "expires_at", "created_at",
            "items", "groups", "has_strike", "strike_reason", "note_required",
        ]

    def get_note_required(self, obj):
        """True if any pool in the (active) booking requires a borrower note."""
        return any(
            item.resource.resource_pool.require_booking_note
            for item in obj.items.all()
            if item.is_active
        )

    def _active_strike(self, obj):
        """The most recent still-active strike tied to this booking, if any."""
        return (
            obj.strikes.filter(expires_at__gt=timezone.now())
            .order_by("-created_at")
            .first()
        )

    def get_has_strike(self, obj):
        return self._active_strike(obj) is not None

    def get_strike_reason(self, obj):
        strike = self._active_strike(obj)
        return strike.reason if strike else None

    def get_groups(self, obj):
        """Items grouped by pool, then by reservation period, for summaries."""
        request = self.context.get("request")
        pools = {}
        order = []
        for item in obj.items.all():
            pool = item.resource.resource_pool
            period = item.period
            start = period.lower.isoformat() if period and period.lower else None
            end = period.upper.isoformat() if period and period.upper else None
            if pool.id not in pools:
                pools[pool.id] = {
                    "pool_id": pool.id,
                    "pool": pool.name,
                    "room": pool.room,
                    "periods": {},
                    "period_order": [],
                }
                order.append(pool.id)
            group = pools[pool.id]
            key = (start, end)
            if key not in group["periods"]:
                group["periods"][key] = {
                    "start": start,
                    "end": end,
                    "lending_type": item.resource.product.lending_type,
                    "items": [],
                }
                group["period_order"].append(key)
            group["periods"][key]["items"].append(
                {
                    "id": item.id,
                    "product": item.resource.product_id,
                    "product_title": item.resource.product.title,
                    "inventory_number": item.resource.inventory_number,
                    "image": _cover_url(item.resource.product, request),
                }
            )
        return [
            {
                "pool_id": pools[pid]["pool_id"],
                "pool": pools[pid]["pool"],
                "room": pools[pid]["room"],
                "periods": [pools[pid]["periods"][k] for k in pools[pid]["period_order"]],
            }
            for pid in order
        ]


class BookingReminderSerializer(serializers.ModelSerializer):
    sent_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = BookingReminder
        fields = ["id", "sent_at", "overdue_pickups", "overdue_returns"]


class ManageBookingItemSerializer(BookingItemSerializer):
    """Item view for lenders — adds the lender-only return information."""

    return_info = serializers.CharField(
        source="resource.product.return_info", read_only=True
    )

    class Meta(BookingItemSerializer.Meta):
        fields = BookingItemSerializer.Meta.fields + ["return_info"]


class ManageBookingSerializer(BookingSerializer):
    """Booking view for lenders/admins — also exposes the borrower and reminders."""

    items = ManageBookingItemSerializer(many=True, read_only=True)
    borrower = serializers.CharField(source="borrower.username", read_only=True)
    borrower_id = serializers.IntegerField(source="borrower.id", read_only=True)
    borrower_name = serializers.SerializerMethodField()
    reminders = BookingReminderSerializer(many=True, read_only=True)

    class Meta(BookingSerializer.Meta):
        fields = BookingSerializer.Meta.fields + [
            "borrower", "borrower_id", "borrower_name", "reminders",
        ]

    def get_borrower_name(self, obj):
        """Human-readable name for the lending desk; falls back to the username."""
        return obj.borrower.get_full_name() or obj.borrower.username


class BlockSerializer(serializers.ModelSerializer):
    """A block day (Sperrtag) for the management overview."""

    pool_name = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    is_holiday = serializers.SerializerMethodField()

    class Meta:
        model = Block
        fields = [
            "id", "scope", "reason", "resource_pool", "pool_name",
            "start_date", "end_date", "is_holiday", "created_at",
        ]

    def get_pool_name(self, obj):
        return obj.resource_pool.name if obj.resource_pool_id else None

    def get_start_date(self, obj):
        lower = obj.period.lower
        return lower.date().isoformat() if lower else None

    def get_end_date(self, obj):
        # Stored upper bound is exclusive; show the inclusive last blocked day.
        upper = obj.period.upper
        if not upper:
            return None
        return (upper - timedelta(microseconds=1)).date().isoformat()

    def get_is_holiday(self, obj):
        return obj.reason.startswith("Holiday:")


class BlockCreateSerializer(serializers.Serializer):
    """Create a (possibly multi-day) block day, system-wide or pool-scoped."""

    resource_pool = serializers.PrimaryKeyRelatedField(
        queryset=ResourcePool.objects.all(),
        required=False,
        allow_null=True,
    )
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        end = attrs.get("end_date") or attrs["start_date"]
        if end < attrs["start_date"]:
            raise serializers.ValidationError("'end_date' must not be before 'start_date'.")
        attrs["end_date"] = end
        return attrs

    def create(self, validated_data):
        start = timezone.make_aware(
            datetime.combine(validated_data["start_date"], time.min)
        )
        end = timezone.make_aware(
            datetime.combine(validated_data["end_date"] + timedelta(days=1), time.min)
        )
        return Block.objects.create(
            period=DateTimeTZRange(start, end),
            reason=validated_data.get("reason", ""),
            resource_pool=validated_data.get("resource_pool"),
        )


class HolidaySettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = HolidaySetting
        fields = ["country", "subdivision"]


class CartSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartSetting
        fields = ["hold_minutes"]

    def validate_hold_minutes(self, value):
        if value < 1:
            raise serializers.ValidationError("Must be at least 1 minute.")
        if value > 7 * 24 * 60:
            raise serializers.ValidationError("Must be at most 7 days.")
        return value
