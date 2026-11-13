# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Signal handlers: blocks, lost rights."""
import logging

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from accounts import roles
from accounts.models import AccessGroup
from lending.models import Block

from . import absences
from .models import Place

_CHANGES = ("post_add", "post_remove", "post_clear")


logger = logging.getLogger(__name__)

# Revocations requested during the current transaction(s); flushed once after
# commit, so ``.set()`` (remove, then add) never cancels what the new state
# still grants.
_pending = {"all": False, "users": set(), "places": set()}


def _flush():
    todo = {"all": _pending["all"], "users": set(_pending["users"]),
            "places": set(_pending["places"])}
    _pending.update({"all": False, "users": set(), "places": set()})
    try:
        if todo["all"]:
            absences.revoke_lost_rights()
            return
        for user_id in todo["users"]:
            absences.revoke_lost_rights(user=user_id)
        for place_id in todo["places"]:
            absences.revoke_lost_rights(place=place_id)
    except Exception:
        logger.exception("Revoking lost desksharing rights failed")


def _request(*, everyone=False, users=(), places=()):
    roles.invalidate_cache()  # do not depend on receiver order
    if everyone:
        _pending["all"] = True
    _pending["users"].update(users)
    _pending["places"].update(places)
    transaction.on_commit(_flush)


@receiver(post_save, sender=Block, dispatch_uid="desks_block_saved")
def _block_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return

    def run():
        try:
            absences.on_block_saved(instance)
        except Exception:  # never break a lending Block save
            logger.exception("Releasing reservations for block %s failed", instance.pk)

    transaction.on_commit(run)


@receiver(m2m_changed, sender=AccessGroup.members.through, dispatch_uid="desks_members")
def _members_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in _CHANGES:
        return
    if reverse:  # user.access_groups.add(...): the user is the instance
        _request(users=[instance.pk])
    elif pk_set:
        _request(users=pk_set)
    else:  # clear (or nothing known): rescan everybody
        _request(everyone=True)


@receiver(m2m_changed, sender=AccessGroup.pools.through, dispatch_uid="desks_group_pools")
def _group_pools_changed(sender, instance, action, **kwargs):
    if action in _CHANGES:
        _request(everyone=True)


@receiver(m2m_changed, sender=Place.access_groups.through, dispatch_uid="desks_place_groups")
def _place_groups_changed(sender, instance, action, reverse, **kwargs):
    if action not in _CHANGES:
        return
    if reverse:
        _request(everyone=True)
    else:
        _request(places=[instance.pk])
