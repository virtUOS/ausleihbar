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
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from catalog.models import NotificationSetting, Product

from .ics import build_ics
from .qr import make_qr_png, pickup_qr_url

logger = logging.getLogger(__name__)


def _lang(booking):
    """The borrower's preferred email language, or the institution default."""
    return (
        getattr(booking.borrower, "language", "")
        or settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    )


def _pool_lang(pool):
    """The configured email language for a pool (its contact + lenders)."""
    return getattr(pool, "email_language", "") or settings.MODELTRANSLATION_DEFAULT_LANGUAGE

# Weekday keys in display order, matching ResourcePool.opening_hours.
_WEEKDAYS = [
    ("mon", "Mon"), ("tue", "Tue"), ("wed", "Wed"), ("thu", "Thu"),
    ("fri", "Fri"), ("sat", "Sat"), ("sun", "Sun"),
]


def _format_bounds(lower, upper, lending_type):
    """(start, end) strings for a period's bounds.

    Day bookings show inclusive calendar dates — the stored upper bound is the
    exclusive following midnight, so the last booked day is one tick earlier.
    Hourly bookings show date and time.
    """
    if lending_type == Product.LendingType.DAYS:
        date_fmt = "%a %d %b %Y"
        start = timezone.localtime(lower).strftime(date_fmt) if lower else "?"
        if not upper:
            return start, _("open end")
        last = timezone.localtime(upper - timedelta(microseconds=1)).strftime(date_fmt)
        return start, last
    fmt = "%a %d %b %Y, %H:%M"
    start = timezone.localtime(lower).strftime(fmt) if lower else "?"
    end = timezone.localtime(upper).strftime(fmt) if upper else _("open end")
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
            lines.append(f"{label}: {spans}")
    return lines


def _pool_block(pool, items):
    """One readable, plain-text pickup block per pool.

    Each sub-section (items, address, opening hours, directions, contact) is
    separated by a blank line and consistently indented, so the mail stays
    legible in any client.
    """
    header = _("Pickup at %(pool)s") % {"pool": pool.name}
    if pool.room:
        header += f" · {pool.room}"
    lines = [header, ""]

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

    hours = _opening_hours_lines(pool.opening_hours)
    if hours:
        lines += ["", "  " + _("Opening hours:")]
        lines += [f"    {h}" for h in hours]

    if pool.directions:
        lines += ["", "  " + _("Directions: %(text)s") % {"text": pool.directions}]

    contact = " / ".join(x for x in [pool.phone, pool.email] if x)
    if contact:
        lines += ["", "  " + _("Contact: %(contact)s") % {"contact": contact}]

    # Optional per-pool note (active language), e.g. eligibility hints.
    note = (getattr(pool, "email_note", "") or "").strip()
    if note:
        lines += [""] + [f"  {line}" for line in note.splitlines()]

    return "\n".join(lines)


def _pools_of(items):
    """Ordered, unique resource pools of the given booking items."""
    seen = {}
    for item in items:
        pool = item.resource.resource_pool
        seen.setdefault(pool.id, pool)
    return list(seen.values())


def _pool_note_lines(pools):
    """Per-pool email notes (active language) for pools that have one.

    Prefixes the pool name only when more than one pool contributes a note, so
    a borrower can tell which hint belongs where.
    """
    with_note = [p for p in pools if (getattr(p, "email_note", "") or "").strip()]
    lines = []
    for pool in with_note:
        note_lines = pool.email_note.strip().splitlines()
        prefix = f"{pool.name}: " if len(with_note) > 1 else ""
        lines += ["", f"  {prefix}{note_lines[0]}"]
        lines += [f"  {line}" for line in note_lines[1:]]
    return lines


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


