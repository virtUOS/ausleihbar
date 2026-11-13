# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing settings per department (= ``catalog.ResourcePool``)."""
import secrets
import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import ArrayField, DateTimeRangeField, RangeOperators
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
    scale_px_per_m = models.FloatField(null=True, blank=True)
    plan = models.JSONField(default=dict, blank=True)
    # Soft delete: false once removed while its places have reservation history.
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["building", "position", "name"]

    def __str__(self):
        return f"{self.building} {self.name}".strip()

    def save(self, *args, **kwargs):
        if not self.plan:
            self.plan = {"shapes": []}
        super().save(*args, **kwargs)


class FloorTemplate(models.Model):
    """A floor's admin-only drawing template (re-encoded image). Kept in the
    database, not under MEDIA_ROOT (served unauthenticated), and streamed
    only by an admin-gated view. A table of its own so that no query through
    a floor ever loads the blob."""

    floor = models.OneToOneField(Floor, on_delete=models.CASCADE, related_name="template")
    data = models.BinaryField()
    content_type = models.CharField(max_length=50)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Template of {self.floor}"


class Room(TimeStampedModel):
    class Kind(models.TextChoices):
        OFFICE = "office", "Office"
        MEETING = "meeting", "Meeting"

    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OFFICE)
    # Soft delete: false once removed while its places have reservation history.
    is_active = models.BooleanField(default=True)

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
        constraints = [
            # A fixed desk is never a special place: special places are shown
            # individually in the statistics, and a fixed desk's assigned hours
            # would reveal its owner's absence days.
            models.CheckConstraint(
                name="desk_fixed_place_not_special",
                condition=Q(is_special=False) | Q(fixed_owner__isnull=True),
            )
        ]

    def __str__(self):
        return self.name

    @property
    def pool(self):
        return self.room.floor.pool

    @property
    def is_bookable(self) -> bool:
        """Active, in an active room on an active floor."""
        return self.is_active and self.room.is_active and self.room.floor.is_active

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        track = not self._state.adding and self.pk and (
            update_fields is None or "fixed_owner" in update_fields
            or "fixed_owner_id" in update_fields
        )
        old_owner = (
            Place.objects.filter(pk=self.pk).values_list("fixed_owner_id", flat=True).first()
            if track else None
        )
        super().save(*args, **kwargs)
        if track and old_owner != self.fixed_owner_id:
            self.sync_owner_use()

    def sync_owner_use(self) -> None:
        """Recompute ``Reservation.owner_use`` of the reservations not yet
        ended after the fixed owner changed (ended rows keep their history).
        ``save()`` calls it; call it after a queryset ``update()`` of
        ``fixed_owner``."""
        from django.utils import timezone

        rows = Reservation.objects.filter(
            place=self, holder__isnull=False, period__endswith__gt=timezone.now()
        )
        if self.fixed_owner_id:
            rows.filter(holder_id=self.fixed_owner_id).update(owner_use=True)
            rows.exclude(holder_id=self.fixed_owner_id).update(owner_use=False)
        else:
            rows.update(owner_use=False)

    def has_reservations(self) -> bool:
        """Whether the place has any reservation (of any status) in its history."""
        return self.reservations.exists()


class Series(models.Model):
    """A weekly recurring reservation of one place. The occurrences are
    ordinary ``Reservation``s created up front for the whole validity."""

    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="desk_series",
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="series")
    # Weekdays, 0 = Monday.
    weekdays = ArrayField(models.PositiveSmallIntegerField(), size=7)
    start_hour = models.PositiveSmallIntegerField()
    end_hour = models.PositiveSmallIntegerField()
    valid_from = models.DateField()
    valid_until = models.DateField()
    comment = models.CharField(max_length=200, blank=True)
    # Set when the whole series was cancelled (the row stays for the history).
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Extension reminders already sent for the current ``valid_until``
    # (28 and 7 days before it; reset when the series is extended).
    reminder_28_sent = models.BooleanField(default=False)
    reminder_7_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["valid_from", "pk"]
        verbose_name_plural = "series"

    def __str__(self):
        return f"{self.place} {self.valid_from}..{self.valid_until}"


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
    # SET_NULL: deleting a series (admin) must not erase reservation history.
    series = models.ForeignKey(
        Series, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations"
    )
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
    # The holder is the place's fixed owner (set on create, move and swap;
    # kept after anonymization for the no-show rule and statistics).
    owner_use = models.BooleanField(default=False)
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

    def save(self, *args, **kwargs):
        # Every creation path: the fixed owner using their own place.
        if self._state.adding and self.holder_id and self.place_id:
            self.owner_use = self.place.fixed_owner_id == self.holder_id
        super().save(*args, **kwargs)


class Absence(models.Model):
    """A period (whole local days, inclusive) in which a person is away.
    No reason is stored (privacy); deleted after retention (``privacy.anonymize_due``)."""

    class Kind(models.TextChoices):
        VACATION = "vacation", "Vacation"
        ABSENT = "absent", "Absent"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="desk_absences"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="desk_absence_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.user} {self.start_date}..{self.end_date}"


class SwapRequest(models.Model):
    """A request to exchange the places of two reservations of the same day.
    ``from_reservation`` belongs to the requester, ``to_reservation`` to the
    person asked."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    from_reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="swap_requests_out"
    )
    to_reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="swap_requests_in"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"swap {self.from_reservation_id} <-> {self.to_reservation_id} ({self.status})"


class ReleaseRequest(models.Model):
    """A request to the holder to hand over the rest of a reservation."""

    Status = SwapRequest.Status

    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="release_requests"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    # Whether the holder may see the requester's name.
    show_name = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"release {self.reservation_id} ({self.status})"


class DeskProfile(models.Model):
    """Per-person desksharing preferences."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="desk_profile"
    )
    # Opt-out: hide the name as holder of desks everywhere in the UI.
    hide_name = models.BooleanField(default=False)
    # Local day of the last daily summary mail (so re-runs never duplicate it).
    last_summary_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Desk profile {self.user}"


class NotificationPreference(models.Model):
    """Channel per person and event; no row means the default (``mail``).
    ``push`` and ``both`` are stored for spec 2 but not accepted yet."""

    class Channel(models.TextChoices):
        MAIL = "mail", "Mail"
        PUSH = "push", "Push"
        BOTH = "both", "Mail and push"
        OFF = "off", "Off"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="desk_notification_prefs"
    )
    event = models.CharField(max_length=40)
    channel = models.CharField(max_length=5, choices=Channel.choices, default=Channel.MAIL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "event"], name="desk_pref_unique_user_event"),
        ]

    def __str__(self):
        return f"{self.user_id} {self.event}={self.channel}"
