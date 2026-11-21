# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Keep course groups' names in sync when their pool is renamed."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from catalog.models import ResourcePool

from .services import ensure_course_group


@receiver(post_save, sender=ResourcePool, dispatch_uid="lti_course_group_names")
def _sync_course_groups(sender, instance, raw=False, **kwargs):
    if raw:
        return
    for link in instance.course_links.select_related("pool"):
        ensure_course_group(link)
