# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Maintenance helpers for resource defect history."""
from .models import Resource, ResourceDefect


def backfill_open_defects():
    """Open a defect-history record for every currently-defective resource
    that has no open one, so defects that predate the history (or were imported
    directly) still show up. Idempotent. Returns the number created.

    The record's reported time is set to the resource's last-updated time as
    the best available estimate of when it became defective.
    """
    created = 0
    for resource in Resource.objects.filter(status=Resource.Status.DEFECTIVE):
        if resource.defects.filter(resolved_at__isnull=True).exists():
            continue
        defect = ResourceDefect.objects.create(
            resource=resource, note=resource.defect_note
        )
        ResourceDefect.objects.filter(pk=defect.pk).update(
            created_at=resource.updated_at
        )
        created += 1
    return created
