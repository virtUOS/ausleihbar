# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Signal handlers: blocks, lost rights."""
import logging
import threading

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

# Revocations requested by the current thread's transaction, flushed once
# after commit, so ``.set()`` (remove, then add) never cancels what the new
# state still grants. The collection is per thread and each on_commit closure
# flushes only the collection it captured, so concurrent requests never
# consume each other's entries. After a rollback the stale entries are
# harmless: they are flushed by the next commit's closure and only re-check
# rights.
_local = threading.local()


def _new_collection():
    return {"all": False, "users": set(), "places": set(), "done": False}


def _flush(coll):
    if coll["done"]:
        return
    coll["done"] = True
    if getattr(_local, "coll", None) is coll:
        _local.coll = None
    try:
        if coll["all"]:
            absences.revoke_lost_rights()
            return
        for user_id in coll["users"]:
            absences.revoke_lost_rights(user=user_id)
        for place_id in coll["places"]:
            absences.revoke_lost_rights(place=place_id)
    except Exception:
        logger.exception("Revoking lost desksharing rights failed")


def _request(*, everyone=False, users=(), places=()):
    roles.invalidate_cache()  # do not depend on receiver order
    coll = getattr(_local, "coll", None)
    if coll is None or coll["done"]:
        coll = _local.coll = _new_collection()
    if everyone:
        coll["all"] = True
    coll["users"].update(users)
    coll["places"].update(places)
    transaction.on_commit(lambda: _flush(coll))


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
