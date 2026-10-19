# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Strike issuance and the resulting account suspension (concept §7.3)."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import Strike, StrikeSetting


def active_strike_count(user, now=None):
    now = now or timezone.now()
    return user.strikes.filter(expires_at__gt=now).count()


def _steps(setting):
    """The policy's escalation steps as ``(count, block_days)``, ascending."""
    return sorted(
        (int(t.get("count", 0)), int(t.get("block_days", 0) or 0))
        for t in setting.thresholds
    )


def block_for_count(count, setting):
    """The threshold step reached with ``count`` active strikes.

    ``None`` if no step applies; else ``(permanent, block_days)`` of the
    highest reached step (``block_days`` 0 means permanent).
    """
    reached = [step for step in _steps(setting) if count >= step[0]]
    if not reached:
        return None
    block_days = reached[-1][1]
    return (block_days == 0, block_days)


def next_step(count, setting):
    """The next step above ``count`` active strikes as ``{"count",
    "block_days"}`` (``block_days`` 0 = permanent), or ``None``."""
    for step_count, block_days in _steps(setting):
        if step_count > count:
            return {"count": step_count, "block_days": block_days}
    return None


def _current_block(user, now):
    """The user's block as ``(blocked_permanently, blocked_until)``; a block
    that has already run out counts as none."""
    until = user.blocked_until if user.blocked_until and user.blocked_until > now else None
    return bool(user.blocked_permanently), until


def recompute_block(user, now=None):
    """Apply the strike policy to ``user`` after a strike change.

    Suspends the account to the step matching the current active-strike count.
    Never lifts an existing block early (a block runs for its fixed period; an
    admin can unblock manually). Returns True if a block was applied/extended.
    """
    now = now or timezone.now()
    block = block_for_count(active_strike_count(user, now), StrikeSetting.load())
    if block is None:
        return False

    permanent, block_days = block
    changed = False
    if permanent:
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


def projected_block(user, now=None):
    """What issuing one more strike to ``user`` would mean — nothing saved.

    Mirrors :func:`recompute_block` (never earlier than an existing block):
    ``{"active_after", "blocked_permanently", "blocked_until"}``.
    """
    now = now or timezone.now()
    active_after = active_strike_count(user, now) + 1
    permanent, until = _current_block(user, now)
    block = block_for_count(active_after, StrikeSetting.load())
    if block is not None:
        step_permanent, block_days = block
        if step_permanent:
            permanent = True
        else:
            step_until = now + timedelta(days=block_days)
            if until is None or step_until > until:
                until = step_until
    return {
        "active_after": active_after,
        "blocked_permanently": permanent,
        "blocked_until": until,
    }


def issue_strike(user, reason, issued_by, booking=None, note=""):
    """Create a strike, re-evaluate the suspension, and notify the user.

    ``booking`` ties the strike to the reservation it was issued over, so the
    borrower can see which booking earned it. ``note`` is the lending team's
    optional personal note — it goes into the mail only (#139).
    """
    setting = StrikeSetting.load()
    now = timezone.now()
    strike = Strike.objects.create(
        user=user,
        reason=reason,
        note=note,
        issued_by=issued_by,
        booking=booking,
        expires_at=now + timedelta(days=setting.strike_expiry_days),
    )
    recompute_block(user, now)
    _notify(user, strike, now)
    return strike


def mail_language(user):
    """The borrower's shop language, or the institution default (#25)."""
    return getattr(user, "language", "") or settings.MODELTRANSLATION_DEFAULT_LANGUAGE


def _booking_pool(booking):
    """The pool a booking belongs to (#26), falling back to its items' pool
    for legacy reservations without one."""
    if booking.resource_pool_id:
        return booking.resource_pool
    item = booking.items.select_related("resource__resource_pool").first()
    return item.resource.resource_pool if item else None


def strike_mail(
    user, *, reason, note, booking, expires_at, active_count, blocked_until,
    blocked_permanently,
):
    """Subject and text (without the common frame) of the strike mail.

    Used for the real mail (values after saving) and the dialog's preview
    (projected values), so both read the same. Call it under the user's
    language.
    """
    from lending.notifications import _label, _pool_block, format_date

    pool = _booking_pool(booking) if booking else None
    if booking:
        code = _label(booking)
        subject = _("Strike for your booking %(code)s") % {"code": code}
    else:
        subject = _("You received a strike")
    if pool:
        intro = _(
            "the lending team of %(pool)s gave you a strike for your "
            "booking %(code)s."
        ) % {"pool": pool.name, "code": code}
    else:
        intro = _("a strike was added to your account.")

    parts = [intro, _("Reason: %(reason)s") % {"reason": reason}]
    if note:
        parts.append(_("A note from the lending team:\n%(msg)s") % {"msg": note})
    parts.append(
        ngettext(
            "This strike expires on %(date)s. You currently have %(count)d "
            "active strike.",
            "This strike expires on %(date)s. You currently have %(count)d "
            "active strikes.",
            active_count,
        ) % {"date": format_date(expires_at), "count": active_count}
    )

    if blocked_permanently:
        block_line = _("Your account is now blocked indefinitely.")
    elif blocked_until:
        block_line = _("Your account is blocked until %(date)s.") % {
            "date": format_date(blocked_until, with_time=True)
        }
    else:
        step = next_step(active_count, StrikeSetting.load())
        if step is None:
            block_line = _("No borrowing block applies yet.")
        elif step["block_days"]:
            block_line = ngettext(
                "From %(count)d active strikes, your account will be blocked "
                "for %(days)d day.",
                "From %(count)d active strikes, your account will be blocked "
                "for %(days)d days.",
                step["block_days"],
            ) % {"count": step["count"], "days": step["block_days"]}
        else:
            block_line = _(
                "From %(count)d active strikes, your account will be blocked "
                "permanently."
            ) % {"count": step["count"]}
    parts.append(block_line)

    if pool:
        parts.append(_pool_block(pool, full=False, pickup=False))
    return subject, "\n\n".join(parts)


def _notify(user, strike, now):
    """Mail the user about the strike, in the same frame as the booking mails
    (greeting, bookings link, sign-off) and through the same fail-soft send."""
    from lending.notifications import send_user_mail

    if not user.email:
        return
    permanent, until = _current_block(user, now)
    with translation.override(mail_language(user)):
        subject, text = strike_mail(
            user,
            reason=strike.reason,
            note=strike.note,
            booking=strike.booking,
            expires_at=strike.expires_at,
            active_count=active_strike_count(user, now),
            blocked_until=until,
            blocked_permanently=permanent,
        )
        send_user_mail(user, subject, text)
