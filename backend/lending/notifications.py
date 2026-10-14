# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Email notifications for booking lifecycle events (Roadmap area G).

Plain-text mails are built here and sent fail-soft: a missing recipient or a
mail-server outage is logged but never breaks the booking flow.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from catalog.models import NotificationSetting, Product
from catalog.richtext import html_to_text

from .ics import build_ics
from .qr import make_qr_png, pickup_qr_url

logger = logging.getLogger(__name__)


def _lang(booking):
    """The borrower's preferred email language, or the institution default."""
    return (
        getattr(booking.borrower, "language", "")
        or settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    )


def _default_lang():
    """Language for mails to a pool's contact address or its lenders (#83):
    the instance's default content language."""
    return settings.MODELTRANSLATION_DEFAULT_LANGUAGE


# Weekday keys in display order, matching ResourcePool.opening_hours; the
# labels are translated when rendered ("Mo" … "So" in German).
_WEEKDAYS = [
    ("mon", gettext_noop("Mon")), ("tue", gettext_noop("Tue")),
    ("wed", gettext_noop("Wed")), ("thu", gettext_noop("Thu")),
    ("fri", gettext_noop("Fri")), ("sat", gettext_noop("Sat")),
    ("sun", gettext_noop("Sun")),
]

# Django date formats per mail language (#82): "Fr., 01.05.2099" /
# "Fri 01 May 2099", with ", 14:00" appended for times.
_DATE_FORMATS = {"de": "D., d.m.Y"}
_DEFAULT_DATE_FORMAT = "D d M Y"


def format_date(value, with_time=False):
    """A date or datetime, localised for the active language.

    Aware datetimes are shown in local time. Shared with other mail senders
    (e.g. the strike mail) so every mail formats dates the same way.
    """
    lang = (translation.get_language() or "").split("-")[0]
    fmt = _DATE_FORMATS.get(lang, _DEFAULT_DATE_FORMAT)
    if with_time:
        fmt += ", H:i"
    if hasattr(value, "tzinfo") and timezone.is_aware(value):
        value = timezone.localtime(value)
    return formats.date_format(value, fmt)


def _format_bounds(lower, upper, lending_type):
    """(start, end) strings for a period's bounds.

    Day bookings show inclusive calendar dates — the stored upper bound is the
    exclusive following midnight, so the last booked day is one tick earlier.
    Hourly bookings show date and time.
    """
    if lending_type == Product.LendingType.DAYS:
        start = format_date(lower) if lower else "?"
        if not upper:
            return start, _("open end")
        return start, format_date(upper - timedelta(microseconds=1))
    start = format_date(lower, with_time=True) if lower else "?"
    end = format_date(upper, with_time=True) if upper else _("open end")
    return start, end


def _format_period(item):
    """(start, end) strings for an item's current period (see _format_bounds)."""
    return _format_bounds(
        item.period.lower, item.period.upper, item.resource.product.lending_type
    )


def _bounds_str(lower, upper, lending_type):
    """Bounds as one line: ``start → end``, or a single value when they match."""
    start, end = _format_bounds(lower, upper, lending_type)
    return start if start == end else f"{start} → {end}"


def _period_str(item):
    """An item's current period as one line (``start → end`` or a single value)."""
    return _bounds_str(
        item.period.lower, item.period.upper, item.resource.product.lending_type
    )


def _opening_hours_lines(opening_hours):
    lines = []
    for key, label in _WEEKDAYS:
        ranges = (opening_hours or {}).get(key) or []
        if ranges:
            spans = ", ".join(f"{a}–{b}" for a, b in ranges)
            lines.append(f"{_(label)}: {spans}")
    return lines


