# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Django settings for the device lending system."""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_list(name, default):
    """Comma-separated env var → list, dropping blanks.

    An empty or trailing-comma value (e.g. CORS_ALLOWED_ORIGINS unset in
    docker-compose) yields [] rather than [''], which would otherwise fail
    Django's system checks (e.g. corsheaders.E013).
    """
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,backend"
)

INSTALLED_APPS = [
    # Must precede django.contrib.admin so the admin picks up the translated
    # field forms (django-modeltranslation requirement).
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Third-party
    "rest_framework",
    "corsheaders",
    "mozilla_django_oidc",
    "basicbar_auth",
    "basicbar_integrations",
    # Local apps
    "common",
    "accounts",
    "catalog",
    "lending",
    "tenancy",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Activates the request language (?lang= → Accept-Language) so
    # django-modeltranslation serves the matching translation of catalog
    # content. Must run before the view/serializers read the active language.
    "config.middleware.ActiveLanguageMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "ausleihbar"),
        "USER": os.environ.get("POSTGRES_USER", "ausleihbar"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "ausleihbar"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

# Supported languages for the UI and notification emails (concept: i18n).
LANGUAGES = [("en", "English"), ("de", "German")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Content translation (django-modeltranslation, issue #6) ---
# User-entered catalog content (product/category/section/set/page/pool text) is
# translatable. The "default" language is the canonical one: it is required when
# creating content and is the first fallback the shop shows when another
# language has no value. It is configurable per deployment (CONTENT_DEFAULT_
# LANGUAGE) so an institution publishing this software can flip it to English —
# our instance keeps German because the existing data was entered in German and
# migration 0021 backfilled it into the `*_de` columns.
MODELTRANSLATION_LANGUAGES = tuple(code for code, _ in LANGUAGES)
MODELTRANSLATION_DEFAULT_LANGUAGE = os.environ.get("CONTENT_DEFAULT_LANGUAGE", "de")
if MODELTRANSLATION_DEFAULT_LANGUAGE not in MODELTRANSLATION_LANGUAGES:
    raise ValueError(
        f"CONTENT_DEFAULT_LANGUAGE={MODELTRANSLATION_DEFAULT_LANGUAGE!r} is not one "
        f"of the supported languages {MODELTRANSLATION_LANGUAGES}."
    )
# Try the default language first when a field is untranslated, then the rest.
MODELTRANSLATION_FALLBACK_LANGUAGES = (
    MODELTRANSLATION_DEFAULT_LANGUAGE,
    *(c for c in MODELTRANSLATION_LANGUAGES if c != MODELTRANSLATION_DEFAULT_LANGUAGE),
)

# Optional machine translation to pre-fill empty translations in the editor
# (issue #6 Phase 4). Off by default; set CONTENT_TRANSLATION_PROVIDER to
# "libretranslate" and point LIBRETRANSLATE_URL at a (self-hosted) instance.
# Only pre-fills an editable draft — it never overwrites a human translation.
CONTENT_TRANSLATION_PROVIDER = os.environ.get("CONTENT_TRANSLATION_PROVIDER", "none")
LIBRETRANSLATE_URL = os.environ.get("LIBRETRANSLATE_URL", "")
LIBRETRANSLATE_API_KEY = os.environ.get("LIBRETRANSLATE_API_KEY", "")

# Symmetric key (Fernet) for encrypting stored third-party secrets at rest —
# currently the per-pool GitLab access token. Prefer a dedicated, stable key in
# TOKEN_ENCRYPTION_KEY (generate one with
# `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
# If unset, a key is derived from DJANGO_SECRET_KEY so it works out of the box —
# but then rotating SECRET_KEY makes already-stored secrets undecryptable.
TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")

# Optional AI features via an OpenAI-compatible LiteLLM endpoint. Off by
# default; set AI_PROVIDER=litellm plus the URL/key/model to enable. Changing
# these requires recreating the container (env is read at startup).
AI_PROVIDER = os.environ.get("AI_PROVIDER", "none")   # none | litellm
AI_BASE_URL = os.environ.get("AI_BASE_URL", "")       # OpenAI-compatible, e.g. https://…/v1
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "")             # e.g. qwen-3.5


def _int_or_none(name):
    """Read a non-negative integer cap from the environment; blank/unset/invalid
    → ``None`` (meaning unlimited)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _int_or_default(name, default):
    """Read an integer from the environment; blank/unset/invalid → ``default``.

    Unlike ``_int_or_none``, this is for settings that need a real numeric
    value (not "unlimited") — e.g. a request timeout — so a malformed env var
    doesn't crash Django at startup.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


AI_TIMEOUT = _int_or_default("AI_TIMEOUT", 30)
# Upper bound on the model's reply length. Generous by default so a reasoning
# model still has room for its answer after any hidden "thinking" tokens.
AI_MAX_TOKENS = _int_or_default("AI_MAX_TOKENS", 2000)
# Reasoning models (e.g. Qwen3) otherwise spend the whole token budget on
# hidden reasoning and return an empty answer. For our structured JSON calls we
# don't want that reasoning, so ask the backend to disable it. Harmless for
# models that don't support the flag; set AI_DISABLE_THINKING=0 to send it off.
AI_DISABLE_THINKING = os.environ.get("AI_DISABLE_THINKING", "1") == "1"

# Optional per-deployment caps on how many can be created. Unset = unlimited.
# Enforced when creating via the API (products, resources) or on first OIDC
# login (users); bulk imports and the shell are not capped.
MAX_RESOURCES = _int_or_none("MAX_RESOURCES")
MAX_PRODUCTS = _int_or_none("MAX_PRODUCTS")
MAX_USERS = _int_or_none("MAX_USERS")

STATIC_URL = "static/"
# Target for `collectstatic` in production (served by the reverse proxy).
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded media (product/category/section/pool images).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Behind a TLS-terminating reverse proxy (e.g. Caddy) in production: trust its
# forwarded host/scheme so absolute URLs use https, and require secure cookies.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow the React/Vite dev server to call the API during development.
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
# The SPA calls the API with the session cookie (same-site localhost).
CORS_ALLOW_CREDENTIALS = True
# Cross-origin POSTs from the SPA carry the CSRF token; trust its origin.
CSRF_TRUSTED_ORIGINS = _env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000"
)

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    # Turns an unhandled IntegrityError (e.g. a unique collision with a
    # trashed row the default manager can't see) into a clean 400.
    "EXCEPTION_HANDLER": "common.exceptions.exception_handler",
}

# --- Email / notifications (Roadmap area G) ---
# Console backend in dev prints mails to the backend log; set EMAIL_BACKEND to
# the SMTP backend plus the EMAIL_HOST/* vars in production. The test runner
# swaps in the locmem backend automatically.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0") == "1"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "Ausleihbar <noreply@ausleihbar.local>"
)
# Public base URL of the shop, used for links inside notification emails.
SHOP_BASE_URL = os.environ.get("SHOP_BASE_URL", "http://localhost:5173")

