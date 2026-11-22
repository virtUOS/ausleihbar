# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Signal handlers for role groups (#80).

- **Pool → system lender group:** this is the one place that creates a pool's
  "Verleiher ‹Pool›" group and keeps its name in sync on rename. It runs on
  every ``ResourcePool`` save (API, Django admin, ZIP import, shell). A trashed
  (soft-deleted) pool keeps its group; a hard delete removes it via CASCADE.
- **Role cache invalidation:** any change to group membership, group rights or
  a user's claims bumps ``accounts.roles``' cache generation.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from catalog.models import ResourcePool

from . import roles
from .models import AccessGroup


@receiver(post_save, sender=ResourcePool)
def _sync_pool_lender_group(sender, instance, raw=False, **kwargs):
    if raw:  # loaddata: fixtures carry their own groups
        return
    roles.ensure_pool_lender_group(instance)


def _invalidate(*args, **kwargs):
    roles.invalidate_cache()


post_save.connect(_invalidate, sender=AccessGroup, dispatch_uid="roles_group_save")
post_delete.connect(_invalidate, sender=AccessGroup, dispatch_uid="roles_group_delete")
post_save.connect(_invalidate, sender=settings.AUTH_USER_MODEL, dispatch_uid="roles_user_save")
m2m_changed.connect(
    _invalidate, sender=AccessGroup.members.through, dispatch_uid="roles_members"
)
m2m_changed.connect(
    _invalidate, sender=AccessGroup.lender_pools.through, dispatch_uid="roles_lender_pools"
)


def _no_rights_for_course_groups(sender, instance, action, reverse, pk_set, **kwargs):
    """LTI course groups grant visibility only: refuse adding lender pools to
    one, from either side of the relation (``group.lender_pools.add(pool)``
    or ``pool.lender_groups.add(group)``)."""
    if action != "pre_add" or not pk_set:
        return
    if reverse:  # instance is a pool, pk_set are group ids
        is_course = AccessGroup.objects.filter(
            pk__in=pk_set, system_course__isnull=False
        ).exists()
    else:
        is_course = instance.system_course_id is not None
    if is_course:
        raise ValidationError("A course group can't grant lender rights.")


m2m_changed.connect(
    _no_rights_for_course_groups,
    sender=AccessGroup.lender_pools.through,
    dispatch_uid="course_group_no_lender_pools",
)