def _pool_block(pool, items=(), *, full=True, pickup=True):
    """One readable, plain-text block per pool.

    Each sub-section (items, address, opening hours, directions, contact,
    pool note) is separated by a blank line and consistently indented, so
    the mail stays legible in any client.

    ``full=False`` gives the short variant (address and contact, no opening
    hours or directions) for mails that ask the borrower to get in touch.
    ``pickup=False`` heads the block with just the pool's name instead of
    "Pickup at …" (e.g. for overdue returns).
    """
    header = _("Pickup at %(pool)s") % {"pool": pool.name} if pickup else pool.name
    if pool.room:
        header += f" · {pool.room}"
    lines = [header]
    if items:
        lines.append("")
    for item in items:
        lines.append(
            f"  • {item.resource.product.title} ({item.resource.inventory_number})"
        )
        lines.append(f"      {_period_str(item)}")

    if pool.address:
        lines += ["", "  " + _("Address:")]
        lines += [
            f"    {line}" for line in pool.address.splitlines() if line.strip()
        ]

    if full:
        hours = _opening_hours_lines(pool.opening_hours)
        if hours:
            lines += ["", "  " + _("Opening hours:")]
            lines += [f"    {h}" for h in hours]

        # An emptied rich-text editor can leave a value like "<p></p>" that is
        # truthy but has no visible content (M1) — check the rendered text,
        # not the raw HTML, before emitting the block.
        directions_text = html_to_text(pool.directions)
        if directions_text:
            lines += ["", "  " + _("Directions:")]
            lines += [
                f"    {line}" for line in directions_text.splitlines() if line.strip()
            ]

    contact = " / ".join(x for x in [pool.phone, pool.email] if x)
    if contact:
        lines += ["", "  " + _("Contact: %(contact)s") % {"contact": contact}]

    # Optional per-pool note (active language), e.g. eligibility hints.
    note = (getattr(pool, "email_note", "") or "").strip()
    if note:
        lines += [""] + [f"  {line}" for line in note.splitlines()]

    return "\n".join(lines)


def _pool_blocks(pools, **kwargs):
    """``_pool_block`` (without items) for each pool, as mail lines."""
    lines = []
    for pool in pools:
        lines += ["", _pool_block(pool, **kwargs)]
    return lines


def _pools_of(items):
    """Ordered, unique resource pools of the given booking items."""
    seen = {}
    for item in items:
        pool = item.resource.resource_pool
        seen.setdefault(pool.id, pool)
    return list(seen.values())


def _group_by_pool(booking):
    """Group a booking's items by their resource pool, preserving order."""
    groups = {}
    for item in booking.items.all():
        pool = item.resource.resource_pool
        groups.setdefault(pool.id, (pool, []))[1].append(item)
    return list(groups.values())


def _name(user):
    return user.get_full_name() or user.username or _("there")


def _label(booking):
    return booking.code or f"#{booking.id}"


def _greeting(user):
    return _("Hi %(name)s,") % {"name": _name(user)}


def _bookings_line():
    shop = settings.SHOP_BASE_URL.rstrip("/")
    return _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}


SIGNATURE = "— Ausleihbar"


def _note_lines(note):
    """An optional admin note as mail lines: a blank line, then the note."""
    return ["", note] if note else []


def send_user_mail(user, subject, text, lead=""):
    """Send ``text`` to ``user`` in the common borrower-mail frame: greeting,
    an optional admin-configured ``lead`` paragraph (e.g. the reason for a
    closure), the text, the bookings link and the sign-off. Notes that belong
    inside the text are placed there by the caller (:func:`_note_lines`).
    Call it under the user's language (fail-soft)."""
    parts = [_greeting(user), lead, text, _bookings_line(), SIGNATURE]
    body = "\n\n".join(p for p in parts if p)
    return _send(subject, f"{body}\n", user.email)


def _body(booking, *, message=""):
    """Per-part body block for a *confirmed* booking (#26).

    Just the intro, its pool block(s), the optional lender note, and the
    pickup line — no greeting, borrower note, bookings link or signature, so
    several of these can be combined into one mail (:func:`_confirmation_body`)
    without repeating them (the borrower's note is the same on every part of
    a split order, so it's shown once there, not per part). A single
    confirmed booking is still the common case, so
    :func:`send_confirmation_email` wraps exactly one of these the same way
    it always has.
    """
    label = _label(booking)
    groups = _group_by_pool(booking)
    if groups and all(_opening_hours_lines(pool.opening_hours) for pool, _i in groups):
        intro = _(
            "your booking %(code)s is confirmed. Please pick up your "
            "item(s) during the opening hours below."
        )
    else:
        intro = _(
            "your booking %(code)s is confirmed. Please pick up your "
            "item(s) during the pool's opening hours."
        )
    blocks = [_pool_block(pool, items) for pool, items in groups]
    body = intro % {"code": label} + "\n\n" + "\n\n".join(blocks)
    if message:
        body += "\n\n" + _("A note from the lending team:\n%(msg)s") % {"msg": message}
    body += "\n\n" + _(
        "At pickup, show your booking number %(code)s — the attached QR code "
        "can be scanned by the lending desk. The attached calendar entry "
        "(.ics) adds the lending period to your calendar."
    ) % {"code": label}
    return body