# --- Authentication / OIDC (ADR-0004) ---
# OIDC is the primary login; Django's ModelBackend stays as a local dev /
# break-glass fallback (e.g. the bootstrap superuser from `createsuperuser`).
AUTHENTICATION_BACKENDS = [
    "basicbar_auth.oidc.OIDCBackend",
    "django.contrib.auth.backends.ModelBackend",
]

OIDC_RP_CLIENT_ID = os.environ.get("OIDC_RP_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = os.environ.get("OIDC_RP_CLIENT_SECRET", "")
OIDC_RP_SIGN_ALGO = "RS256"
# Keep the ID token in the session so logout can send it as id_token_hint.
OIDC_STORE_ID_TOKEN = True

# Endpoints: set them explicitly, or set OIDC_OP_ISSUER to derive them from the
# provider's discovery document. Explicit values always win (needed for the
# local browser/backchannel split). Switching provider = change these env vars.
OIDC_OP_ISSUER = os.environ.get("OIDC_OP_ISSUER", "")
OIDC_OP_AUTHORIZATION_ENDPOINT = os.environ.get("OIDC_OP_AUTHORIZATION_ENDPOINT", "")
OIDC_OP_TOKEN_ENDPOINT = os.environ.get("OIDC_OP_TOKEN_ENDPOINT", "")
OIDC_OP_USER_ENDPOINT = os.environ.get("OIDC_OP_USER_ENDPOINT", "")
OIDC_OP_JWKS_ENDPOINT = os.environ.get("OIDC_OP_JWKS_ENDPOINT", "")
OIDC_OP_LOGOUT_ENDPOINT = os.environ.get("OIDC_OP_LOGOUT_ENDPOINT", "")

if OIDC_OP_ISSUER and not OIDC_OP_AUTHORIZATION_ENDPOINT:
    from basicbar_auth.discovery import discover_endpoints

    _discovered = discover_endpoints(OIDC_OP_ISSUER)
    OIDC_OP_AUTHORIZATION_ENDPOINT = _discovered.get("authorization_endpoint", "")
    OIDC_OP_TOKEN_ENDPOINT = OIDC_OP_TOKEN_ENDPOINT or _discovered.get("token_endpoint", "")
    OIDC_OP_USER_ENDPOINT = OIDC_OP_USER_ENDPOINT or _discovered.get("userinfo_endpoint", "")
    OIDC_OP_JWKS_ENDPOINT = OIDC_OP_JWKS_ENDPOINT or _discovered.get("jwks_uri", "")
    OIDC_OP_LOGOUT_ENDPOINT = OIDC_OP_LOGOUT_ENDPOINT or _discovered.get("end_session_endpoint", "")

OIDC_OP_LOGOUT_URL_METHOD = "basicbar_auth.oidc.provider_logout_url"

# Claim mapping (provider-agnostic; defaults are standard OIDC claim names).
OIDC_CLAIM_USERNAME = os.environ.get("OIDC_CLAIM_USERNAME", "preferred_username")
OIDC_CLAIM_EMAIL = os.environ.get("OIDC_CLAIM_EMAIL", "email")
OIDC_CLAIM_FIRST_NAME = os.environ.get("OIDC_CLAIM_FIRST_NAME", "given_name")
OIDC_CLAIM_LAST_NAME = os.environ.get("OIDC_CLAIM_LAST_NAME", "family_name")
# Group/role claim, and the group that grants Django admin (empty = disabled,
# admins then managed manually via Django admin / a createsuperuser account).
OIDC_GROUPS_CLAIM = os.environ.get("OIDC_GROUPS_CLAIM", "groups")
OIDC_ADMIN_GROUP = os.environ.get("OIDC_ADMIN_GROUP", "")

# Where to send the browser after login/logout (the SPA).
LOGIN_REDIRECT_URL = os.environ.get("OIDC_LOGIN_REDIRECT_URL", "http://localhost:5173/")
LOGOUT_REDIRECT_URL = os.environ.get("OIDC_LOGOUT_REDIRECT_URL", "http://localhost:5173/")
# On a failed/declined login (incl. a silent prompt=none attempt with no IdP
# session) send the browser back to the SPA with a marker, so the landing page
# shows instead of erroring and does not retry the silent login.
LOGIN_REDIRECT_URL_FAILURE = LOGIN_REDIRECT_URL.rstrip("/") + "/?sso=failed"
