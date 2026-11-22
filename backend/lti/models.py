# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""LTI course pools: LMS course ↔ pool links and the LTI switch.

Platform registrations, the tool key and LTI user links come from
basicbar-lti; this app holds what a course context maps onto here — one or
more pools, each through an ``LtiCourseLink`` that owns a system access group
(``AccessGroup.system_course``). Learners launching from the course join the
group; the group gates the pool while the link is active.
"""
from basicbar_lti.models import LtiPlatform
from django.conf import settings
from django.db import models, transaction

from common.models import TimeStampedModel


class LtiSetting(models.Model):
    """System-wide LTI switches. Singleton (pk forced to 1)."""

    # Lecturers may create their own (personal) pool from a course launch.
    # Off by default: an admin creates the pool and makes the lecturer lender.
    instructors_create_pools = models.BooleanField(default=False)

    class Meta:
        verbose_name = "LTI setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "LTI setting"


class LtiCourseLink(TimeStampedModel):
    """An LMS course (platform + context) opened to one pool.

    Saving keeps the link's system access group in sync (created on first
    save, named after course and pool, attached to the pool's visibility
    groups only while ``is_active``); deleting the link deletes the group.
    """

    platform = models.ForeignKey(
        LtiPlatform, on_delete=models.CASCADE, related_name="course_links"
    )
    context_id = models.CharField(max_length=255)
    # Course title from the LMS, refreshed on every launch.
    title = models.CharField(max_length=255, blank=True)
    pool = models.ForeignKey(
        "catalog.ResourcePool", on_delete=models.CASCADE, related_name="course_links"
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_course_links",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "context_id", "pool"],
                name="one_link_per_course_and_pool",
            )
        ]

    def save(self, *args, **kwargs):
        from .services import ensure_course_group

        with transaction.atomic():
            super().save(*args, **kwargs)
            ensure_course_group(self)

    def __str__(self):
        return f"{self.platform.name}:{self.context_id} → {self.pool}"
