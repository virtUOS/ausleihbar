# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Creates the database cache table (``settings.CACHES["default"]``).

The LTI login stores pylti1p3's OIDC state/nonce in the default cache and the
launch reads them back — possibly in another gunicorn worker, so the cache
must be shared (database table instead of per-process LocMem).
"""
from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command(
        "createcachetable", database=schema_editor.connection.alias, verbosity=0
    )


def drop_cache_table(apps, schema_editor):
    for cache in settings.CACHES.values():
        if cache["BACKEND"].endswith("DatabaseCache"):
            table = schema_editor.quote_name(cache["LOCATION"])
            schema_editor.execute(f"DROP TABLE IF EXISTS {table}")


class Migration(migrations.Migration):
    dependencies = [("lti", "0001_initial")]

    operations = [migrations.RunPython(create_cache_table, drop_cache_table)]
