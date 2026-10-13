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
