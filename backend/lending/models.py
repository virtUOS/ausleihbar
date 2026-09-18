# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Lending domain — the heart of the system (ADR-0003, ADR-0006).

Bookings are time intervals per resource. A PostgreSQL exclusion constraint
guarantees that no two *active* booking items for the same resource overlap.
"""
from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


class Booking(TimeStampedModel):
    """A borrower's reservation/booking, made up of one or more items."""

    class Status(models.TextChoices):
        CART = "cart", "Cart"                    # in progress; holds slots, expires
        PENDING = "pending", "Pending"           # submitted, awaiting confirmation
        CONFIRMED = "confirmed", "Confirmed"
        HANDED_OUT = "handed_out", "Handed out"
        RETURNED = "returned", "Returned"
        CANCELLED = "cancelled", "Cancelled"

    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.CART
    )
    # Human-readable reservation number, e.g. "R-00042".
    code = models.CharField(max_length=16, blank=True)
    # Optional borrower message (e.g. "for the music seminar", "picked up by X").
    note = models.TextField(blank=True)
    # When a cart's slot hold expires (then the held slots are free again).
    expires_at = models.DateTimeField(null=True, blank=True)
    # Last time an overdue reminder was emailed (to avoid resending too often).
    overdue_reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Booking {self.code or f'#{self.pk}'} ({self.status})"

    def submit(self, note=""):
        """Submit a cart as a reservation: awaiting confirmation, no expiry."""
        self.status = self.Status.PENDING
        self.note = note
        self.expires_at = None
        self.save(update_fields=["status", "note", "expires_at", "updated_at"])

    def cancel(self):
        """Cancel the booking and release its held slots."""
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])
        self.items.update(is_active=False)

    def confirm(self):
        """Confirm a pending reservation (the hold no longer expires)."""
        self.status = self.Status.CONFIRMED
        self.expires_at = None
        self.save(update_fields=["status", "expires_at", "updated_at"])

    def _sync_status(self):
        """Roll the booking status up from its items' handout/return state."""
        # values_list issues a fresh query, bypassing any prefetched item cache.
        states = list(self.items.values_list("handed_out_at", "returned_at"))
        if states and all(returned for _, returned in states):
            new_status = self.Status.RETURNED
        elif any(out and not returned for out, returned in states):
            new_status = self.Status.HANDED_OUT
        elif self.status in (self.Status.HANDED_OUT, self.Status.RETURNED):
            new_status = self.Status.CONFIRMED  # everything reverted
        else:
            new_status = self.status
        if new_status != self.status:
            self.status = new_status
            self.save(update_fields=["status", "updated_at"])

    def hand_out_items(self, item_ids=None):
        """Hand out items (one appointment); default = all not-yet-handed-out."""
        from django.utils import timezone

        items = self.items.filter(is_active=True, handed_out_at__isnull=True)
        if item_ids is not None:
            items = items.filter(id__in=item_ids)
        items.update(handed_out_at=timezone.now())
        self._sync_status()

    def return_items(self, item_ids=None):
        """Take items back (one appointment); frees their slots."""
        from django.utils import timezone

        items = self.items.filter(
            handed_out_at__isnull=False, returned_at__isnull=True
        )
        if item_ids is not None:
            items = items.filter(id__in=item_ids)
        items.update(returned_at=timezone.now(), is_active=False)
        self._sync_status()

    # Whole-booking convenience (used by tests / single-appointment bookings).
    def hand_out(self):
        self.hand_out_items()

    def mark_returned(self):
        self.return_items()


class Block(TimeStampedModel):
    """A blocked time range during which affected resources cannot be booked.

    Scope is determined by which target is set (most specific wins for the
    "scope" label, but a resource is blocked if *any* applicable block exists):
    resource > product > pool > system (all targets empty = system-wide).
    """

    period = DateTimeRangeField()
    reason = models.CharField(max_length=255, blank=True)
    resource_pool = models.ForeignKey(
        "catalog.ResourcePool", null=True, blank=True, on_delete=models.CASCADE,
        related_name="blocks",
    )
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.CASCADE,
        related_name="blocks",
    )
    resource = models.ForeignKey(
        "catalog.Resource", null=True, blank=True, on_delete=models.CASCADE,
        related_name="blocks",
    )

    class Meta:
        ordering = ["-created_at"]

    @property
    def scope(self):
        if self.resource_id:
            return "resource"
        if self.product_id:
            return "product"
        if self.resource_pool_id:
            return "pool"
        return "system"

    def __str__(self):
        return f"Block ({self.scope}) {self.period}"


class BookingItem(models.Model):
    """One reserved resource for a time interval."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="items")
    resource = models.ForeignKey(
        "catalog.Resource",
        on_delete=models.PROTECT,
        related_name="booking_items",
    )
    period = DateTimeRangeField()
    # Whether this item currently occupies the resource (false once cancelled
    # or returned).
    is_active = models.BooleanField(default=True)
    # Per-appointment handout/return — a multi-period reservation is handed out
    # and taken back one appointment at a time.
    handed_out_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    # Set when the "product missing" notice was sent, so the periodic job does
    # not mail the same upcoming borrower twice (issue #48).
    missing_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            ExclusionConstraint(
                name="no_overlapping_active_bookings",
                expressions=[
                    ("resource", RangeOperators.EQUAL),
                    ("period", RangeOperators.OVERLAPS),
                ],
                condition=Q(is_active=True),
            )
        ]

    def __str__(self):
        return f"{self.resource} @ {self.period}"


class BookingReminder(TimeStampedModel):
    """Audit record of an overdue reminder emailed to the borrower.

    ``created_at`` is when the reminder was sent.
    """

    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="reminders"
    )
    recipient = models.EmailField(blank=True)
    overdue_pickups = models.PositiveSmallIntegerField(default=0)
    overdue_returns = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reminder for booking {self.booking_id} at {self.created_at}"


class HolidaySetting(models.Model):
    """System-wide region used to auto-load public holidays as blocks.

    A singleton (pk is forced to 1). Admins set the country and subdivision
    (e.g. DE / NI); the system loads public holidays for at least the longest
    pool booking horizon (concept §3.5).
    """

    country = models.CharField(max_length=2, default="DE")
    subdivision = models.CharField(max_length=8, blank=True)

    class Meta:
        verbose_name = "holiday setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Holidays: {self.country}/{self.subdivision or '—'}"


class CartSetting(models.Model):
    """System-wide cart configuration (concept §4.5).

    A singleton (pk is forced to 1). ``hold_minutes`` is how long a cart holds
    its reserved resources before the hold expires; every cart action renews
    the hold. When it lapses the resources are freed again.
    """

    hold_minutes = models.PositiveIntegerField(default=30)

    class Meta:
        verbose_name = "cart setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"Cart hold: {self.hold_minutes} min"