def _send(subject, body, recipient):
    if not recipient:
        logger.info("Booking notification skipped: recipient has no email address.")
        return False
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
        return True
    except Exception:  # pragma: no cover - a mail outage must not break booking
        logger.exception("Failed to send booking notification email")
        return False


def _send_attached(subject, body, recipient, attachments):
    """Send a plain-text mail with attachments (fail-soft).

    ``attachments`` is a list of ``(filename, content, mimetype)`` tuples.
    """
    if not recipient:
        logger.info("Booking notification skipped: recipient has no email address.")
        return False
    try:
        message = EmailMessage(
            subject, body, settings.DEFAULT_FROM_EMAIL, [recipient]
        )
        for filename, content, mimetype in attachments:
            message.attach(filename, content, mimetype)
        message.send()
        return True
    except Exception:  # pragma: no cover - a mail outage must not break booking
        logger.exception("Failed to send booking notification email")
        return False


def _reservation_received_body(bookings, *, intro_override="", footer=""):
    """Body for :func:`send_reservation_email`: one or several reservations.

    Shares its building blocks with the confirmation mail (greeting,
    per-pool blocks, borrower note, bookings link, footer), but lists one
    "Booking number" line and its pool block(s) per booking, since a
    multi-pool cart submit (#26) produces one booking per pool.
    """
    first = bookings[0]
    intro = intro_override or _(
        "we received your reservation. It is on hold and the "
        "lending team will confirm it shortly."
    )
    body = f"{_greeting(first.borrower)}\n\n{intro}"
    if len(bookings) > 1:
        body += "\n\n" + _("Each pool confirms its part of your order separately.")
    for booking in bookings:
        body += "\n\n" + _("Booking number: %(code)s") % {"code": _label(booking)}
        blocks = [_pool_block(pool, items) for pool, items in _group_by_pool(booking)]
        body += "\n\n" + "\n\n".join(blocks)
    if first.note:
        body += "\n\n" + _("Your message: %(note)s") % {"note": first.note}
    body += f"\n\n{_bookings_line()}"
    if footer:
        body += f"\n\n{footer}"
    return f"{body}\n\n{SIGNATURE}\n"


def send_reservation_email(bookings):
    """Notify the borrower that their reservation(s) were submitted.

    Accepts a single ``Booking`` or a list of them: submitting a multi-pool
    cart (#26) splits it into one reservation per pool, and the borrower gets
    one combined mail listing each reservation number and its pickup details.

    Admins can customise the opening and closing text per language via
    ``NotificationSetting`` (issue #30); the structured details stay intact.
    """
    from .models import Booking

    if isinstance(bookings, Booking):
        bookings = [bookings]
    first = bookings[0]
    setting = NotificationSetting.load()
    with translation.override(_lang(first)):
        # Attribute access resolves to the active language's column.
        intro = (setting.reservation_intro or "").strip()
        footer = (setting.reservation_footer or "").strip()
        codes = [_label(b) for b in bookings]
        if len(bookings) == 1:
            subject = _(
                "Ausleihbar reservation %(code)s received (awaiting confirmation)"
            ) % {"code": codes[0]}
        else:
            subject = _(
                "Ausleihbar order received: %(codes)s (awaiting confirmation)"
            ) % {"codes": ", ".join(codes)}
        body = _reservation_received_body(
            bookings, intro_override=intro, footer=footer
        )
        return _send(subject, body, first.borrower.email)


def _confirmation_body(parts, open_parts, message):
    """Full body of a confirmation mail: one or several confirmed parts,
    combined behind a single greeting/bookings-link/signature (#26).

    When ``open_parts`` is non-empty, the mail is a partial confirmation: a
    prominent notice up front, then one line per still-open part, before the
    confirmed part(s)' own blocks.
    """
    first = parts[0]
    body = _greeting(first.borrower)
    if open_parts:
        body += "\n\n" + _(
            "PARTIAL CONFIRMATION — only part of your order is confirmed so far."
        )
        for part in open_parts:
            pool_name = part.resource_pool.name if part.resource_pool else ""
            body += "\n" + _("Still awaiting confirmation: %(pool)s (%(code)s)") % {
                "pool": pool_name, "code": _label(part),
            }
    single = len(parts) == 1
    for part in parts:
        part_message = message if (single and message) else part.confirmation_message
        body += "\n\n" + _body(part, message=part_message)
    # The borrower's note is the same on every part of a split order (#26) —
    # show it once here rather than repeating it per part.
    if first.note:
        body += "\n\n" + _("Your message: %(note)s") % {"note": first.note}
    body += f"\n\n{_bookings_line()}"
    return f"{body}\n\n{SIGNATURE}\n"


