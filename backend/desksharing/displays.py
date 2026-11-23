# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Device side of the door displays: secret auth, pairing codes, rate limit.

The secret is a random hex string the device generates; only its sha256 is
stored and compared (lookup by ``secret_hash``). It is never logged.
"""
import hashlib
import re
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import connection, transaction

from .models import Display

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
CODE_TTL = timedelta(minutes=10)
MAX_PENDING = 50
STALE_AFTER = timedelta(days=1)
EVENT_LIMIT = 30
EVENT_WINDOW = 60  # seconds
PANELS = {choice for choice, _ in Display.Panel.choices}

_DIGITS_RE = re.compile(r"[0-9]{1,6}")
_SECRET_RE = re.compile(r"[0-9a-fA-F]{64,512}")
_LOCK_KEY = 727_001  # pg advisory lock serialising pending-row handling


def valid_secret(secret: str) -> bool:
    return bool(secret) and _SECRET_RE.fullmatch(secret) is not None


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.strip().lower().encode()).hexdigest()


def bearer_secret(request) -> str:
    """The raw secret of ``Authorization: Bearer <secret>`` or ``""``."""
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def _telemetry(request) -> dict:
    fields = {}
    raw = request.headers.get("X-Battery-mV", "")
    if _DIGITS_RE.fullmatch(raw):  # ASCII only: str.isdigit() accepts "²"
        fields["battery_mv"] = int(raw)
    firmware = "".join(
        ch for ch in request.headers.get("X-Firmware", "")[:40]
        if ch.isascii() and ch.isprintable()
    )
    if firmware:
        fields["firmware"] = firmware
    return fields


def find(request) -> Display | None:
    """The display of a valid secret without writing anything."""
    secret = bearer_secret(request)
    if not valid_secret(secret):
        return None
    return Display.objects.filter(secret_hash=hash_secret(secret)).first()


def authenticate(request, display: Display | None = None) -> Display | None:
    """The display of a valid secret (telemetry saved), else ``None``."""
    from django.utils import timezone

    display = display or find(request)
    if display is None:
        return None
    fields = {"last_seen_at": timezone.now(), **_telemetry(request)}
    Display.objects.filter(pk=display.pk).update(**fields)
    for name, value in fields.items():
        setattr(display, name, value)
    return display


def _lock() -> None:
    """Transaction-scoped lock: pending creation, rotation and cleanup are
    serialised so a code is never handed out twice and the cap holds."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK_KEY])


def _pending(now):
    return Display.objects.filter(room__isnull=True, pairing_expires_at__gt=now)


def _new_code(now) -> str:
    taken = set(_pending(now).values_list("pairing_code", flat=True))
    for _ in range(100):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in taken:
            return code
    raise RuntimeError("no free pairing code")  # pragma: no cover


def _cleanup(now) -> None:
    cutoff = now - STALE_AFTER
    Display.objects.filter(room__isnull=True, last_seen_at__lt=cutoff).delete()
    Display.objects.filter(
        room__isnull=True, last_seen_at__isnull=True, created_at__lt=cutoff
    ).delete()


def has_live_code(display: Display, now) -> bool:
    return bool(
        display.pairing_code and display.pairing_expires_at and display.pairing_expires_at > now
    )


def ensure_code(display: Display, now) -> Display | None:
    """Give an unpaired display a valid code (rotating an expired one).
    ``None`` when a new code is needed but ``MAX_PENDING`` codes are live."""
    if has_live_code(display, now):
        return display
    with transaction.atomic():
        _lock()
        fresh = Display.objects.select_for_update().get(pk=display.pk)
        if not (fresh.pairing_code and fresh.pairing_expires_at
                and fresh.pairing_expires_at > now):
            if _pending(now).count() >= MAX_PENDING:
                return None
            fresh.pairing_code = _new_code(now)
            fresh.pairing_expires_at = now + CODE_TTL
            fresh.save(update_fields=["pairing_code", "pairing_expires_at", "updated_at"])
        display.pairing_code = fresh.pairing_code
        display.pairing_expires_at = fresh.pairing_expires_at
    return display


def ensure_pending(secret: str, panel: str, now) -> Display | None:
    """Create the unpaired row of an unknown secret (``None`` = cap reached)."""
    if not valid_secret(secret) or panel not in PANELS:
        return None
    digest = hash_secret(secret)
    with transaction.atomic():
        _lock()
        _cleanup(now)
        existing = Display.objects.filter(secret_hash=digest).first()
        if existing is not None:
            return existing
        if _pending(now).count() >= MAX_PENDING:
            return None
        return Display.objects.create(
            secret_hash=digest, panel=panel, last_seen_at=now,
            pairing_code=_new_code(now), pairing_expires_at=now + CODE_TTL,
        )


def _count(store, prefix: str, ident, now, window: int) -> int:
    """Bump and return the counter of ``ident`` in the current fixed window
    (approximate on caches without atomic ``incr``)."""
    key = f"{prefix}:{ident}:{int(now.timestamp()) // window}"
    store.add(key, 0, window * 2)
    try:
        return store.incr(key)
    except ValueError:  # expired between add and incr
        store.set(key, 1, window * 2)
        return 1


def allow_event(display: Display, now) -> bool:
    """At most ``EVENT_LIMIT`` button events per ``EVENT_WINDOW`` seconds."""
    return _count(cache, "door-event", display.pk, now, EVENT_WINDOW) <= EVENT_LIMIT


FRAME_LIMIT = 60
FRAME_WINDOW = 60  # seconds


def allow_frame(display: Display, now) -> bool:
    """At most ``FRAME_LIMIT`` frame requests of a paired display per
    ``FRAME_WINDOW`` seconds (a healthy sign asks every few minutes)."""
    return _count(cache, "door-frame", display.pk, now, FRAME_WINDOW) <= FRAME_LIMIT


PAIRING_LIMIT = 12
PAIRING_WINDOW = 60  # seconds
PENDING_PER_IP = 10
PENDING_IP_WINDOW = int(CODE_TTL.total_seconds())


def _throttle():
    from django.core.cache import caches

    return caches["throttle"]


def allow_pairing_request(request, now) -> bool:
    """Per-client-IP limit for frame requests of unknown / unpaired devices."""
    from common.net import client_ip

    count = _count(_throttle(), "door-pairing", client_ip(request), now, PAIRING_WINDOW)
    return count <= PAIRING_LIMIT


def allow_new_pending(request, now) -> bool:
    """At most ``PENDING_PER_IP`` new pending codes (new displays or rotated
    expired codes) per client IP and code lifetime, so one address cannot
    take all ``MAX_PENDING`` slots. Kept in the throttle cache only (nothing
    stored in the database)."""
    from common.net import client_ip

    count = _count(_throttle(), "door-pending", client_ip(request), now, PENDING_IP_WINDOW)
    return count <= PENDING_PER_IP
