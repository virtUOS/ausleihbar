# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Desksharing notifications: one service, a channel per person and event.

``notify(user, event, context)`` resolves the person's channel
(``NotificationPreference``, default ``mail``) and delivers. Only ``mail`` is
delivered in spec 1 (through ``lending.notifications.send_user_mail``, in the
person's language); ``push`` plugs in via ``register_channel`` in spec 2.

Privacy: a mail names no other person, except (a) the booker in "booked for
you" (the recipient is the holder; skipped when the booker opted out) and
(b) a release requester who chose to show their name (``requester_name`` in
the context, decided by ``requests.request_release``). Contexts hold neutral
place/time briefs.
"""
import logging
from datetime import date

from django.conf import settings
from django.core import signing
from django.utils import translation
from django.utils.translation import gettext as _, ngettext

from lending.notifications import format_date, send_user_mail

from . import hours, privacy
from .models import NotificationPreference, Place

logger = logging.getLogger(__name__)

DAILY_SUMMARY = "daily_summary"
GRACE_NUDGE = "grace_nudge"
RELEASED_NO_SHOW = "released_no_show"
RELEASED_OTHER = "released_other"
BOOKED_FOR_YOU = "booked_for_you"
ADMIN_CHANGED = "admin_changed"
SWAP_REQUEST = "swap_request"
SWAP_ANSWER = "swap_answer"
RELEASE_REQUEST = "release_request"
RELEASE_ANSWER = "release_answer"
SERIES_EXTENSION_DUE = "series_extension_due"

EVENTS = (
    DAILY_SUMMARY, GRACE_NUDGE, RELEASED_NO_SHOW, RELEASED_OTHER, BOOKED_FOR_YOU,
    ADMIN_CHANGED, SWAP_REQUEST, SWAP_ANSWER, RELEASE_REQUEST, RELEASE_ANSWER,
    SERIES_EXTENSION_DUE,
)

MAIL, PUSH, BOTH, OFF = (c.value for c in NotificationPreference.Channel)
DEFAULT_CHANNEL = MAIL
# Until spec 2 enables push, only these may be chosen.
SELECTABLE_CHANNELS = (MAIL, OFF)

# Delivery hooks per channel; spec 2 registers the web-push sender here.
_senders: dict = {}


def register_channel(channel: str, sender) -> None:
    """Register ``sender(user, event, context)`` for a channel (``push``)."""
    _senders[channel] = sender


def channel_for(user, event: str) -> str:
    row = (
        NotificationPreference.objects.filter(user_id=user.pk, event=event)
        .values_list("channel", flat=True)
        .first()
    )
    return row or DEFAULT_CHANNEL


def preferences_for(user) -> dict:
    """Every event with the person's channel."""
    stored = dict(
        NotificationPreference.objects.filter(user_id=user.pk).values_list("event", "channel")
    )
    return {event: stored.get(event, DEFAULT_CHANNEL) for event in EVENTS}


def set_preferences(user, changes: dict) -> None:
    for event, channel in changes.items():
        NotificationPreference.objects.update_or_create(
            user=user, event=event, defaults={"channel": channel}
        )


def notify(user, event: str, context: dict) -> bool:
    """Send ``event`` to ``user`` through their channel. Never raises for a
    delivery problem (the state change it reports is already done). Returns
    whether something was delivered."""
    delivered = False
    if user is None or not getattr(user, "pk", None):
        return False
    if event not in EVENTS:
        raise ValueError(f"Unknown desksharing event {event!r}")
    channel = channel_for(user, event)
    if channel == OFF:
        return False
    if channel in (MAIL, BOTH):
        try:
            delivered = bool(_send_mail(user, event, context)) or delivered
        except Exception:
            logger.exception("Desksharing mail %s failed for user %s", event, user.pk)
    if channel in (PUSH, BOTH):
        sender = _senders.get(PUSH)
        if sender is not None:
            try:
                sender(user, event, context)
                delivered = True
            except Exception:
                logger.exception("Desksharing push %s failed for user %s", event, user.pk)
    return delivered


# Signed one-click links ------------------------------------------------------

ACTION_SALT = "desksharing.action"


def make_action_token(reservation, user) -> str:
    """Token for ``POST /api/desks/actions/``: bound to the reservation and
    the recipient; the endpoint rejects it after the reservation ended."""
    return signing.dumps({"r": reservation.pk, "u": user.pk}, salt=ACTION_SALT, compress=True)


def read_action_token(token: str) -> tuple[int, int]:
    """``(reservation_id, user_id)``; ``signing.BadSignature`` if invalid."""
    data = signing.loads(token, salt=ACTION_SALT)
    return int(data["r"]), int(data["u"])


def _base() -> str:
    return settings.SHOP_BASE_URL.rstrip("/")


def action_url(reservation, user, action: str) -> str:
    return f"{_base()}/desks/a/{make_action_token(reservation, user)}?action={action}"


# Mail rendering ------------------------------------------------------------


def _lang(user) -> str:
    return getattr(user, "language", "") or settings.MODELTRANSLATION_DEFAULT_LANGUAGE


def _kind_label(kind: str) -> str:
    return _("Meeting room") if kind == Place.Kind.MEETING_ROOM else _("Desk")


def _place_text(place) -> str:
    """``D1 (R1, B1 EG)`` for a model place or a place brief dict."""
    if isinstance(place, dict):
        name, room, floor = place["name"], place.get("room", ""), place.get("floor", "")
        building, kind = place.get("building", ""), place.get("kind", Place.Kind.DESK)
    else:
        name, room, kind = place.name, place.room.name, place.kind
        floor, building = place.room.floor.name, place.room.floor.building
    name = f"{_kind_label(kind)} {name}"
    where = ", ".join(p for p in (room, " ".join(x for x in (building, floor) if x)) if p)
    return f"{name} ({where})" if where else name


def _span(day: date, start_hour: int, end_hour: int) -> str:
    return f"{format_date(day)}, {start_hour:02d}:00–{end_hour:02d}:00"


def _res_line(res) -> str:
    day, start, end = hours.local_day_hours(res.period)
    return f"{_span(day, start, end)}: {_place_text(res.place)}"


def _brief_line(brief: dict) -> str:
    return f"{_span(date.fromisoformat(brief['day']), brief['start_hour'], brief['end_hour'])}: " \
        f"{_place_text(brief['place'])}"


def _bullets(lines) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _app_link() -> str:
    return _("Open the desk booking: %(url)s") % {"url": f"{_base()}/desks"}


def _render_daily_summary(user, ctx):
    rows = sorted(ctx["reservations"], key=lambda r: (r.period.lower, r.pk))
    return (
        _("Your reservations for today"),
        _("here are your reservations for today:") + "\n\n"
        + _bullets(_res_line(r) for r in rows) + "\n\n" + _app_link(),
    )


def _render_grace_nudge(user, ctx):
    res = ctx["reservation"]
    text = (
        _("you have not checked in yet for your reservation:") + "\n\n"
        + _bullets([_res_line(res)]) + "\n\n"
        + _("If you do not show up, it may be given to someone else.") + "\n\n"
        + _("I am coming later: %(url)s") % {"url": action_url(res, user, "later")} + "\n"
        + _("Release: %(url)s") % {"url": action_url(res, user, "release")} + "\n\n"
        + _("The links work until the reservation ends and only for you.")
    )
    return _("Are you still coming? Your reservation is waiting"), text


def _rows(ctx) -> list:
    """The reservations of a context (a list, or the single legacy key)."""
    rows = ctx.get("reservations") or [ctx["reservation"]]
    return sorted(rows, key=lambda r: (r.period.lower, r.pk))


def _render_released_no_show(user, ctx):
    res = ctx["reservation"]
    text = (
        _("your reservation was released because you did not check in in time:") + "\n\n"
        + _bullets([_res_line(res)])
    )
    alternatives = ctx.get("alternatives") or []
    if alternatives:
        text += "\n\n" + _("Still free for the rest of that time:") + "\n"
        text += _bullets(_place_text(p) for p in alternatives)
    return _("Your reservation was released"), text + "\n\n" + _app_link()


def _render_released_other(user, ctx):
    reason = ctx.get("reason") or ""
    why = {
        "absence": _("absence"),
        "block": _("the place is blocked at that time"),
        "rights": _("you may no longer book this place"),
    }.get(reason, _("changed by the administration"))
    return (
        _("Your reservation was released"),
        _("your reservation was released (reason: %(why)s):") % {"why": why} + "\n\n"
        + _bullets(_res_line(r) for r in _rows(ctx)) + "\n\n" + _app_link(),
    )


def _render_booked_for_you(user, ctx):
    rows = sorted(ctx["reservations"], key=lambda r: (r.period.lower, r.pk))
    booker = rows[0].booked_by if rows else None
    if booker is not None and booker.pk != user.pk and not privacy.hides_name(booker):
        who = privacy.display_name(booker)
        intro = _("%(who)s booked for you:") % {"who": who}
    else:
        intro = _("a reservation was booked for you:")
    return (
        _("A reservation was booked for you"),
        intro + "\n\n" + _bullets(_res_line(r) for r in rows) + "\n\n" + _app_link(),
    )


def _render_admin_changed(user, ctx):
    rows = _rows(ctx)
    res = rows[0]
    reason = ctx.get("reason") or ""
    if ctx.get("action") == "move":
        text = (
            _("your reservation was moved by the administration:") + "\n\n"
            + _bullets([_res_line(res)]) + "\n"
            + _("Previous place: %(place)s") % {"place": _place_text(ctx["from_place"])}
        )
        return _("Your reservation was moved"), text + "\n\n" + _app_link()
    text = _("your reservation was cancelled by the administration:") + "\n\n" \
        + _bullets(_res_line(r) for r in rows)
    if reason == "place_removed":
        text += "\n\n" + _("The place is no longer available.")
    elif reason:
        text += "\n\n" + _("Reason: %(reason)s") % {"reason": reason}
    return _("Your reservation was cancelled"), text + "\n\n" + _app_link()


def _render_swap_request(user, ctx):
    return (
        _("Request to swap places"),
        _("someone would like to swap their reservation with yours.") + "\n\n"
        + _("Offered:") + "\n" + _bullets([_brief_line(ctx["offered"])]) + "\n"
        + _("Yours:") + "\n" + _bullets([_brief_line(ctx["own"])]) + "\n\n"
        + _("Please answer in the app:") + " " + f"{_base()}/desks",
    )


def _render_swap_answer(user, ctx):
    if ctx.get("accepted"):
        text = (
            _("your swap request was accepted. Your reservation is now:") + "\n\n"
            + _bullets([_brief_line(ctx["reservation"])])
        )
        previous = ctx.get("previous")
        if previous:
            text += "\n" + _("Before:") + "\n" + _bullets([_brief_line(previous)])
        return _("Swap request accepted"), text + "\n\n" + _app_link()
    return (
        _("Swap request declined"),
        _("your swap request was declined. Your reservation stays as it was:") + "\n\n"
        + _bullets([_brief_line(ctx["reservation"])]) + "\n\n" + _app_link(),
    )


def _render_release_request(user, ctx):
    name = ctx.get("requester_name")
    if name:
        intro = _("%(name)s would like to take over your reservation:") % {"name": name}
    else:
        intro = _("someone would like to take over your reservation:")
    return (
        _("Request to release your reservation"),
        intro + "\n\n"
        + _bullets([_brief_line(ctx["reservation"])]) + "\n\n"
        + _("Please answer in the app:") + " " + f"{_base()}/desks",
    )


def _render_release_answer(user, ctx):
    if ctx.get("accepted"):
        return (
            _("Your request was accepted"),
            _("your request was accepted. The reservation is now yours:") + "\n\n"
            + _bullets([_brief_line(ctx["reservation"])]) + "\n\n" + _app_link(),
        )
    return (
        _("Your request was declined"),
        _("your request for this reservation was declined:") + "\n\n"
        + _bullets([_brief_line(ctx["reservation"])]) + "\n\n" + _app_link(),
    )


def _render_series_extension_due(user, ctx):
    series = ctx["series"]
    days = ctx["days"]
    return (
        _("Your recurring reservation ends soon"),
        ngettext(
            "your recurring reservation of %(place)s ends on %(date)s (in %(days)d day).",
            "your recurring reservation of %(place)s ends on %(date)s (in %(days)d days).",
            days,
        )
        % {"place": _place_text(series.place), "date": format_date(series.valid_until), "days": days}
        + "\n\n" + _("You can extend it by three months in the app:")
        + f" {_base()}/desks",
    )


_RENDERERS = {
    DAILY_SUMMARY: _render_daily_summary,
    GRACE_NUDGE: _render_grace_nudge,
    RELEASED_NO_SHOW: _render_released_no_show,
    RELEASED_OTHER: _render_released_other,
    BOOKED_FOR_YOU: _render_booked_for_you,
    ADMIN_CHANGED: _render_admin_changed,
    SWAP_REQUEST: _render_swap_request,
    SWAP_ANSWER: _render_swap_answer,
    RELEASE_REQUEST: _render_release_request,
    RELEASE_ANSWER: _render_release_answer,
    SERIES_EXTENSION_DUE: _render_series_extension_due,
}


def _send_mail(user, event: str, context: dict) -> bool:
    with translation.override(_lang(user)):
        subject, text = _RENDERERS[event](user, context)
        link = _("Your desk bookings: %(url)s") % {"url": f"{_base()}/desks/mine"}
        return send_user_mail(user, subject, text, link_line=link)


def notify_grouped(reservations, event: str, *, log=logger, **context) -> None:
    """One mail per holder listing all of their ``reservations`` (bulk
    changes). Call after commit; failures are logged per holder."""
    by_holder: dict = {}
    for res in reservations:
        if res.holder is not None:
            by_holder.setdefault(res.holder_id, (res.holder, []))[1].append(res)
    for holder, rows in by_holder.values():
        try:
            notify(holder, event, {"reservations": rows, **context})
        except Exception:
            log.exception("Notification %s failed for user %s", event, holder.pk)
