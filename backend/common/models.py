# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Shared base models and mixins."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base model that tracks creation and update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager — hides trashed rows from every ordinary query."""

    def get_queryset(self):
        return super().get_queryset().alive()


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    pass


class SoftDeleteModel(TimeStampedModel):
    """Abstract base: `delete` in the UI sets `deleted_at` instead of removing
    the row. Trashed rows are hidden by the default manager; `all_objects` sees
    everything (trash view, purge, restore lookups)."""

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        # Django's integrity checks / cascade collection must see ALL rows.
        base_manager_name = "all_objects"

    @property
    def is_trashed(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, user=None):
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


class CspViolation(models.Model):
    """One aggregated Content-Security-Policy violation (issue #44).

    Reports from browsers are normalised (``common.csp``) so a row carries no
    personal data — no IP, user or query string — and repeated reports only
    bump ``count``/``last_seen``.
    """

    directive = models.CharField(max_length=100)
    blocked = models.CharField(max_length=200, blank=True)
    page = models.CharField(max_length=200)
    count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen"]
        constraints = [
            models.UniqueConstraint(
                fields=["directive", "blocked", "page"], name="unique_csp_violation"
            )
        ]
        verbose_name = "CSP violation"
        verbose_name_plural = "CSP violations"

    def __str__(self):
        return f"{self.directive}: {self.blocked or '—'} on {self.page}"