def send_confirmation_email(parts, open_parts=(), message=""):
    """Notify the borrower their order (or part of it) was confirmed (#26).

    ``parts`` is a single confirmed ``Booking`` or a list of them — an order
    is confirmed in one combined mail, either because every part is done or
    because it's time to flush the still-held parts. When ``open_parts`` is
    given, the mail is clearly marked as a partial confirmation and names
    those still-open parts.

    Attaches a QR code per confirmed part so the lending desk can scan the
    pickup from the borrower's phone (concept §6.2), and an iCalendar entry
    of its pickup period(s) for the borrower's calendar (concept §4.6). A
    per-part lender note (issue #29) is taken from ``part.confirmation_message``;
    ``message`` is a legacy kwarg honoured only for a single-booking call.
    """
    from .models import Booking

    if isinstance(parts, Booking):
        parts = [parts]
    first = parts[0]
    codes = ", ".join(_label(p) for p in parts)

    with translation.override(_lang(first)):
        # Built under the borrower's language: the .ics text is translated.
        attachments = []
        for part in parts:
            label = _label(part)
            attachments.append(
                (f"pickup-{label}.png", make_qr_png(pickup_qr_url(part)), "image/png")
            )
            attachments.append(
                (f"booking-{label}.ics", build_ics(part), "text/calendar")
            )
        if open_parts:
            subject = _("Ausleihbar — partial confirmation: %(codes)s") % {
                "codes": codes
            }
        elif len(parts) > 1:
            # A full confirmation that completes several parts at once (M6) —
            # e.g. the held-until-send-time flush confirms two pools together.
            subject = _(
                "Ausleihbar bookings %(codes)s confirmed — pickup details"
            ) % {"codes": codes}
        else:
            subject = _(
                "Ausleihbar booking %(code)s confirmed — pickup details"
            ) % {"code": codes}
        return _send_attached(
            subject,
            _confirmation_body(parts, open_parts, message),
            first.borrower.email,
            attachments,
        )


def _item_line(item):
    return (
        f"  - {item.resource.product.title} ({item.resource.inventory_number}): "
        f"{_period_str(item)}"
    )


def _contact_text(intro, items, pools, contact_line, note=""):
    """Body text of a "please get in touch" mail (defect, missing item,
    closure cancellation): intro, the affected items, an optional admin
    ``note``, then the contact line and a short block per pool with address
    and contact."""
    lines = [intro, ""]
    lines += [_item_line(i) for i in items]
    lines += _note_lines(note)
    lines += ["", contact_line]
    lines += _pool_blocks(pools, full=False, pickup=False)
    return "\n".join(lines)


def send_defect_notice(booking, items):
    """Tell a borrower a reserved item is defective and could not be moved."""
    setting = NotificationSetting.load()
    pools = _pools_of(items)
    with translation.override(_lang(booking)):
        intro = _(
            "an item reserved on your booking %(code)s has become "
            "unavailable (defect) and we could not move it to another unit:"
        ) % {"code": _label(booking)}
        text = _contact_text(
            intro, items, pools,
            _("Please contact the lending team to arrange an alternative:"),
            (setting.defect_note or "").strip(),
        )
        subject = _(
            "Ausleihbar booking %(code)s — reserved item unavailable"
        ) % {"code": _label(booking)}
        return send_user_mail(booking.borrower, subject, text)


def send_missing_product_notice(booking, items):
    """Warn a borrower that a reserved item is still out (not returned) and
    could not be moved to another unit before their pickup (issue #48)."""
    setting = NotificationSetting.load()
    pools = _pools_of(items)
    with translation.override(_lang(booking)):
        intro = _(
            "an item reserved on your booking %(code)s may not be available "
            "at pickup: it has not yet been returned and we could not move "
            "your booking to another unit:"
        ) % {"code": _label(booking)}
        text = _contact_text(
            intro, items, pools,
            _("Please contact the lending team before you come by:"),
            (setting.defect_note or "").strip(),
        )
        subject = _(
            "Ausleihbar booking %(code)s — reserved item may be unavailable"
        ) % {"code": _label(booking)}
        return send_user_mail(booking.borrower, subject, text)