def _body(booking, *, confirmed, message="", intro_override="", footer=""):
    label = _label(booking)
    if confirmed:
        intro = _(
            "your reservation %(code)s is confirmed. Please pick up your "
            "item(s) during the opening hours below."
        ) % {"code": label}
    else:
        # The reservation number lives in its own mandatory line below, so a
        # custom intro can't drop it — keep it out of the default intro text.
        intro = intro_override or _(
            "we received your reservation. It is on hold and the "
            "lending team will confirm it shortly."
        )
    blocks = [_pool_block(pool, items) for pool, items in _group_by_pool(booking)]
    shop = settings.SHOP_BASE_URL.rstrip("/")
    greeting = _("Hi %(name)s,") % {"name": _name(booking.borrower)}
    body = f"{greeting}\n\n{intro}"
    if not confirmed:
        body += "\n\n" + _("Reservation number: %(code)s") % {"code": label}
    body += "\n\n" + "\n\n".join(blocks)
    if message:
        body += "\n\n" + _("A note from the lending team:\n%(msg)s") % {"msg": message}
    if booking.note:
        body += "\n\n" + _("Your message: %(note)s") % {"note": booking.note}
    if confirmed:
        body += "\n\n" + _(
            "At pickup, show your code %(code)s — the attached QR code can be "
            "scanned by the lending desk."
        ) % {"code": label}
    bookings_line = _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}
    body += f"\n\n{bookings_line}"
    if footer:
        body += f"\n\n{footer}"
    return body + "\n\n— Ausleihbar\n"


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

    Reuses the same pieces as :func:`_body` (greeting, per-pool blocks, note,
    bookings link, footer), but lists one "Reservation number" line and its
    pool block(s) per booking, since a multi-pool cart submit (#26) produces
    one booking per pool. For a single booking this renders identically to
    ``_body(booking, confirmed=False, ...)``.
    """
    first = bookings[0]
    intro = intro_override or _(
        "we received your reservation. It is on hold and the "
        "lending team will confirm it shortly."
    )
    shop = settings.SHOP_BASE_URL.rstrip("/")
    greeting = _("Hi %(name)s,") % {"name": _name(first.borrower)}
    body = f"{greeting}\n\n{intro}"
    if len(bookings) > 1:
        body += "\n\n" + _("Each pool confirms its part of your order separately.")
    for booking in bookings:
        body += "\n\n" + _("Reservation number: %(code)s") % {"code": _label(booking)}
        blocks = [_pool_block(pool, items) for pool, items in _group_by_pool(booking)]
        body += "\n\n" + "\n\n".join(blocks)
    if first.note:
        body += "\n\n" + _("Your message: %(note)s") % {"note": first.note}
    bookings_line = _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}
    body += f"\n\n{bookings_line}"
    if footer:
        body += f"\n\n{footer}"
    return body + "\n\n— Ausleihbar\n"


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


def send_confirmation_email(booking, message=""):
    """Notify the borrower that their reservation was confirmed.

    Attaches a QR code of the booking code so the lending desk can scan the
    pickup from the borrower's phone (concept §6.2), and an iCalendar entry of
    the pickup period(s) for the borrower's calendar (concept §4.6). An optional
    ``message`` is a one-off note the confirming lender adds (issue #29).
    """
    label = _label(booking)
    attachments = [
        (f"pickup-{label}.png", make_qr_png(pickup_qr_url(booking)), "image/png"),
        (f"booking-{label}.ics", build_ics(booking), "text/calendar"),
    ]
    with translation.override(_lang(booking)):
        subject = _(
            "Ausleihbar reservation %(code)s confirmed — pickup details"
        ) % {"code": label}
        return _send_attached(
            subject,
            _body(booking, confirmed=True, message=message),
            booking.borrower.email,
            attachments,
        )


def _item_line(item):
    return (
        f"  - {item.resource.product.title} ({item.resource.inventory_number}): "
        f"{_period_str(item)}"
    )


def send_defect_notice(booking, items):
    """Tell a borrower a reserved device is defective and could not be moved."""
    shop = settings.SHOP_BASE_URL.rstrip("/")
    setting = NotificationSetting.load()
    pools = _pools_of(items)
    with translation.override(_lang(booking)):
        lines = [_("Hi %(name)s,") % {"name": _name(booking.borrower)}, ""]
        lines.append(
            _(
                "a device reserved on your booking %(code)s has become "
                "unavailable (defect) and we could not move it to another unit:"
            ) % {"code": _label(booking)}
        )
        lines += [""]
        lines += [_item_line(i) for i in items]
        lines += ["", _("Please contact the lending pool to arrange an alternative:")]
        for pool in pools:
            contact = " / ".join(x for x in [pool.phone, pool.email] if x)
            lines.append(f"  {pool.name}{(' — ' + contact) if contact else ''}")
        lines += _pool_note_lines(pools)
        bookings_line = _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}
        lines += ["", bookings_line]
        extra = (setting.defect_note or "").strip()
        if extra:
            lines += ["", extra]
        lines += ["", "— Ausleihbar", ""]
        subject = _(
            "Ausleihbar reservation %(code)s — reserved device unavailable"
        ) % {"code": _label(booking)}
        return _send(subject, "\n".join(lines), booking.borrower.email)


def send_missing_product_notice(booking, items):
    """Warn a borrower that a reserved device is still out (not returned) and
    could not be moved to another unit before their pickup (issue #48)."""
    shop = settings.SHOP_BASE_URL.rstrip("/")
    setting = NotificationSetting.load()
    pools = _pools_of(items)
    with translation.override(_lang(booking)):
        lines = [_("Hi %(name)s,") % {"name": _name(booking.borrower)}, ""]
        lines.append(
            _(
                "a device reserved on your booking %(code)s may not be available "
                "at pickup: it has not yet been returned and we could not move "
                "your booking to another unit:"
            ) % {"code": _label(booking)}
        )
        lines += [""]
        lines += [_item_line(i) for i in items]
        lines += ["", _("Please contact the lending pool before you come by:")]
        for pool in pools:
            contact = " / ".join(x for x in [pool.phone, pool.email] if x)
            lines.append(f"  {pool.name}{(' — ' + contact) if contact else ''}")
        lines += _pool_note_lines(pools)
        lines += ["", _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}]
        extra = (setting.defect_note or "").strip()
        if extra:
            lines += ["", extra]
        lines += ["", "— Ausleihbar", ""]
        subject = _(
            "Ausleihbar reservation %(code)s — reserved device may be unavailable"
        ) % {"code": _label(booking)}
        return _send(subject, "\n".join(lines), booking.borrower.email)


def send_defect_pool_notice(resource, note=""):
    """Tell a pool's contact that one of its resources was marked defective.

    Opt-in per pool via ``ResourcePool.notify_on_defect`` (concept §3.6);
    skipped when the pool has no contact email. Fail-soft like the others.
    """
    pool = resource.resource_pool
    if not pool or not pool.notify_on_defect or not pool.email:
        return False
    with translation.override(_pool_lang(pool)):
        lines = [
            _("Hi,"),
            "",
            _("a resource in %(pool)s was marked defective:") % {"pool": pool.name},
            "",
            f"  - {resource.product.title} ({resource.inventory_number})",
        ]
        if note:
            lines += ["", _("Note: %(note)s") % {"note": note}]
        lines += ["", "— Ausleihbar", ""]
        subject = _("Ausleihbar — device marked defective in %(pool)s") % {
            "pool": pool.name
        }
        return _send(subject, "\n".join(lines), pool.email)


def send_cancellation_notice(booking):
    """Tell each involved pool's contact that a borrower cancelled a booking.

    Opt-in per pool via ``ResourcePool.notify_on_cancellation`` (concept §6.5);
    skipped for pools without a contact email. One mail per notifying pool.
    Returns the number of mails sent. Fail-soft like the other notices.
    """
    shop = settings.SHOP_BASE_URL.rstrip("/")
    borrower = _name(booking.borrower)
    label = _label(booking)
    sent = 0
    for pool, items in _group_by_pool(booking):
        if not pool.notify_on_cancellation or not pool.email:
            continue
        with translation.override(_pool_lang(pool)):
            lines = [
                _("Hi,"),
                "",
                _(
                    "%(borrower)s cancelled reservation %(code)s. The following "
                    "item(s) from %(pool)s are free again:"
                ) % {"borrower": borrower, "code": label, "pool": pool.name},
                "",
            ]
            lines += [_item_line(i) for i in items]
            manage_line = _("Open the lending desk: %(url)s") % {
                "url": f"{shop}/manage/list"
            }
            lines += ["", manage_line, "", "— Ausleihbar", ""]
            subject = _(
                "Ausleihbar — reservation %(code)s cancelled by %(borrower)s"
            ) % {"code": label, "borrower": borrower}
            if _send(subject, "\n".join(lines), pool.email):
                sent += 1
    return sent


def _closure_when(block):
    """The closure's date (range) for the mail subject/intro."""
    lower = block.period.lower
    start = timezone.localtime(lower).strftime("%d %b %Y") if lower else ""
    if block.period.upper:
        last = timezone.localtime(block.period.upper - timedelta(microseconds=1))
        end = last.strftime("%d %b %Y")
        if end != start:
            return f"{start} – {end}"
    return start


def send_booking_rescheduled(booking, changes, block):
    """Tell a borrower their booking was moved because of a new closure.

    ``changes`` is a list of ``(item, old_period, new_period)`` tuples.
    """
    shop = settings.SHOP_BASE_URL.rstrip("/")
    setting = NotificationSetting.load()
    pools = _pools_of([item for item, _o, _n in changes])
    with translation.override(_lang(booking)):
        lines = [_("Hi %(name)s,") % {"name": _name(booking.borrower)}, ""]
        lines.append(
            _(
                "because of a closure on %(when)s we had to reschedule your "
                "reservation %(code)s:"
            ) % {"when": _closure_when(block), "code": _label(booking)}
        )
        lines += [""]
        for item, old_period, new_period in changes:
            lending_type = item.resource.product.lending_type
            old = _bounds_str(old_period.lower, old_period.upper, lending_type)
            new = _bounds_str(new_period.lower, new_period.upper, lending_type)
            lines.append(
                f"  - {item.resource.product.title} "
                f"({item.resource.inventory_number}):"
            )
            lines.append(f"      {old}  →  {new}")
        lines += _pool_note_lines(pools)
        bookings_line = _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}
        lines += ["", bookings_line]
        extra = (setting.rescheduled_note or "").strip()
        if extra:
            lines += ["", extra]
        lines += ["", "— Ausleihbar", ""]
        subject = _(
            "Ausleihbar reservation %(code)s — rescheduled due to a closure"
        ) % {"code": _label(booking)}
        return _send(subject, "\n".join(lines), booking.borrower.email)


def send_booking_cancelled_closure(booking, items, block):
    """Tell a borrower their booking was cancelled because of a new closure."""
    shop = settings.SHOP_BASE_URL.rstrip("/")
    setting = NotificationSetting.load()
    pools = _pools_of(items)
    with translation.override(_lang(booking)):
        lines = [_("Hi %(name)s,") % {"name": _name(booking.borrower)}, ""]
        lines.append(
            _(
                "because of a closure on %(when)s your reservation %(code)s had "
                "to be cancelled:"
            ) % {"when": _closure_when(block), "code": _label(booking)}
        )
        lines += [""]
        lines += [_item_line(i) for i in items]
        lines += ["", _("Please contact the lending pool to arrange an alternative:")]
        for pool in pools:
            contact = " / ".join(x for x in [pool.phone, pool.email] if x)
            lines.append(f"  {pool.name}{(' — ' + contact) if contact else ''}")
        lines += _pool_note_lines(pools)
        bookings_line = _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}
        lines += ["", bookings_line]
        extra = (setting.cancellation_note or "").strip()
        if extra:
            lines += ["", extra]
        lines += ["", "— Ausleihbar", ""]
        subject = _(
            "Ausleihbar reservation %(code)s — cancelled due to a closure"
        ) % {"code": _label(booking)}
        return _send(subject, "\n".join(lines), booking.borrower.email)


def send_defect_review(recipient, pool, rows):
    """Ask a lender to retire or reactivate long-standing defective resources.

    ``rows`` is a list of (resource, defective_since_date) tuples.
    """
    with translation.override(_pool_lang(pool)):
        lines = [
            _("Hi,"),
            "",
            _(
                "these resources in %(pool)s have been defective for a while. "
                "Please retire them or return them to service:"
            ) % {"pool": pool.name},
            "",
        ]
        for resource, since in rows:
            note = resource.defect_note or _("no note")
            since_str = _("defective since %(date)s") % {"date": f"{since:%Y-%m-%d}"}
            lines.append(
                f"  - {resource.inventory_number} ({resource.product.title}) — "
                f"{since_str}: {note}"
            )
        lines += ["", "— Ausleihbar", ""]
        subject = _("Ausleihbar — defective resources in %(pool)s need review") % {
            "pool": pool.name
        }
        return _send(subject, "\n".join(lines), recipient)


def send_overdue_reminder(booking, pickups, returns):
    """Remind the borrower about overdue pickups and/or returns."""
    if not pickups and not returns:
        return False
    shop = settings.SHOP_BASE_URL.rstrip("/")
    setting = NotificationSetting.load()
    pools = _pools_of(list(pickups) + list(returns))
    with translation.override(_lang(booking)):
        lines = [_("Hi %(name)s,") % {"name": _name(booking.borrower)}, ""]
        lines.append(
            _("this is a reminder about your reservation %(code)s.")
            % {"code": _label(booking)}
        )
        if pickups:
            lines += ["", _("Not yet picked up (overdue):")]
            lines += [_item_line(i) for i in pickups]
        if returns:
            lines += ["", _("Not yet returned (overdue) — please bring them back:")]
            lines += [_item_line(i) for i in returns]
        lines += _pool_note_lines(pools)
        bookings_line = _("View your bookings: %(url)s") % {"url": f"{shop}/bookings"}
        lines += ["", bookings_line]
        extra = (setting.reminder_note or "").strip()
        if extra:
            lines += ["", extra]
        lines += ["", "— Ausleihbar", ""]
        subject = _("Ausleihbar reservation %(code)s — overdue reminder") % {
            "code": _label(booking)
        }
        sent = _send(subject, "\n".join(lines), booking.borrower.email)
    if sent:
        from .models import BookingReminder

        BookingReminder.objects.create(
            booking=booking,
            recipient=booking.borrower.email or "",
            overdue_pickups=len(pickups),
            overdue_returns=len(returns),
        )
    return sent
