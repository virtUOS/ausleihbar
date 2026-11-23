# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Button interaction of a door display.

The device only sends button names; the interaction state (``select`` /
``confirm`` sessions) lives in ``Display.ui_state``. ``press`` maps a button
to an action and returns the ``Screen`` to render; ``current_screen`` is the
read-only counterpart (an expired session falls back to ``normal``).
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from . import checkin, door_actions, hours
from .booking import BookingError
from .door_view import LABEL_HIDDEN, DoorView, build_door_view
from .models import Reservation

BUTTONS = ("top", "up", "down", "bottom", "wake")

SELECT_TIMEOUT = 20  # seconds the select / duration session stays awake
CONFIRM_TIMEOUT = 10

TEXT_CONFIRM_DESK = "{name} auschecken?"
TEXT_CONFIRM_MEETING = "Meeting beenden?"
MSG_CHECKED_IN = "Eingecheckt ✓"
MSG_CHECKED_OUT = "Ausgecheckt"
MSG_BOOKED = "Belegt bis {time}"
MSG_FAILED = "Nicht möglich"


@dataclass
class Screen:
    view: DoorView
    mode: str  # normal | select | confirm
    selected: int | None  # desk index in ``view.desks``
    hours: int  # chosen meeting duration
    confirm_text: str | None
    message: str | None
    session_timeout: int  # 0 = no session, else seconds the device stays awake


def _normal_state() -> dict:
    return {"mode": "normal", "index": 0, "hours": 1, "target": None, "expires_at": None}


def _load(display, now) -> dict:
    """The stored state, or a fresh normal one when absent or expired."""
    raw = display.ui_state or {}
    state = {**_normal_state(), **raw}
    if state["mode"] == "normal" or not state["expires_at"]:
        return _normal_state()
    if datetime.fromisoformat(state["expires_at"]) <= now:
        return _normal_state()
    return state


def _save(display, state) -> None:
    display.ui_state = state
    display.save(update_fields=["ui_state"])


def _session(mode, now, timeout, *, index=0, hours_=1, target=None) -> dict:
    return {
        "mode": mode,
        "index": index,
        "hours": hours_,
        "target": target,
        "expires_at": (now + timedelta(seconds=timeout)).isoformat(),
    }


def _view(display, now) -> DoorView:
    return build_door_view(display.room, panel=display.panel, now=now)


def _confirm_name(tile) -> str:
    if tile.label and tile.label != LABEL_HIDDEN:
        return tile.label
    return tile.name


def _screen(display, state, now, *, view=None, message=None) -> Screen:
    view = view or _view(display, now)
    mode = state["mode"]
    selected = None
    confirm_text = None
    if mode == "select" and view.kind == "office" and view.desks:
        selected = min(max(int(state["index"]), 0), len(view.desks) - 1)
    elif mode == "confirm":
        target = state["target"] or {}
        if view.kind in ("single", "office"):
            tile = next(
                (t for t in view.desks if t.reservation_id == target.get("reservation_id")), None
            )
            if tile is None:
                state = _normal_state()
                mode = "normal"
            else:
                confirm_text = TEXT_CONFIRM_DESK.format(name=_confirm_name(tile))
                selected = view.desks.index(tile) if view.kind == "office" else None
        elif view.kind == "meeting":
            confirm_text = TEXT_CONFIRM_MEETING
        else:
            state = _normal_state()
            mode = "normal"
    elif mode == "select" and view.kind != "meeting":
        state = _normal_state()
        mode = "normal"
    timeout = 0
    if mode != "normal":
        left = datetime.fromisoformat(state["expires_at"]) - now
        timeout = max(0, math.ceil(left.total_seconds()))
    return Screen(
        view=view,
        mode=mode,
        selected=selected,
        hours=int(state["hours"]),
        confirm_text=confirm_text,
        message=message,
        session_timeout=timeout,
    )


def current_screen(display, now) -> Screen:
    return _screen(display, _load(display, now), now)


def _reload(reservation_id) -> Reservation | None:
    if reservation_id is None:
        return None
    return (
        Reservation.objects.select_related("place__pool", "place__room", "holder")
        .filter(pk=reservation_id, status=Reservation.Status.ACTIVE)
        .first()
    )


def _run(display, now, state, action, reservation) -> Screen:
    """Run a check-in / check-out and return the follow-up ``normal`` screen."""
    try:
        if action == "check_in":
            door_actions.check_in(reservation, display=display, now=now)
            message = MSG_CHECKED_IN
        else:
            door_actions.check_out(reservation, display=display, now=now)
            message = MSG_CHECKED_OUT
    except BookingError:
        message = MSG_FAILED
    return _finish(display, now, message)


def _finish(display, now, message=None) -> Screen:
    state = _normal_state()
    _save(display, state)
    return _screen(display, state, now, message=message)


def _stale(display, now) -> Screen:
    return _finish(display, now, None)


def _enter_confirm(display, now, reservation_id, action) -> Screen:
    state = _session(
        "confirm", now, CONFIRM_TIMEOUT, index=_load(display, now)["index"],
        target={"reservation_id": reservation_id, "action": action},
    )
    _save(display, state)
    return _screen(display, state, now)