def send_defect_pool_notice(resource, note=""):
    """Tell a pool's contact that one of its items was marked defective.

    Opt-in per pool via ``ResourcePool.notify_on_defect`` (concept §3.6);
    skipped when the pool has no contact email. Sent in the instance default
    language (#83). Fail-soft like the others.
    """
    pool = resource.resource_pool
    if not pool or not pool.notify_on_defect or not pool.email:
        return False
    with translation.override(_default_lang()):
        lines = [
            _("Hi,"),
            "",
            _("an item in %(pool)s was marked defective:") % {"pool": pool.name},
            "",
            f"  - {resource.product.title} ({resource.inventory_number})",
        ]
        if note:
            lines += ["", _("Note: %(note)s") % {"note": note}]
        lines += ["", SIGNATURE, ""]
        subject = _("Ausleihbar — item marked defective in %(pool)s") % {
            "pool": pool.name
        }
        return _send(subject, "\n".join(lines), pool.email)


def send_cancellation_notice(booking):
    """Tell each involved pool's contact that a borrower cancelled a booking.

    Opt-in per pool via ``ResourcePool.notify_on_cancellation`` (concept §6.5);
    skipped for pools without a contact email. One mail per notifying pool,
    in the instance default language (#83). Returns the number of mails sent.
    Fail-soft like the other notices.
    """
    shop = settings.SHOP_BASE_URL.rstrip("/")
    label = _label(booking)
    sent = 0
    for pool, items in _group_by_pool(booking):
        if not pool.notify_on_cancellation or not pool.email:
            continue
        with translation.override(_default_lang()):
            # Inside the override: the nameless fallback is translated too.
            borrower = _name(booking.borrower)
            lines = [
                _("Hi,"),
                "",
                _(
                    "%(borrower)s cancelled booking %(code)s. The following "
                    "item(s) from %(pool)s are free again:"
                ) % {"borrower": borrower, "code": label, "pool": pool.name},
                "",
            ]
            lines += [_item_line(i) for i in items]
            manage_line = _("Open the lending desk: %(url)s") % {
                "url": f"{shop}/manage/list"
            }
            lines += ["", manage_line, "", SIGNATURE, ""]
            subject = _(
                "Ausleihbar — booking %(code)s cancelled by %(borrower)s"
            ) % {"code": label, "borrower": borrower}
            if _send(subject, "\n".join(lines), pool.email):
                sent += 1
    return sent


def _closure_when(block):
    """The closure's date (range) for the mail intro, localised: "on X" for
    a single day, "from X to Y" for several."""
    lower = block.period.lower
    start = format_date(lower) if lower else ""
    if block.period.upper:
        end = format_date(block.period.upper - timedelta(microseconds=1))
        if end != start:
            return _("from %(start)s to %(end)s") % {"start": start, "end": end}
    return _("on %(date)s") % {"date": start}


def send_booking_rescheduled(booking, changes, block):
    """Tell a borrower their booking was moved because of a new closure.

    ``changes`` is a list of ``(item, old_period, new_period)`` tuples. The
    admin's reason note leads the mail; it ends with the full pickup details
    of each affected pool.
    """
    setting = NotificationSetting.load()
    pools = _pools_of([item for item, _o, _n in changes])
    with translation.override(_lang(booking)):
        lines = [
            _(
                "because of a closure %(when)s we had to reschedule your "
                "booking %(code)s:"
            ) % {"when": _closure_when(block), "code": _label(booking)},
            "",
        ]
        for item, old_period, new_period in changes:
            lending_type = item.resource.product.lending_type
            old = _bounds_str(old_period.lower, old_period.upper, lending_type)
            new = _bounds_str(new_period.lower, new_period.upper, lending_type)
            lines.append(
                f"  - {item.resource.product.title} "
                f"({item.resource.inventory_number}):"
            )
            lines.append("      " + _("before: %(period)s") % {"period": old})
            lines.append("      " + _("now: %(period)s") % {"period": new})
        lines += _pool_blocks(pools)
        subject = _(
            "Ausleihbar booking %(code)s — rescheduled due to a closure"
        ) % {"code": _label(booking)}
        return send_user_mail(
            booking.borrower, subject, "\n".join(lines),
            lead=(setting.rescheduled_note or "").strip(),
        )


