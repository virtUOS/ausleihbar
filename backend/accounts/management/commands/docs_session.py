# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Print a fresh login session key for a user — docs stack only.

The website screenshot script sets it as the session cookie, so no OIDC
login is needed. Refuses to run unless the database name ends with ``_docs``.

Usage:
    python manage.py docs_session alex      # prints the session key
    python manage.py docs_session --cookie-name
"""
from importlib import import_module

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from common.docs_guard import require_docs_database

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


class Command(BaseCommand):
    help = "Print a session key logging in <username> (docs database only)."

    def add_arguments(self, parser):
        parser.add_argument("username", nargs="?")
        parser.add_argument(
            "--cookie-name", action="store_true",
            help="Print the session cookie name instead.",
        )

    def handle(self, *args, username=None, cookie_name=False, **options):
        require_docs_database()
        if cookie_name:
            self.stdout.write(settings.SESSION_COOKIE_NAME)
            return
        if not username:
            raise CommandError("Give a username (or --cookie-name).")
        user = get_user_model().objects.filter(username=username, is_active=True).first()
        if user is None:
            raise CommandError(f"No active user '{username}'.")
        session = import_module(settings.SESSION_ENGINE).SessionStore()
        session[SESSION_KEY] = user._meta.pk.value_to_string(user)
        session[BACKEND_SESSION_KEY] = MODEL_BACKEND
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.create()
        self.stdout.write(session.session_key)
