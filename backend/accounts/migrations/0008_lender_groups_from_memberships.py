# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Move lender assignments into per-pool system groups (#80).

Forward: every pool (incl. trashed ones) gets its system group
"Verleiher ‹Pool›" whose manual members are the pool's ``PoolMembership``
users; the system group "Administratoren" is created (no members — admins via
``is_staff``/``is_superuser`` stay as they are). Idempotent.

Backward: recreate ``PoolMembership`` rows from the system groups' manual
members, then drop the system groups.
"""
from django.db import migrations

ADMIN_GROUP_NAME = "Administratoren"


def _free_name(AccessGroup, base):
    name, n = base, 1
    while AccessGroup.objects.filter(name=name).exists():
        n += 1
        name = f"{base} ({n})"
    return name


def forward(apps, schema_editor):
    AccessGroup = apps.get_model("accounts", "AccessGroup")
    PoolMembership = apps.get_model("accounts", "PoolMembership")
    ResourcePool = apps.get_model("catalog", "ResourcePool")

    # _base_manager: include trashed (soft-deleted) pools.
    for pool in ResourcePool._base_manager.order_by("pk"):
        group = AccessGroup.objects.filter(system_pool=pool).first()
        if group is None:
            group = AccessGroup.objects.create(
                name=_free_name(AccessGroup, f"Verleiher {pool.name}"),
                system_pool=pool,
            )
        group.lender_pools.set([pool])
        user_ids = PoolMembership.objects.filter(resource_pool=pool).values_list(
            "user_id", flat=True
        )
        group.members.add(*user_ids)

    if not AccessGroup.objects.filter(system_admin=True).exists():
        AccessGroup.objects.create(
            name=_free_name(AccessGroup, ADMIN_GROUP_NAME),
            is_admin=True,
            system_admin=True,
        )


def backward(apps, schema_editor):
    AccessGroup = apps.get_model("accounts", "AccessGroup")
    PoolMembership = apps.get_model("accounts", "PoolMembership")

    for group in AccessGroup.objects.filter(system_pool__isnull=False):
        for user_id in group.members.values_list("id", flat=True):
            PoolMembership.objects.get_or_create(
                user_id=user_id, resource_pool_id=group.system_pool_id, role="manager"
            )
    AccessGroup.objects.filter(system_pool__isnull=False).delete()
    AccessGroup.objects.filter(system_admin=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_access_group_rights"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
