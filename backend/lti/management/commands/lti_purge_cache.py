# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Delete expired rows of the database cache (``settings.CACHES``).

The ``default`` cache is a ``DatabaseCache`` (table ``django_cache``): it
holds pylti1p3's launch state/nonce and launch data (name, e-mail, roles,
course) and the one-time hand-off tokens of framed launches. Django removes
expired rows only when the table outgrows ``MAX_ENTRIES``, so without this
pass they stay in the table (and in backups). Run it periodically (cron).
"""
from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.core.management.base import BaseCommand
from django.db import connections, router
from django.utils import timezone


def purge_expired() -> int:
    """Delete expired entries from every database cache; returns the count."""
    deleted = 0
    for alias in caches.settings:
        cache = caches[alias]
        if not isinstance(cache, DatabaseCache):
            continue
        connection = connections[router.db_for_write(cache.cache_model_class)]
        quote = connection.ops.quote_name
        now = timezone.now().replace(microsecond=0)
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {quote(cache._table)} WHERE {quote('expires')} < %s",
                [connection.ops.adapt_datetimefield_value(now)],
            )
            deleted += max(cursor.rowcount, 0)
    return deleted


class Command(BaseCommand):
    help = "Delete expired rows of the database cache (LTI launch data, hand-off tokens)."

    def handle(self, *args, **options):
        deleted = purge_expired()
        self.stdout.write(f"Deleted {deleted} expired cache entries.")
