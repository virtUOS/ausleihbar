# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower

CODE_MAX = 20


def to_buildings(apps, schema_editor):
    """One building per distinct former free text (case-insensitive). A text
    longer than a code keeps its full wording as the description."""
    Building = apps.get_model("desksharing", "Building")
    Floor = apps.get_model("desksharing", "Floor")
    by_key = {}
    for floor in Floor.objects.exclude(building_legacy="").order_by("pk"):
        text = floor.building_legacy.strip()
        if not text:
            continue
        key = text.lower()
        if key not in by_key:
            code = text[:CODE_MAX].strip()
            base, n = code, 2
            while Building.objects.filter(code__iexact=code).exists():
                suffix = f"-{n}"
                code = base[: CODE_MAX - len(suffix)] + suffix
                n += 1
            by_key[key] = Building.objects.create(
                code=code, description=text if len(text) > CODE_MAX else ""
            )
        floor.building = by_key[key]
        floor.save(update_fields=["building"])


def to_text(apps, schema_editor):
    Floor = apps.get_model("desksharing", "Floor")
    for floor in Floor.objects.exclude(building=None).select_related("building"):
        b = floor.building
        floor.building_legacy = (b.description if b.description and len(b.description) <= 100 else b.code)
        floor.save(update_fields=["building_legacy"])


class Migration(migrations.Migration):
    dependencies = [
        ("desksharing", "0016_remove_absence_kind"),
    ]

    operations = [
        migrations.CreateModel(
            name="Building",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=20)),
                ("description", models.CharField(blank=True, max_length=200)),
                ("address", models.TextField(blank=True)),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.AddConstraint(
            model_name="building",
            constraint=models.UniqueConstraint(Lower("code"), name="desk_building_code_unique"),
        ),
        migrations.RenameField(model_name="floor", old_name="building", new_name="building_legacy"),
        migrations.AddField(
            model_name="floor",
            name="building",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="floors", to="desksharing.building",
            ),
        ),
        migrations.AlterModelOptions(
            name="floor", options={"ordering": ["building__code", "position", "name"]},
        ),
        migrations.RunPython(to_buildings, to_text),
        migrations.RemoveField(model_name="floor", name="building_legacy"),
    ]
