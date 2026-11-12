# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing settings per department (= ``catalog.ResourcePool``)."""
from django.core.exceptions import ValidationError
from django.db import models

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
