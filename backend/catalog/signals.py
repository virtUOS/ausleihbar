# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Keep a resource's defect history in sync with its status.

Whenever a resource's status moves to ``defective`` an open ResourceDefect is
opened (carrying the current defect note); when it moves away from
``defective`` any open record is resolved. This captures every path —
the lending-desk actions, the admin inventory form, or the shell.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Resource


@receiver(pre_save, sender=Resource)
def _remember_old_status(sender, instance, **kwargs):
    if instance.pk:
        instance._old_status = (
            Resource.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )
    else:
        instance._old_status = None


@receiver(post_save, sender=Resource)
def _track_defects(sender, instance, created, **kwargs):
    old = getattr(instance, "_old_status", None)
    defective = Resource.Status.DEFECTIVE
    if instance.status == defective and old != defective:
        if not instance.defects.filter(resolved_at__isnull=True).exists():
            instance.defects.create(note=instance.defect_note)
    elif old == defective and instance.status != defective:
        instance.defects.filter(resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )
