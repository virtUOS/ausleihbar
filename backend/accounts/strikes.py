# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Strike issuance and the resulting account suspension (concept §7.3)."""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Strike, StrikeSetting


def active_strike_count(user, now=None):
    now = now or timezone.now()
    return user.strikes.filter(expires_at__gt=now).count()


def recompute_block(user, now=None):
    """Apply the strike policy to ``user`` after a strike change.

    Suspends the account to the step matching the current active-strike count.
    Never lifts an existing block early (a block runs for its fixed period; an
    admin can unblock manually). Returns True if a block was applied/extended.
    """
    now = now or timezone.now()
    setting = StrikeSetting.load()
    active = active_strike_count(user, now)
    applicable = [t for t in setting.thresholds if active >= int(t.get("count", 0))]
    if not applicable:
        return False

    step = max(applicable, key=lambda t: int(t.get("count", 0)))
    block_days = int(step.get("block_days", 0) or 0)
    changed = False
    if block_days == 0:
        if not user.blocked_permanently:
            user.blocked_permanently = True
            changed = True
    else:
        until = now + timedelta(days=block_days)
        if user.blocked_until is None or until > user.blocked_until:
            user.blocked_until = until
            changed = True
    if changed:
        user.save(update_fields=["blocked_until", "blocked_permanently"])
    return changed


def issue_strike(user, reason, issued_by, booking=None):
    """Create a strike, re-evaluate the suspension, and notify the user.

    ``booking`` ties the strike to the reservation it was issued over, so the
    borrower can see which booking earned it.
    """
    setting = StrikeSetting.load()
    now = timezone.now()
    strike = Strike.objects.create(
        user=user,
        reason=reason,
        issued_by=issued_by,
        booking=booking,
        expires_at=now + timedelta(days=setting.strike_expiry_days),
    )
    recompute_block(user, now)
    _notify(user, strike)
    return strike


def _notify(user, strike):
    if not user.email:
        return
    # Send in the borrower's shop language, or the institution default (#25).
    lang = getattr(user, "language", "") or settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    with translation.override(lang):
        if user.blocked_permanently:
            block_line = _("Your account is now blocked indefinitely.")
        elif user.blocked_until:
            block_line = _("Your account is blocked until %(date)s.") % {
                "date": f"{user.blocked_until:%Y-%m-%d}"
            }
        else:
            block_line = _("No borrowing block applies yet.")
        message = _(
            "A strike was added to your account.\n\nReason: %(reason)s\n\n"
        ) % {"reason": strike.reason} + block_line
        send_mail(
            subject=_("You received a strike"),
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