def _confirmed(display, now, state) -> Screen:
    """Act on the confirm target if it is still in the expected state."""
    target = state["target"] or {}
    res = _reload(target.get("reservation_id"))
    action = target.get("action")
    if res is None:
        return _stale(display, now)
    if action == "check_out":
        valid = res.checked_in_at is not None and res.period.lower <= now
    elif action == "check_in":
        valid = res.checked_in_at is None and checkin._window_open(res, now)
    else:
        valid = False
    if not valid:
        return _stale(display, now)
    return _run(display, now, state, action, res)


def _refresh(display, state, now) -> Screen:
    """No action: keep the session (restarting its timer) and re-render."""
    if state["mode"] != "normal":
        state = _session(
            state["mode"], now, CONFIRM_TIMEOUT if state["mode"] == "confirm" else SELECT_TIMEOUT,
            index=state["index"], hours_=state["hours"], target=state["target"],
        )
        _save(display, state)
    return _screen(display, state, now)


def _press_single(display, button, now, state, view) -> Screen:
    tile = view.desks[0]
    if state["mode"] == "confirm":
        return _confirmed(display, now, state)
    if tile.actionable == "check_in":
        return _run(display, now, state, "check_in", _reload(tile.reservation_id))
    if tile.actionable == "check_out":
        return _enter_confirm(display, now, tile.reservation_id, "check_out")
    return _screen(display, state, now, view=view)


def _first_actionable(view) -> int:
    return next((i for i, t in enumerate(view.desks) if t.actionable), 0)


def _press_office(display, button, now, state, view) -> Screen:
    mode = state["mode"]
    count = len(view.desks)
    if mode == "normal":
        if button in ("up", "down"):
            new = _session("select", now, SELECT_TIMEOUT, index=_first_actionable(view))
            _save(display, new)
            return _screen(display, new, now, view=view)
        return _screen(display, state, now, view=view)
    if mode == "select":
        index = min(max(int(state["index"]), 0), count - 1)
        if button in ("up", "down"):
            index = (index + (1 if button == "down" else -1)) % count
            new = _session("select", now, SELECT_TIMEOUT, index=index)
            _save(display, new)
            return _screen(display, new, now, view=view)
        if button == "bottom":
            return _finish(display, now)
        if button == "top":
            tile = view.desks[index]
            if tile.actionable == "check_in":
                return _run(display, now, state, "check_in", _reload(tile.reservation_id))
            if tile.actionable == "check_out":
                new = _session(
                    "confirm", now, CONFIRM_TIMEOUT, index=index,
                    target={"reservation_id": tile.reservation_id, "action": "check_out"},
                )
                _save(display, new)
                return _screen(display, new, now, view=view)
        return _refresh(display, {**state, "index": index}, now)
    # confirm
    if button == "top":
        return _confirmed(display, now, state)
    if button == "bottom":
        return _finish(display, now)
    return _refresh(display, state, now)


def _press_meeting(display, button, now, state, view) -> Screen:
    info = view.meeting
    mode = state["mode"]
    if mode == "confirm":
        if button == "top":
            return _confirmed(display, now, state)
        if button == "bottom":
            return _finish(display, now)
        return _refresh(display, state, now)
    res = _reload(info.reservation_id)
    if res is not None:
        if button != "top":
            return _screen(display, state, now, view=view)
        if res.checked_in_at is None:
            if checkin._window_open(res, now):
                return _run(display, now, state, "check_in", res)
        elif res.period.lower <= now:
            return _enter_confirm(display, now, res.pk, "check_out")
        return _screen(display, state, now, view=view)
    if info.state != "free" or info.max_hours < 1:
        return _screen(display, state, now, view=view)
    chosen = min(max(int(state["hours"]), 1), info.max_hours)
    if button in ("up", "down"):
        chosen = min(max(chosen + (1 if button == "up" else -1), 1), info.max_hours)
        new = _session("select", now, SELECT_TIMEOUT, hours_=chosen)
        _save(display, new)
        return _screen(display, new, now, view=view)
    if button == "bottom" and mode == "select":
        return _finish(display, now)
    if button == "top":
        try:
            booked = door_actions.book_anonymous(
                info_place(display, view), display=display, hours_=chosen, now=now
            )
        except BookingError:
            return _finish(display, now, MSG_FAILED)
        end = timezone.localtime(booked.period.upper, hours.TZ)
        return _finish(display, now, MSG_BOOKED.format(time=f"{end:%H:%M}"))
    return _refresh(display, state, now)


def info_place(display, view):
    """The meeting-room place of the display's room."""
    from .models import Place

    return (
        Place.objects.select_related("pool", "room")
        .filter(room=display.room, kind=Place.Kind.MEETING_ROOM, is_active=True, pool__isnull=False)
        .order_by("name", "pk")
        .first()
    )


def press(display, button: str, now) -> Screen:
    state = _load(display, now)
    if button not in BUTTONS or button == "wake":
        return _screen(display, state, now)
    view = _view(display, now)
    if view.kind in ("empty", "closed"):
        return _screen(display, _normal_state(), now, view=view)
    if view.kind != "single" and display.panel == "2.1":
        return _screen(display, _normal_state(), now, view=view)
    if view.kind == "single":
        return _press_single(display, button, now, state, view)
    if view.kind == "office":
        return _press_office(display, button, now, state, view)
    return _press_meeting(display, button, now, state, view)
