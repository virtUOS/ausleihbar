from django.db import migrations

GROUP_NAME = "Alle Angemeldeten"


def _free_name(AccessGroup):
    name, n = GROUP_NAME, 1
    while AccessGroup.objects.filter(name=name).exists():
        n += 1
        name = f"{GROUP_NAME} ({n})"
    return name


def attach_all_users_group(apps, schema_editor):
    """Pools that are open today (no ordinary group, not personal — soft-deleted
    and inactive ones too) get the group "Alle Angemeldeten" (ADR-0021)."""
    AccessGroup = apps.get_model("accounts", "AccessGroup")
    ResourcePool = apps.get_model("catalog", "ResourcePool")
    group = AccessGroup.objects.filter(system_all=True).first()
    if group is None:
        group = AccessGroup.objects.create(name=_free_name(AccessGroup), system_all=True)
    restricted = AccessGroup.objects.filter(
        system_course__isnull=True, pools__isnull=False
    ).values("pools")
    open_pools = ResourcePool._base_manager.filter(is_personal=False).exclude(
        pk__in=restricted
    )
    group.pools.add(*open_pools)


def detach_all_users_group(apps, schema_editor):
    AccessGroup = apps.get_model("accounts", "AccessGroup")
    AccessGroup.objects.filter(system_all=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_accessgroup_system_all"),
        ("catalog", "0072_resourcepool_is_personal"),
    ]

    operations = [
        migrations.RunPython(attach_all_users_group, detach_all_users_group),
    ]
