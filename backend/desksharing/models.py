# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing settings per department (= ``catalog.ResourcePool``)."""
import secrets
import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


def default_business_hours():
    """Mon-Fri 06-20, weekend closed (keys: weekday 0=Monday)."""
    return {str(d): ([6, 20] if d < 5 else None) for d in range(7)}


class DeskSettings(TimeStampedModel):
    pool = models.OneToOneField(
        "catalog.ResourcePool",
        on_delete=models.CASCADE,
        related_name="desk_settings",
    )
    enabled = models.BooleanField(default=False)
    assistant_group = models.ForeignKey(
        "accounts.AccessGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # {"0": [start_hour, end_hour], ..., "6": null}: weekday -> hours or closed.
    business_hours = models.JSONField(default=default_business_hours, blank=True)
    desk_grace_normal_min = models.PositiveIntegerField(default=60)
    desk_grace_short_min = models.PositiveIntegerField(default=15)
    desk_scarcity_free_below = models.PositiveIntegerField(default=2)
    room_grace_normal_min = models.PositiveIntegerField(default=60)
    room_grace_short_min = models.PositiveIntegerField(default=15)
    room_scarcity_free_below = models.PositiveIntegerField(default=2)
    retention_days = models.PositiveIntegerField(default=90)

    class Meta:
        verbose_name = "desksharing settings"
        verbose_name_plural = "desksharing settings"

    def __str__(self):
        return f"Desksharing: {self.pool}"

    @classmethod
    def for_pool(cls, pool) -> "DeskSettings":
        return cls.objects.get_or_create(pool=pool)[0]

    def clean(self):
        super().clean()
        # Desksharing needs a closed circle of users: no university-wide list.
        if self.enabled and self.pool_id and not self.pool.access_groups.exists():
            raise ValidationError(
                {"enabled": "Desksharing needs at least one access group on the pool."}
            )


def new_qr_token() -> str:
    return secrets.token_urlsafe(16)


class Feature(TimeStampedModel):
    """Equipment of a place (e.g. "Docking station"), maintained per pool."""

    pool = models.ForeignKey(
        "catalog.ResourcePool", on_delete=models.CASCADE, related_name="desk_features"
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Floor(TimeStampedModel):
    pool = models.ForeignKey(
        "catalog.ResourcePool", on_delete=models.CASCADE, related_name="desk_floors"
    )
    building = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)
    # Admin-only drawing template. Kept in the database (re-encoded image),
    # not under MEDIA_ROOT, which is served unauthenticated; it is streamed
    # only by an admin-gated view.
    template_data = models.BinaryField(null=True, blank=True, editable=False)
    template_content_type = models.CharField(max_length=50, blank=True, editable=False)
    scale_px_per_m = models.FloatField(null=True, blank=True)
    plan = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["building", "position", "name"]

    def __str__(self):
        return f"{self.building} {self.name}".strip()

    def save(self, *args, **kwargs):
        if not self.plan:
            self.plan = {"shapes": []}
        super().save(*args, **kwargs)


class Room(TimeStampedModel):
    class Kind(models.TextChoices):
        OFFICE = "office", "Office"
        MEETING = "meeting", "Meeting"

    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OFFICE)

    class Meta:
        ordering = ["floor_id", "name"]

    def __str__(self):
        return f"{self.floor} / {self.name}"


class Place(TimeStampedModel):
    class Kind(models.TextChoices):
        DESK = "desk", "Desk"
        MEETING_ROOM = "meeting_room", "Meeting room"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="places")
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.DESK)
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    features = models.ManyToManyField(Feature, blank=True, related_name="places")
    access_groups = models.ManyToManyField(
        "accounts.AccessGroup", blank=True, related_name="desk_places"
    )
    is_special = models.BooleanField(default=False)
    fixed_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # {"x": float, "y": float, "rotation": float} in plan coordinates.
    plan_symbol = models.JSONField(null=True, blank=True)
    qr_token = models.CharField(max_length=32, unique=True, default=new_qr_token)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["room_id", "name"]

    def __str__(self):
        return self.name

    @property
    def pool(self):
        return self.room.floor.pool

    def has_reservations(self) -> bool:
        """Reservations arrive with the booking models (Task 3)."""
        rel = getattr(self, "reservations", None)
        return bool(rel is not None and rel.exists())


class Reservation(models.Model):
    """One place for whole local hours of one day (``period`` is [start, end))."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        RELEASED = "released", "Released"

    class ReleaseReason(models.TextChoices):
        NONE = "", "-"
        NO_SHOW = "no_show", "No-show"
        ABSENCE = "absence", "Absence"
        HOLDER = "holder", "Holder"
        ADMIN = "admin", "Admin"
        REQUEST = "request", "Request"
        BLOCK = "block", "Block"
        RIGHTS = "rights", "Rights"

    # PROTECT: places with reservations are soft-deleted (history for stats).
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="reservations")
    # Null after anonymization.
    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="desk_reservations",
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # Places booked together in one action.
    group = models.UUIDField(default=uuid.uuid4, db_index=True)
    period = DateTimeRangeField()
    comment = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    late_until = models.DateTimeField(null=True, blank=True)
    potentially_free_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(
        max_length=10, choices=ReleaseReason.choices, default="", blank=True
    )
    no_show = models.BooleanField(default=False)
    # Snapshot of the holder's opt-out at booking time.
    holder_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["period", "place_id"]
        constraints = [
            ExclusionConstraint(
                name="desk_no_overlapping_active_reservations",
                expressions=[
                    ("place", RangeOperators.EQUAL),
                    ("period", RangeOperators.OVERLAPS),
                ],
                condition=Q(status="active"),
            )
        ]

    def __str__(self):
        return f"{self.place} {self.period}"
