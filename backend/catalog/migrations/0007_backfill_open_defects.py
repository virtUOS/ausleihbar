"""Backfill defect history for resources that are already defective.

Defects marked before the ResourceDefect history existed only live in the
resource's current ``status``/``defect_note``. Open a history record for each
currently-defective resource (using its last-updated time as the reported
time) so recurring problems are visible. Resolved past defects predate any
stored data and cannot be reconstructed.
"""
from django.db import migrations


def backfill_open_defects(apps, schema_editor):
    Resource = apps.get_model("catalog", "Resource")
    ResourceDefect = apps.get_model("catalog", "ResourceDefect")
    for resource in Resource.objects.filter(status="defective"):
        if ResourceDefect.objects.filter(
            resource=resource, resolved_at__isnull=True
        ).exists():
            continue
        defect = ResourceDefect.objects.create(
            resource=resource, note=resource.defect_note
        )
        # created_at is auto_now_add; reset it to the resource's last-updated
        # time as the best available estimate of when it became defective.
        ResourceDefect.objects.filter(pk=defect.pk).update(
            created_at=resource.updated_at
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_resourcedefect"),
    ]

    operations = [
        migrations.RunPython(backfill_open_defects, migrations.RunPython.noop),
    ]
