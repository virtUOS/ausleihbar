# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Safety guard for the website screenshot tooling (``seed_docs_demo``,
``docs_session``).

Those commands wipe data and mint login sessions, so they only ever run
against the isolated docs database (``docker-compose.docs.yml``), whose name
ends with ``_docs`` — never the dev or production database.
"""
from django.core.management.base import CommandError
from django.db import connection

DOCS_DB_SUFFIX = "_docs"


def docs_database_active():
    """Whether the active database is a docs database (name ends ``_docs``)."""
    return str(connection.settings_dict.get("NAME") or "").endswith(DOCS_DB_SUFFIX)


def require_docs_database():
    """Raise ``CommandError`` unless the docs database is active."""
    if not docs_database_active():
        raise CommandError(
            f"Only for the docs database (…{DOCS_DB_SUFFIX}); the active "
            f"database is '{connection.settings_dict.get('NAME')}'."
        )
