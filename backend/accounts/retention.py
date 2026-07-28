# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Data retention: anonymize long-inactive accounts (GDPR).

Accounts that have had no activity for the configured window *and* have no open
lending process are anonymized: every piece of personal data is scrubbed and
the record is kept only as a neutral placeholder ("Gelöschter Nutzer"), so the
device/booking history it is referenced from stays intact.

Anonymization is irreversible and done in place — ``lending.Booking.borrower``
is ``PROTECT``, so the row cannot simply be deleted without losing history.

Admins (``is_staff`` / ``is_superuser``) are never touched. Inactive lenders
(pool members) *are* anonymized; their memberships are removed in the process.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import DateTimeField
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger(__name__)

# Booking states that mean a lending process is still open (not finished).
OPEN_BOOKING_STATUSES = ("cart", "pending", "confirmed", "handed_out")

ANON_FIRST_NAME = "Gelöschter"
ANON_LAST_NAME = "Nutzer"


def inactive_candidates(retention_days):
    """Users eligible for anonymization right now (a queryset).

    Eligible = not an admin, not already anonymized, last activity (last login,
    or — if never recorded — the join date) older than the window, and no open
    lending process.
    """
    User = get_user_model()
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    return (
        User.objects.filter(is_staff=False, is_superuser=False, anonymized_at__isnull=True)
        .annotate(
            last_seen=Coalesce("last_login", "date_joined", output_field=DateTimeField())
        )
        .filter(last_seen__lt=cutoff)
        .exclude(bookings__status__in=OPEN_BOOKING_STATUSES)
        .distinct()
    )


@transaction.atomic
def anonymize_user(user):
    """Scrub all personal data from ``user`` in place, keeping it as a
    placeholder so referenced history survives."""
    from lending.models import BookingReminder

    # Reminder e-mails are stored as plain strings on the booking's reminders.
    BookingReminder.objects.filter(booking__borrower=user).update(recipient="")

    # Drop role/access links — a deleted person keeps no lender or group access.
    user.pool_memberships.all().delete()
    user.access_groups.clear()

    user.username = f"deleted-{user.pk}"
    user.first_name = ANON_FIRST_NAME
    user.last_name = ANON_LAST_NAME
    user.email = ""
    user.subject = None
    user.claims = {}
    user.language = ""
    user.verified_at = None
    user.blocked_until = None
    user.blocked_permanently = False
    user.is_active = False
    user.set_unusable_password()
    user.anonymized_at = timezone.now()
    user.save()
    return user


def run(retention_days=None, *, dry_run=False, force=False):
    """Anonymize all currently-eligible accounts.

    Uses :class:`accounts.models.RetentionSetting` for the window and the on/off
    switch; ``retention_days`` overrides the window and ``force`` ignores the
    switch. Returns a summary dict.
    """
    from .models import RetentionSetting

    setting = RetentionSetting.load()
    if retention_days is None:
        retention_days = setting.retention_days
    if not setting.enabled and not force:
        return {"enabled": False, "anonymized": 0, "candidates": 0, "dry_run": dry_run}

    candidates = list(inactive_candidates(retention_days))
    if not dry_run:
        for user in candidates:
            anonymize_user(user)
            logger.info("Anonymized inactive account #%s", user.pk)
    return {
        "enabled": True,
        "retention_days": retention_days,
        "candidates": len(candidates),
        "anonymized": 0 if dry_run else len(candidates),
        "dry_run": dry_run,
    }
