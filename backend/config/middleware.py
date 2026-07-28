# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Request-language activation for content translation (issue #6).

The SPA knows which language it is showing and passes it explicitly as a
``?lang=`` query parameter on API calls; browsers also send ``Accept-Language``.
This middleware activates the resulting language for the request so
django-modeltranslation serves the matching translation of catalog content and
fields fall back per ``MODELTRANSLATION_FALLBACK_LANGUAGES`` when empty.
"""

from django.conf import settings
from django.utils import translation


class ActiveLanguageMiddleware:
    """Activate the request language from ``?lang=`` or ``Accept-Language``."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._supported = {code for code, _ in settings.LANGUAGES}

    def __call__(self, request):
        language = self._language_for(request)
        translation.activate(language)
        request.LANGUAGE_CODE = language
        try:
            return self.get_response(request)
        finally:
            translation.deactivate()

    def _language_for(self, request):
        # An explicit ?lang= wins (only the two-letter base, e.g. "de-DE" → "de").
        requested = request.GET.get("lang", "").split("-")[0].lower()
        if requested in self._supported:
            return requested
        # Otherwise honour the browser's Accept-Language header.
        return translation.get_language_from_request(request, check_path=False)
