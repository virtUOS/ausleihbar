# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Scheduled notifications run by ``desks_daily``: the daily summary and the
series extension reminders. Both are idempotent (markers on the profile /
series), so the command may run any number of times per day."""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import hours, notify
from .models import DeskProfile, Reservation, Series

logger = logging.getLogger(__name__)

REMINDER_DAYS = (28, 7)


def send_daily_summaries(now=None) -> int:
    """One mail per person with reservations left today, from
    ``DESKS_SUMMARY_HOUR`` on and at most once per local day. Returns the
    number of people handled."""
    now = now or timezone.now()
    local = timezone.localtime(now, hours.TZ)
    if local.hour < settings.DESKS_SUMMARY_HOUR:
        return 0
    today = local.date()
    rows = (
        Reservation.objects.filter(
            status=Reservation.Status.ACTIVE,
            holder__isnull=False,
            holder__is_active=True,
            place__room__floor__pool__desk_settings__enabled=True,
            period__startswith__lt=hours.local_dt(today + timedelta(days=1), 0),
            period__endswith__gt=max(now, hours.local_dt(today, 0)),
        )
        .select_related("holder", "place__room__floor")
        .order_by("period", "pk")
    )
    by_user: dict = {}
    for res in rows:
        by_user.setdefault(res.holder_id, []).append(res)
    handled = 0
    for user_id, reservations in by_user.items():
        user = reservations[0].holder
        profile, _created = DeskProfile.objects.get_or_create(user=user)
        if profile.last_summary_date == today:
            continue
        # Mark first: a crash after sending must not mail the person twice.
        DeskProfile.objects.filter(pk=profile.pk).update(last_summary_date=today)
        try:
            notify.notify(user, notify.DAILY_SUMMARY, {"reservations": reservations, "day": today})
        except Exception:
            logger.exception("Daily summary failed for user %s", user_id)
        handled += 1
    return handled


def send_series_reminders(now=None) -> int:
    """Remind the holder 28 and 7 days before ``valid_until`` (once each; a
    run after the 7-day mark also settles the 28-day one). Returns the number
    of mails."""
    today = timezone.localtime(now or timezone.now(), hours.TZ).date()
    due = Series.objects.filter(
        cancelled_at__isnull=True,
        holder__isnull=False,
        holder__is_active=True,
        valid_until__gte=today,
        valid_until__lte=today + timedelta(days=REMINDER_DAYS[0]),
    ).select_related("holder", "place__room__floor")
    sent = 0
    for series in due:
        days = (series.valid_until - today).days
        if days <= REMINDER_DAYS[1]:
            marker, fields = "reminder_7_sent", {"reminder_7_sent": True, "reminder_28_sent": True}
        else:
            marker, fields = "reminder_28_sent", {"reminder_28_sent": True}
        # The conditional update is the claim: concurrent runs mail once.
        if not Series.objects.filter(pk=series.pk, **{marker: False}).update(**fields):
            continue
        try:
            notify.notify(
                series.holder, notify.SERIES_EXTENSION_DUE, {"series": series, "days": days}
            )
        except Exception:
            logger.exception("Series reminder failed for series %s", series.pk)
        sent += 1
    return sent
