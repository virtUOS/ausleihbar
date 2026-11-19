# Backfill the new department fields from the floors and merge equipment
# that only differed by department (same name, ignoring case).
from django.db import migrations
from django.db.models.functions import Lower


def backfill_pools(apps, schema_editor):
    Floor = apps.get_model("desksharing", "Floor")
    Room = apps.get_model("desksharing", "Room")
    Place = apps.get_model("desksharing", "Place")
    Reservation = apps.get_model("desksharing", "Reservation")
    for floor in Floor.objects.all():
        Room.objects.filter(floor=floor).update(pool_id=floor.pool_id)
        Place.objects.filter(room__floor=floor).update(pool_id=floor.pool_id)
        Reservation.objects.filter(place__room__floor=floor).update(pool_id=floor.pool_id)


def merge_features(apps, schema_editor):
    Feature = apps.get_model("desksharing", "Feature")
    Through = apps.get_model("desksharing", "Place").features.through
    survivors = {}
    for feature in Feature.objects.annotate(key=Lower("name")).order_by("pk"):
        keep = survivors.setdefault(feature.key, feature)
        if keep.pk == feature.pk:
            continue
        for row in Through.objects.filter(feature_id=feature.pk):
            Through.objects.get_or_create(place_id=row.place_id, feature_id=keep.pk)
        feature.delete()  # cascades its remaining place links


class Migration(migrations.Migration):

    dependencies = [
        ("desksharing", "0020_places_ownership"),
    ]

    operations = [
        migrations.RunPython(backfill_pools, migrations.RunPython.noop),
        migrations.RunPython(merge_features, migrations.RunPython.noop),
    ]
