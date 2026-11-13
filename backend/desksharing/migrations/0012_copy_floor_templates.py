"""Move existing drawing templates from ``Floor`` into ``FloorTemplate``."""
from django.db import migrations


def forwards(apps, schema_editor):
    Floor = apps.get_model("desksharing", "Floor")
    FloorTemplate = apps.get_model("desksharing", "FloorTemplate")
    for floor in Floor.objects.exclude(template_data=None).iterator():
        if not floor.template_data:
            continue
        FloorTemplate.objects.update_or_create(
            floor_id=floor.pk,
            defaults={
                "data": bytes(floor.template_data),
                "content_type": floor.template_content_type or "application/octet-stream",
            },
        )


def backwards(apps, schema_editor):
    Floor = apps.get_model("desksharing", "Floor")
    FloorTemplate = apps.get_model("desksharing", "FloorTemplate")
    for tpl in FloorTemplate.objects.iterator():
        Floor.objects.filter(pk=tpl.floor_id).update(
            template_data=bytes(tpl.data), template_content_type=tpl.content_type
        )


class Migration(migrations.Migration):

    dependencies = [
        ('desksharing', '0011_floor_template'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