def send_booking_cancelled_closure(booking, items, block):
    """Tell a borrower their booking was cancelled because of a new closure."""
    setting = NotificationSetting.load()
    pools = _pools_of(items)
    with translation.override(_lang(booking)):
        intro = _(
            "because of a closure %(when)s your booking %(code)s had "
            "to be cancelled:"
        ) % {"when": _closure_when(block), "code": _label(booking)}
        text = _contact_text(
            intro, items, pools,
            _("Please contact the lending team to arrange an alternative:"),
        )
        subject = _(
            "Ausleihbar booking %(code)s — cancelled due to a closure"
        ) % {"code": _label(booking)}
        return send_user_mail(
            booking.borrower, subject, text,
            lead=(setting.cancellation_note or "").strip(),
        )


def send_defect_review(recipient, pool, rows):
    """Ask a lender to retire or reactivate long-standing defective items.

    ``rows`` is a list of (resource, defective_since_date) tuples. Sent in
    the instance default language (#83).
    """
    with translation.override(_default_lang()):
        lines = [
            _("Hi,"),
            "",
            _(
                "these items in %(pool)s have been defective for a while. "
                "Please retire them or return them to service:"
            ) % {"pool": pool.name},
            "",
        ]
        for resource, since in rows:
            note = resource.defect_note or _("no note")
            since_str = _("defective since %(date)s") % {"date": format_date(since)}
            lines.append(
                f"  - {resource.inventory_number} ({resource.product.title}) — "
                f"{since_str}: {note}"
            )
        lines += ["", SIGNATURE, ""]
        subject = _("Ausleihbar — defective items in %(pool)s need review") % {
            "pool": pool.name
        }
        return _send(subject, "\n".join(lines), recipient)


def send_overdue_reminder(booking, pickups, returns):
    """Remind the borrower about overdue pickups and/or returns, with the
    affected pools' details (address, opening hours, contact)."""
    if not pickups and not returns:
        return False
    setting = NotificationSetting.load()
    pools = _pools_of(list(pickups) + list(returns))
    with translation.override(_lang(booking)):
        lines = [
            _("this is a reminder about your booking %(code)s.")
            % {"code": _label(booking)}
        ]
        if pickups:
            lines += ["", _("Not yet picked up (overdue):")]
            lines += [_item_line(i) for i in pickups]
        if returns:
            lines += ["", _("Not yet returned (overdue) — please bring them back:")]
            lines += [_item_line(i) for i in returns]
        # Overdue returns go back to the pool, so only head the blocks with
        # "Pickup at" when every item is still waiting to be picked up.
        lines += _pool_blocks(pools, pickup=not returns)
        lines += _note_lines((setting.reminder_note or "").strip())
        subject = _("Ausleihbar booking %(code)s — overdue reminder") % {
            "code": _label(booking)
        }
        sent = send_user_mail(booking.borrower, subject, "\n".join(lines))
    if sent:
        from .models import BookingReminder

        BookingReminder.objects.create(
            booking=booking,
            recipient=booking.borrower.email or "",
            overdue_pickups=len(pickups),
            overdue_returns=len(returns),
        )
    return sent


def send_pickup_reminder(booking, items, setting=None):
    """Remind the borrower the day before pickup (``send_pickup_reminders``):
    the items to collect with the full pickup details of their pool(s) —
    address, opening hours, directions, contact and pool note. ``setting``
    is the already loaded ``NotificationSetting`` (loaded when omitted)."""
    setting = setting or NotificationSetting.load()
    groups = {}
    for item in items:
        pool = item.resource.resource_pool
        groups.setdefault(pool.id, (pool, []))[1].append(item)
    with translation.override(_lang(booking)):
        label = _label(booking)
        lines = [
            _("your booking %(code)s can be picked up tomorrow:") % {"code": label}
        ]
        for pool, pool_items in groups.values():
            lines += ["", _pool_block(pool, pool_items)]
        lines += _note_lines((setting.pickup_reminder_note or "").strip())
        subject = _("Ausleihbar booking %(code)s — pickup tomorrow") % {
            "code": label
        }
        return send_user_mail(booking.borrower, subject, "\n".join(lines))
