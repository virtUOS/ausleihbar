# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Signal handlers: blocks, lost rights."""
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from accounts import roles
from accounts.models import AccessGroup
from lending.models import Block

from . import absences
from .models import Place

_CHANGES = ("post_add", "post_remove", "post_clear")


@receiver(post_save, sender=Block, dispatch_uid="desks_block_saved")
def _block_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        absences.on_block_saved(instance)


@receiver(m2m_changed, sender=AccessGroup.members.through, dispatch_uid="desks_members")
def _members_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in _CHANGES:
        return
    roles.invalidate_cache()  # do not depend on receiver order
    if reverse:  # user.access_groups.add(...): the user is the instance
        absences.revoke_lost_rights(user=instance)
    elif pk_set:
        for user in instance.members.model.objects.filter(pk__in=pk_set):
            absences.revoke_lost_rights(user=user)
    else:  # clear (or nothing known): rescan everybody
        absences.revoke_lost_rights()


@receiver(m2m_changed, sender=AccessGroup.pools.through, dispatch_uid="desks_group_pools")
def _group_pools_changed(sender, instance, action, **kwargs):
    if action in _CHANGES:
        roles.invalidate_cache()
        absences.revoke_lost_rights()


@receiver(m2m_changed, sender=Place.access_groups.through, dispatch_uid="desks_place_groups")
def _place_groups_changed(sender, instance, action, reverse, **kwargs):
    if action not in _CHANGES:
        return
    roles.invalidate_cache()
    absences.revoke_lost_rights(place=None if reverse else instance)
