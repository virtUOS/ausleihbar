# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Room and item layouts of the door display frames (see ``door_render``).

Item signs (spec §6.5): ``item_small`` (2.1") and ``item_wide`` (5.79").

Approved mockups: single office 2.1" (four states), multi-desk office 5.79"
(2 / 2×2 / 4×2 tiles, selection with a thick frame and no pointer), meeting
room 5.79" (state left, top-button action top right, schedule below) and a
2.1" summary for rooms that need the large panel.
"""
from django.utils import timezone

from .door_render import (
    BLACK, ELLIPSIS, HINT_REFRESH, HINT_YES_ANY, TEXT_CONFIRM_DESK_NOTE, TEXT_CONFIRM_MEETING_NOTE, WHITE,
    block_height, clean, content_right, dashed_rect, dashed_vline, draw_confirm, draw_hints,
    draw_lines, fit_lines, fit_text, font, hhmm, line_step, opens_line, qr_image, stand,
    text_height, truncate,
)
from .door_view import LABEL_FREE
from .hours import TZ

# User-facing literals (German UI of the sign).
ROOM_MEETING = "{room} · Besprechungsraum"
FREE = "FREI"
FREE_UNTIL = "bis {time}"
BOOKED_PERIOD = "GEBUCHT {start} – {end}"
RUNNING_UNTIL = "BELEGT bis {time}"
BOOKED = "GEBUCHT"
RUNNING = "BELEGT"
CLOSED = "GESCHLOSSEN"
CLOSED_SHORT = "Geschlossen"
NOT_CHECKED_IN = "noch nicht eingecheckt"
CHECKED_IN = "eingecheckt ✓"
BOOK_WITH_NAME = "Mit Namen buchen →"
WITHOUT_LOGIN = "ohne Anmeldung"
TAKE_HOURS = "Belegen {hours} Std. ▸"
TAKE_IMPOSSIBLE = "Belegen nicht möglich"
RELEASE_AT = "Freigabe {time}"
CHECK_IN_ACTION = "Einchecken ▸"
END_MEETING = "Meeting beenden ▸"
SCHEDULE_TODAY = "Heute"
SCHEDULE_DURATION = "Heute · Dauer mit der Wippe ändern"
SCHEDULE_AFTER = "Danach"
SCHEDULE_EMPTY = "Keine weiteren Buchungen"
SLOT_FREE = LABEL_FREE
HIDDEN = "belegt"

OFFICE_FREE = "{free} von {total} frei"
OFFICE_TAKEN = "besetzt"
OFFICE_SELECT = "{room} · Platz wählen"
OFFICE_POSITION = "Platz {pos} von {total}"
OFFICE_MORE = "+{count}"
TILE_STATE = {
    "checked_in": " · anwesend ✓",
    "booked": " · gebucht",
    "potentially_free": " · evtl. frei",
    "closed": " · geschlossen",
}
TILE_STATE_SHORT = {"checked_in": " ✓", "potentially_free": " · evtl."}
BOOK_PLACE = "{name} buchen"
BOOK_IN_ROOM = "Platz in diesem Raum buchen"
BOOK_PLACE_PHONE = "{name} mit dem Handy buchen"
TOP_BUTTON = "Obere Taste:"
ACTION_LABEL = {"check_in": "Einchecken", "check_out": "Auschecken"}
NO_ACTION = "Keine Aktion"
HINT_SELECT = "▲ Platz ▼"
HINT_CANCEL = "Abbruch"
HINT_TAKE = "Belegen"
HINT_DURATION = "+ Dauer –"  # stacked top → bottom: "+" by the upper rocker half (up = +1 h)
HINT_CHECK_IN = "Einchecken"
HINT_END = "Beenden"

SINGLE_BOOKED = "gebucht · noch nicht da"
SINGLE_PRESENT = "anwesend ✓"
SINGLE_PRESS_CHECK_IN = "Taste drücken → einchecken"
SINGLE_PRESS_CHECK_OUT = "Taste: auschecken"
SINGLE_CONFIRM = "Wirklich auschecken?"
SINGLE_CONFIRM_NOTE = ("Das Büro wird für den Rest", "des Tages freigegeben.")
SINGLE_CONFIRM_AGAIN = "Nochmal drücken = Ja"
SINGLE_BOOK = "buchen"
SINGLE_HINT = {"check_in": "Einchecken ▸", "check_out": "Auschecken ▸"}

SUMMARY_FREE = "{free}/{total} frei"

TAKEN = ("booked", "checked_in")
NAME_SIZES = (52, 46, 40, 36, 32, 28, 26, 24, 22, 20, 18, 16, 14)
FREE_SIZES = (52, 44, 36, 30, 26, 22, 18, 14)


# --- meeting room (5.79") ---------------------------------------------------

MEETING_LEFT = 450
ACTION_HEIGHT = 86


def _pending(info) -> bool:
    """Free now, but the next booking's check-in window is open."""
    return info.state == "free" and info.reservation_id is not None


def _meeting_hints(screen, info):
    if _pending(info):
        return (HINT_CHECK_IN, "", HINT_REFRESH)
    if info.state == "free":
        if info.max_hours < 1:
            return ("", "", HINT_REFRESH)
        bottom = HINT_CANCEL if screen.mode == "select" else HINT_REFRESH
        return (HINT_TAKE, HINT_DURATION, bottom)
    if info.state in ("booked", "potentially_free") and info.reservation_id is not None:
        return (HINT_CHECK_IN, "", HINT_REFRESH)
    if info.state == "checked_in" and info.reservation_id is not None:
        return (HINT_END, "", HINT_REFRESH)
    return ("", "", HINT_REFRESH)


def _meeting_left(image, draw, view, info):
    _, height = image.size
    x0, box_w = 18, MEETING_LEFT - 36
    running = info.state == "checked_in"
    fg = WHITE if running else BLACK
    if running:
        draw.rectangle((0, 0, MEETING_LEFT - 1, height - 1), fill=BLACK)
    elif info.state in ("booked", "potentially_free"):
        dashed_vline(draw, MEETING_LEFT, 0, height, 3, BLACK)
    else:
        draw.rectangle((MEETING_LEFT, 0, MEETING_LEFT + 2, height - 1), fill=BLACK)
    top_f = font(15)
    top, _ = fit_text(draw, ROOM_MEETING.format(room=view.room_name), box_w, (15,), bold=False)
    draw.text((x0, 12), top, font=top_f, fill=fg)
    area_top = 12 + text_height(top_f) + 6
    bottom_y = height - 12

    if info.state == "free":
        qr = qr_image(info.qr_url, 96)
        if qr is not None:
            image.paste(qr, (MEETING_LEFT - 16 - qr.width, height - 14 - qr.height))
            draw.text((x0, bottom_y), BOOK_WITH_NAME, font=font(14), fill=fg, anchor="ld")
        big = font(84, True)
        lines = [(FREE, big)]
        if info.free_until is not None:
            lines.append((FREE_UNTIL.format(time=hhmm(info.free_until)), font(24, True)))
        y = area_top + 10
        for text, f in lines:
            draw.text((x0, y), text, font=f, fill=fg)
            y += text_height(f)
        return
    if info.state not in ("booked", "potentially_free", "checked_in"):
        closed, closed_f = fit_text(draw, CLOSED, box_w, (48, 40, 32))
        draw.text((x0, area_top + 30), closed, font=closed_f, fill=fg)
        return

    # booked / running: period line, title (largest), holder line.
    if running:
        period = RUNNING_UNTIL.format(time=hhmm(info.end)) if info.end else RUNNING
    elif info.start and info.end:
        period = BOOKED_PERIOD.format(start=hhmm(info.start), end=hhmm(info.end))
    else:
        period = BOOKED
    status = CHECKED_IN if running else NOT_CHECKED_IN
    title = info.title
    holder = info.holder
    if not title:
        title, holder = holder or (RUNNING if running else BOOKED), None
    bottom_f = font(16)
    suffix = f" · {status}"
    bottom = status
    if holder:
        room = box_w - draw.textlength(suffix, font=bottom_f)
        if room >= 60:
            name, _ = fit_text(draw, holder, room, (16,), bold=False, name=True)
            bottom = f"{name}{suffix}"
    draw.text((x0, bottom_y), bottom, font=bottom_f, fill=fg, anchor="ld")
    period_f = font(22)
    period, _ = fit_text(draw, period, box_w, (22,), bold=False)
    title_box = bottom_y - text_height(bottom_f) - 8 - (area_top + text_height(period_f) + 4)
    lines, f = fit_lines(draw, title, box_w, title_box, (40, 36, 32, 28, 24, 20), max_lines=2)
    total = text_height(period_f) + 4 + block_height(f, len(lines))
    free_space = bottom_y - text_height(bottom_f) - 8 - area_top
    y = area_top + max(0, (free_space - total) // 2)
    draw.text((x0, y), period, font=period_f, fill=fg)
    draw_lines(draw, x0, y + text_height(period_f) + 4, lines, f, fg)


def _meeting_action(draw, screen, info, x0, x1):
    """The top-button action in the top third of the right column."""
    inverted = False
    small = big = None
    if _pending(info):
        small, big, inverted = info.next_label, (CHECK_IN_ACTION, 22), True
    elif info.state == "free":
        if info.max_hours >= 1:
            hours = min(max(screen.hours, 1), info.max_hours)
            small, big, inverted = WITHOUT_LOGIN, (TAKE_HOURS.format(hours=hours), 22), True
        else:
            big = (TAKE_IMPOSSIBLE, 16)
    elif info.state in ("booked", "potentially_free") and info.reservation_id is not None:
        small = RELEASE_AT.format(time=hhmm(info.release_at)) if info.release_at else None
        big, inverted = (CHECK_IN_ACTION, 22), True
    elif info.state == "checked_in" and info.reservation_id is not None:
        big = (END_MEETING, 18)
    if inverted:
        draw.rectangle((x0, 0, x1 - 1, ACTION_HEIGHT - 1), fill=BLACK)
    draw.rectangle((x0, ACTION_HEIGHT, x1 - 1, ACTION_HEIGHT + 2), fill=BLACK)
    fg = WHITE if inverted else BLACK
    right = x1 - 10
    if big is None:
        return
    sizes = tuple(sorted({big[1], 18, 14}, reverse=True))
    big_text, big_f = fit_text(draw, big[0], x1 - x0 - 24, sizes)
    small_f = font(15)
    total = text_height(big_f) + (text_height(small_f) + 4 if small else 0)
    y = (ACTION_HEIGHT - total) // 2
    if small:
        small, _ = fit_text(draw, small, x1 - x0 - 24, (15,), bold=False)
        draw.text((right, y), small, font=small_f, fill=fg, anchor="ra")
        y += text_height(small_f) + 4
    draw.text((right, y), big_text, font=big_f, fill=fg, anchor="ra")


def _schedule(draw, info, x0, x1, top, bottom):
    head_f, slot_f = font(16, True), font(16)
    if info.state == "free":
        duration = info.max_hours >= 1 and not _pending(info)
        head = SCHEDULE_DURATION if duration else SCHEDULE_TODAY
    else:
        head = SCHEDULE_AFTER
    head, head_f = fit_text(draw, head, x1 - x0, (16, 15, 14, 13))
    draw.text((x0, top), head, font=head_f, fill=BLACK)
    y = top + text_height(head_f) + 4
    row_h = 24
    if not info.schedule:
        draw.text((x0, y + 2), SCHEDULE_EMPTY, font=slot_f, fill=BLACK)
        return
    for slot in info.schedule:
        if y + row_h > bottom:
            break
        times = f"{hhmm(slot.start)} – {hhmm(slot.end)}"
        draw.text((x0, y + 2), times, font=slot_f, fill=BLACK)
        is_free = slot.label == SLOT_FREE
        room = x1 - x0 - draw.textlength(times, font=slot_f) - 12
        label, f = fit_text(draw, slot.label, room, (16,), bold=is_free)
        draw.text((x1, y + 2), label, font=f, fill=BLACK, anchor="ra")
        draw.line((x0, y + row_h - 1, x1, y + row_h - 1), fill=BLACK, width=1)
        y += row_h


def meeting(image, draw, screen, panel):
    view, info = screen.view, screen.view.meeting
    if screen.mode == "confirm" and screen.confirm_text:
        draw_confirm(image, panel, screen, header=view.room_name,
                     note=TEXT_CONFIRM_MEETING_NOTE, any_button=False)
        return
    _, height = image.size
    _meeting_left(image, draw, view, info)
    x0, x1 = MEETING_LEFT + 3, content_right(panel)
    _meeting_action(draw, screen, info, x0, x1)
    stand_f = font(13)
    _schedule(draw, info, x0 + 14, x1 - 10, ACTION_HEIGHT + 11,
              height - text_height(stand_f) - 8)
    draw.text((x0 + 14, height - 6), stand(view), font=stand_f, fill=BLACK, anchor="ld")
    draw_hints(image, panel, _meeting_hints(screen, info))


# --- multi-desk office (5.79"; single offices on 5.79" too) -----------------

GRID_TOP = 50
GRID_GAP = 12
SIDE_W = 118
MAX_TILES = 8


def _tile_parts(draw, tile, box):
    """Header, footer and the box left for the main text of a desk tile."""
    x0, y0, x1, y1 = box
    pad = 9
    inner_w = x1 - x0 - 2 * pad
    small_f = font(13 if y1 - y0 > 110 else 12)
    name = clean(tile.name)
    head = name + TILE_STATE.get(tile.state, "")
    if draw.textlength(head, font=small_f) > inner_w:
        head = name + TILE_STATE_SHORT.get(tile.state, "")
    head, _ = fit_text(draw, head, inner_w, (small_f.size,), bold=False)
    foot = None
    if tile.until is not None and tile.state != "free":
        foot = FREE_UNTIL.format(time=hhmm(tile.until))
    elif tile.state == "free" and tile.free_note:
        foot = tile.free_note
    if foot:
        foot, _ = fit_text(draw, foot, inner_w, (small_f.size,), bold=False)
    top = y0 + pad - 2 + text_height(small_f) + 2
    bottom = y1 - pad + 2 - ((text_height(small_f) + 2) if foot else 0)
    return head, foot, small_f, inner_w, top, bottom


def _tile_main(draw, tile, inner_w, height, cap=None):
    """(lines, font) of the main text; ``cap`` limits the font size so all
    names in a grid share one size."""
    if tile.state == "free":
        return fit_lines(draw, FREE, inner_w, height, FREE_SIZES, max_lines=1)
    if tile.state == "closed":
        return fit_lines(draw, CLOSED_SHORT, inner_w, height, NAME_SIZES[4:], max_lines=1)
    sizes = tuple(s for s in NAME_SIZES if cap is None or s <= cap) or NAME_SIZES[-1:]
    return fit_lines(draw, tile.label or HIDDEN, inner_w, height, sizes, name=True, max_lines=2)


def _tile(draw, tile, box, selected, cap):
    x0, y0, x1, y1 = box
    taken = tile.state in TAKEN
    fg = WHITE if taken else BLACK
    if taken:
        draw.rectangle(box, fill=BLACK)
    elif tile.state == "potentially_free":
        dashed_rect(draw, box, 3, BLACK)
    else:
        draw.rectangle(box, outline=BLACK, width=3)
    if selected:
        draw.rectangle((x0 - 7, y0 - 7, x1 + 7, y1 + 7), outline=BLACK, width=4)
    pad = 9
    head, foot, small_f, inner_w, top, bottom = _tile_parts(draw, tile, box)
    draw.text((x0 + pad, y0 + pad - 2), head, font=small_f, fill=fg)
    if foot:
        draw.text((x0 + pad, y1 - pad + 2), foot, font=small_f, fill=fg, anchor="ld")
    lines, f = _tile_main(draw, tile, inner_w, bottom - top, cap)
    y = top + max(0, (bottom - top - block_height(f, len(lines))) // 2)
    draw_lines(draw, x0 + pad, y, lines, f, fg)


def _grid(count, side):
    if count <= 2:
        return 1, count
    if count <= 4:
        return (2, 2) if side else (1, count)
    return 2, 4


def _side_qr(image, draw, url, caption, box, bold=False):
    x0, y0, x1, y1 = box
    cap_f_size = 11
    cap_lines, cap_f = fit_lines(draw, caption, x1 - x0, 30, (cap_f_size,), bold=bold, max_lines=2)
    cap_h = block_height(cap_f, len(cap_lines))
    qr = qr_image(url, min(x1 - x0, y1 - y0 - cap_h - 4))
    if qr is None:
        draw_lines(draw, x0, (y0 + y1 - cap_h) // 2, cap_lines, cap_f, BLACK, align="center",
                   box_w=x1 - x0)
        return
    total = qr.height + 4 + cap_h
    y = y0 + (y1 - y0 - total) // 2
    image.paste(qr, (x0 + (x1 - x0 - qr.width) // 2, y))
    draw_lines(draw, x0, y + qr.height + 4, cap_lines, cap_f, BLACK, align="center",
               box_w=x1 - x0)


def _side_select(image, draw, tile, box):
    x0, y0, x1, y1 = box
    w = x1 - x0
    if tile.state == "free" and not tile.actionable:
        _side_qr(image, draw, tile.qr_url, BOOK_PLACE_PHONE.format(name=tile.name), box, bold=True)
        return
    name_f, f13, act_f = font(15, True), font(13), font(15, True)
    name, _ = fit_text(draw, tile.name, w, (15,))
    action = ACTION_LABEL.get(tile.actionable)
    parts = text_height(name_f) + 6 + text_height(f13)
    if action:
        parts += 6 + text_height(act_f) + 6
    y = y0 + (y1 - y0 - parts) // 2
    draw.text((x0, y), name, font=name_f, fill=BLACK)
    y += text_height(name_f) + 6
    if not action:
        draw.text((x0, y), NO_ACTION, font=f13, fill=BLACK)
        return
    draw.text((x0, y), TOP_BUTTON, font=f13, fill=BLACK)
    y += text_height(f13) + 6
    label, _ = fit_text(draw, action, w - 12, (15,))
    draw.rectangle((x0, y, x0 + min(w, draw.textlength(label, font=act_f) + 12),
                    y + text_height(act_f) + 6), fill=BLACK)
    draw.text((x0 + 6, y + 3), label, font=act_f, fill=WHITE)


def office(image, draw, screen, panel, *, single=False):
    view = screen.view
    tiles = view.desks
    _, height = image.size
    right = content_right(panel)
    selected = screen.selected if screen.mode == "select" and not single else None
    if selected is not None:
        selected = min(max(selected, 0), len(tiles) - 1)
    if screen.mode == "confirm" and screen.confirm_text:
        index = 0 if single else screen.selected
        valid = index is not None and 0 <= index < len(tiles)
        name = tiles[index].name if valid else view.room_name
        header = f"{view.room_name} · {name}" if not single else view.room_name
        draw_confirm(image, panel, screen, header=header,
                     note=TEXT_CONFIRM_DESK_NOTE.format(name=name), any_button=single)
        return

    # Window of at most 8 tiles; selection pages through the rest.
    start = (selected // MAX_TILES) * MAX_TILES if selected is not None else 0
    shown = tiles[start:start + MAX_TILES]
    hidden = len(tiles) - len(shown)
    free_tiles = [t for t in shown if t.state == "free"]
    free_total = sum(1 for t in tiles if t.state == "free")
    side = selected is not None or bool(free_tiles) or bool(view.room_qr_url and free_total)

    # Header.
    x0 = 14
    if selected is not None:
        right_text, right_f = OFFICE_POSITION.format(pos=selected + 1, total=len(tiles)), font(16)
        left = OFFICE_SELECT.format(room=view.room_name)
    else:
        free = free_total
        right_text = OFFICE_TAKEN if free == 0 else OFFICE_FREE.format(free=free, total=len(tiles))
        if single:
            right_text = OFFICE_TAKEN if free == 0 else SLOT_FREE
        if hidden:
            right_text = f"{OFFICE_MORE.format(count=hidden)}  ·  {right_text}"
        right_f = font(26, True)
        left = view.room_name
    header_right = right - 10
    draw.text((header_right, 36), right_text, font=right_f, fill=BLACK, anchor="rs")
    stand_f = font(13)
    stand_text = stand(view)
    room_w = (header_right - x0 - draw.textlength(right_text, font=right_f) - 24
              - draw.textlength(stand_text, font=stand_f) - 12)
    left, left_f = fit_text(draw, left, room_w, (20,))
    draw.text((x0, 36), left, font=left_f, fill=BLACK, anchor="ls")
    draw.text((x0 + draw.textlength(left, font=left_f) + 12, 36), stand_text, font=stand_f,
              fill=BLACK, anchor="ls")

    # Tiles.
    grid_right = right - 10 - ((SIDE_W + GRID_GAP) if side else 0)
    grid_bottom = height - 10
    rows, cols = _grid(len(shown), side)
    tile_w = (grid_right - x0 - (cols - 1) * GRID_GAP) / cols
    tile_h = (grid_bottom - GRID_TOP - (rows - 1) * GRID_GAP) / rows
    boxes = []
    for i in range(len(shown)):
        r, c = divmod(i, cols)
        bx = round(x0 + c * (tile_w + GRID_GAP))
        by = round(GRID_TOP + r * (tile_h + GRID_GAP))
        boxes.append((bx, by, round(bx + tile_w) - 1, round(by + tile_h) - 1))
    name_sizes = [
        _tile_main(draw, tile, parts[3], parts[5] - parts[4])[1].size
        for tile, box in zip(shown, boxes)
        if tile.state not in ("free", "closed")
        for parts in [_tile_parts(draw, tile, box)]
    ]
    cap = min(name_sizes) if name_sizes else None
    for i, (tile, box) in enumerate(zip(shown, boxes)):
        _tile(draw, tile, box, selected is not None and start + i == selected, cap)

    # Side: QR to book, or what the top button does in selection mode.
    if side:
        side_box = (right - 10 - SIDE_W, GRID_TOP, right - 10, grid_bottom)
        if selected is not None:
            _side_select(image, draw, tiles[selected], side_box)
        elif free_tiles and (free_total == 1 or not view.room_qr_url):
            only = free_tiles[0]
            _side_qr(image, draw, only.qr_url, BOOK_PLACE.format(name=only.name), side_box)
        else:
            _side_qr(image, draw, view.room_qr_url, BOOK_IN_ROOM, side_box)

    if single:
        draw_hints(image, panel, SINGLE_HINT.get(tiles[0].actionable, HINT_REFRESH))
    elif selected is not None:
        action = ACTION_LABEL.get(tiles[selected].actionable, "")
        draw_hints(image, panel, (action, HINT_SELECT, HINT_CANCEL))
    else:
        # The rocker starts the selection once a place can be checked in/out.
        rocker = HINT_SELECT if any(t.actionable for t in tiles) else ""
        draw_hints(image, panel, ("", rocker, HINT_REFRESH))


# --- single office ----------------------------------------------------------

def single(image, draw, screen, panel):
    if panel != "2.1":
        office(image, draw, screen, panel, single=True)
        return
    view, tile = screen.view, screen.view.desks[0]
    _, height = image.size
    right = content_right(panel)
    x0 = 8
    box_w = right - 6 - x0
    head_f, f11 = font(11, True), font(11)
    confirm = screen.mode == "confirm" and screen.confirm_text
    present = tile.state == "checked_in" and not confirm
    fg = WHITE if present else BLACK
    if present:
        draw.rectangle((0, 0, right - 1, height - 1), fill=BLACK)

    if tile.state == "free" and not confirm:
        qr = qr_image(tile.qr_url, 76)
        text_w = box_w - ((qr.width + 6) if qr is not None else 0)
        head, _ = fit_text(draw, view.room_name, text_w, (11,))
        draw.text((x0, 6), head, font=head_f, fill=BLACK)
        free_lines, free_f = fit_lines(draw, FREE, text_w, 50, (40, 32, 24), max_lines=1)
        draw_lines(draw, x0, 26, free_lines, free_f, BLACK)
        if tile.free_note:
            note, _ = fit_text(draw, tile.free_note, text_w, (11,), bold=False)
            draw.text((x0, 26 + text_height(free_f) + 2), note, font=f11, fill=BLACK)
        if tile.actionable == "check_in":
            press, press_f = fit_text(draw, SINGLE_PRESS_CHECK_IN, text_w, (11, 9))
            draw.text((x0, height - 6), press, font=press_f, fill=BLACK, anchor="ld")
        if qr is not None:
            cap_f = font(9)
            total = qr.height + 2 + text_height(cap_f)
            qx = right - 6 - qr.width
            qy = (height - total) // 2
            image.paste(qr, (qx, qy))
            draw.text((qx + qr.width / 2, qy + qr.height + 2), SINGLE_BOOK, font=cap_f,
                      fill=BLACK, anchor="ma")
        draw_hints(image, panel, SINGLE_HINT.get(tile.actionable, HINT_REFRESH))
        return

    head, _ = fit_text(draw, view.room_name, box_w, (11,))
    draw.text((x0, 6), head, font=head_f, fill=fg)
    rule_y = 6 + text_height(head_f) + 2
    draw.rectangle((x0, rule_y, right - 6, rule_y + 1), fill=fg)
    y = rule_y + 6
    bottom_y = height - 6
    if confirm:
        draw.text((x0, y), fit_text(draw, SINGLE_CONFIRM, box_w, (15, 13))[0],
                  font=font(15, True), fill=BLACK)
        y += text_height(font(15, True)) + 2
        for line in SINGLE_CONFIRM_NOTE:
            draw.text((x0, y), line, font=f11, fill=BLACK)
            y += line_step(f11) + 2
        draw.text((x0, bottom_y), SINGLE_CONFIRM_AGAIN, font=head_f, fill=BLACK, anchor="ld")
        draw_hints(image, panel, HINT_YES_ANY)
        return
    if tile.state == "closed":
        draw.text((x0, y + 10), CLOSED_SHORT, font=font(22, True), fill=fg)
        draw_hints(image, panel, HINT_REFRESH)
        return

    sub = SINGLE_PRESENT if present else SINGLE_BOOKED
    if tile.until is not None:
        sub = f"{sub} · {FREE_UNTIL.format(time=hhmm(tile.until))}"
    sub, _ = fit_text(draw, sub, box_w, (11,), bold=False)
    draw.text((x0, y), sub, font=f11, fill=fg)
    y += text_height(f11) + 2
    footer = None
    if tile.actionable == "check_in":
        footer = (SINGLE_PRESS_CHECK_IN, head_f)
    elif tile.actionable == "check_out":
        footer = (SINGLE_PRESS_CHECK_OUT, f11)
    name_bottom = bottom_y - (text_height(f11) + 4 if footer else 0)
    lines, f = fit_lines(draw, tile.label or HIDDEN, box_w, name_bottom - y,
                         (22, 20, 18, 16, 14), name=True, max_lines=2)
    draw_lines(draw, x0, y, lines, f, fg)
    if footer:
        draw.text((x0, bottom_y), footer[0], font=footer[1], fill=fg, anchor="ld")
    draw_hints(image, panel, SINGLE_HINT.get(tile.actionable, HINT_REFRESH))


# --- 2.1" summary of a meeting room or multi-desk office --------------------

def summary(image, draw, screen, panel):
    view = screen.view
    _, height = image.size
    right = content_right(panel)
    x0 = 8
    box_w = right - 6 - x0
    head_f, stand_f = font(11, True), font(9)
    stand_text = stand(view)
    head, _ = fit_text(draw, view.room_name, box_w - draw.textlength(stand_text, font=stand_f) - 6,
                       (11,))
    draw.text((x0, 6), head, font=head_f, fill=BLACK)
    draw.text((right - 6, 6 + head_f.getmetrics()[0]), stand_text, font=stand_f, fill=BLACK,
              anchor="rs")
    rule_y = 6 + text_height(head_f) + 2
    draw.rectangle((x0, rule_y, right - 6, rule_y + 1), fill=BLACK)
    top = rule_y + 6

    info = view.meeting
    qr_url = None
    sub = None
    if view.kind == "meeting" and info is not None:
        if info.state == "free":
            big, qr_url = FREE, info.qr_url
            if info.free_until:
                sub = FREE_UNTIL.format(time=hhmm(info.free_until))
        elif info.state in ("booked", "potentially_free", "checked_in"):
            big = RUNNING if info.state == "checked_in" else BOOKED
            if info.end:
                sub = FREE_UNTIL.format(time=hhmm(info.end))
        else:
            big = CLOSED_SHORT
    else:
        free = sum(1 for t in view.desks if t.state == "free")
        if free:
            big = SUMMARY_FREE.format(free=free, total=len(view.desks))
            qr_url = view.room_qr_url
        else:
            big = OFFICE_TAKEN
    qr = qr_image(qr_url, 76) if qr_url else None
    if qr is not None:
        qy = top + (height - 4 - top - qr.height) // 2
        image.paste(qr, (right - 6 - qr.width, qy))
    text_w = box_w - ((qr.width + 6) if qr is not None else 0)
    lines, f = fit_lines(draw, big, text_w, 44, (36, 30, 26, 22, 18), max_lines=1)
    sub_f = font(15, True)
    total = block_height(f, 1) + ((text_height(sub_f) + 2) if sub else 0)
    y = top + max(0, (height - 6 - top - total) // 2)
    draw_lines(draw, x0, y, lines, f, BLACK)
    if sub:
        sub, _ = fit_text(draw, sub, text_w, (15, 13))
        draw.text((x0, y + block_height(f, 1) + 2), sub, font=sub_f, fill=BLACK)
    draw_hints(image, panel, ("", "", HINT_REFRESH))


# --- item signs (spec §6.5) -------------------------------------------------

ITEM_FREE = "Frei"
ITEM_FREE_FROM = "ab {time} reserviert"
ITEM_NO_RESERVATION = "heute keine Reservierung"
ITEM_RESERVED = "Reserviert {start}–{end}"
ITEM_LATE = "Verspätet"
ITEM_LATE_SINCE = "seit {minutes} Min. nicht gestartet"
ITEM_RELEASE_AT = "Freigabe um {time}"
ITEM_IN_USE = "In Benutzung bis {time}"
ITEM_CLOSED = "Geschlossen"
ITEM_OUT_OF_SERVICE = "Außer Betrieb"
ITEM_CODE = "Code {code}"
ITEM_SLOT = "{start}–{end}"
ITEM_LEFT = 460  # 5.79": state column | later reservations


def _clock(dt, now) -> str:
    """HH:MM, with the date when ``dt`` is not today (multi-day bookings)."""
    local, today = timezone.localtime(dt, TZ), timezone.localtime(now, TZ).date()
    return hhmm(dt) if local.date() == today else f"{local:%d.%m.} {local:%H:%M}"


def _item_texts(view):
    """``(headline, sub lines, code line or None)`` of the item sign."""
    slot, now = view.slot, view.now
    code = ITEM_CODE.format(code=slot.code) if slot is not None and slot.code else None
    if view.state == "free":
        sub = (ITEM_FREE_FROM.format(time=_clock(view.next_start, now))
               if view.next_start else ITEM_NO_RESERVATION)
        return ITEM_FREE, [sub], None
    if view.state == "reserved":
        return ITEM_RESERVED.format(start=_clock(slot.start, now),
                                    end=_clock(slot.end, now)), [], code
    if view.state == "late":
        subs = [ITEM_LATE_SINCE.format(minutes=view.late_minutes or 0)]
        if view.release_at is not None:
            subs.append(ITEM_RELEASE_AT.format(time=_clock(view.release_at, now)))
        return ITEM_LATE, subs, code
    if view.state == "in_use":
        return ITEM_IN_USE.format(time=_clock(slot.end, now)), [], code
    if view.state == "closed":
        return ITEM_CLOSED, ([opens_line(view.next_open, now)] if view.next_open else []), None
    return ITEM_OUT_OF_SERVICE, [], None


def _truncate_start(draw, text, box_w, f):
    """Longest suffix of ``text`` behind "…" that fits ``box_w`` ("" if none):
    an inventory number tells units apart by its end."""
    text = clean(text)
    if draw.textlength(text, font=f) <= box_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:  # largest n with "…" + suffix(n) fitting
        mid = (lo + hi + 1) // 2
        if draw.textlength(ELLIPSIS + text[-mid:].lstrip(), font=f) <= box_w:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return ELLIPSIS if draw.textlength(ELLIPSIS, font=f) <= box_w else ""
    return ELLIPSIS + text[-lo:].lstrip()


def _item_header_texts(draw, view, box_w, head_f, inv_f):
    """(title, inventory number) for the header: the number has priority
    (up to 60 % of the width, shortened from the start), the title takes the
    rest."""
    inv = _truncate_start(draw, view.inventory_number, box_w * 0.6, inv_f)
    inv_w = draw.textlength(inv, font=inv_f)
    title = truncate(draw, view.title, box_w - inv_w - 10, head_f)
    return title, inv


def _item_header(draw, view, x0, x1, y, head_f, inv_f, fg):
    """Product title left, inventory number right; returns the rule's y."""
    title, inv = _item_header_texts(draw, view, x1 - x0, head_f, inv_f)
    draw.text((x0, y), title, font=head_f, fill=fg)
    draw.text((x1, y + head_f.getmetrics()[0]), inv, font=inv_f, fill=fg, anchor="rs")
    rule_y = y + text_height(head_f) + 2
    draw.rectangle((x0, rule_y, x1, rule_y + 1), fill=fg)
    return rule_y + 2


def _item_main(draw, view, x0, box_w, top, bottom, sizes, sub_f, fg):
    """Headline (white on a black bar while late) and sub lines."""
    big, subs, _ = _item_texts(view)
    sub_lines = [fit_text(draw, s, box_w, (sub_f.size,), bold=False)[0] for s in subs]
    gap = max(2, sub_f.size // 4)
    subs_h = len(sub_lines) * (line_step(sub_f) + gap)
    late = view.state == "late"
    pad = 4 if late else 0
    lines, f = fit_lines(draw, big, box_w - 2 * pad, bottom - top - subs_h - 2 * pad, sizes,
                         max_lines=2)
    big_h = block_height(f, len(lines))
    total = big_h + 2 * pad + subs_h
    y = top + max(0, (bottom - top - total) // 2)
    if late:
        width = max(draw.textlength(line, font=f) for line in lines)
        draw.rectangle((x0, y, x0 + round(width) + 2 * pad, y + big_h + 2 * pad + 2), fill=fg)
        draw_lines(draw, x0 + pad, y + pad, lines, f, WHITE if fg == BLACK else BLACK)
    else:
        draw_lines(draw, x0, y, lines, f, fg)
    y += big_h + 2 * pad + gap * 2
    for line in sub_lines:
        draw.text((x0, y), line, font=sub_f, fill=fg)
        y += line_step(sub_f) + gap


def _item_footer(draw, view, x0, x1, baseline, code_f, stand_f, fg):
    _, _, code = _item_texts(view)
    stand_text = stand(view)
    stand_w = draw.textlength(stand_text, font=stand_f) if stand_text else 0
    if code:
        draw.text((x0, baseline), truncate(draw, code, x1 - x0 - stand_w - 8, code_f),
                  font=code_f, fill=fg, anchor="ls")
    if stand_text:
        draw.text((x1, baseline), stand_text, font=stand_f, fill=fg, anchor="rs")


def item_small(image, draw, screen, panel):
    """2.1" item sign: header, state, sub lines, booking code and "Stand"."""
    view = screen.view
    _, height = image.size
    right = content_right(panel)
    x0, x1 = 8, right - 6
    fg = WHITE if view.state == "in_use" else BLACK
    if fg == WHITE:
        draw.rectangle((0, 0, right - 1, height - 1), fill=BLACK)
    top = _item_header(draw, view, x0, x1, 5, font(11, True), font(9), fg) + 4
    code_f = font(11, True)
    baseline = height - 6
    bottom = baseline - code_f.getmetrics()[0] - 4
    _item_main(draw, view, x0, x1 - x0, top, bottom, (28, 24, 20, 17, 15, 13), font(11), fg)
    _item_footer(draw, view, x0, x1, baseline, code_f, font(9), fg)
    draw_hints(image, panel, HINT_REFRESH)


def item_wide(image, draw, screen, panel):
    """5.79" item sign: like the small one plus today's later reservations
    (times and codes only) in a right-hand column."""
    view = screen.view
    _, height = image.size
    right = content_right(panel)
    x0, x1 = 22, right - 14
    fg = WHITE if view.state == "in_use" else BLACK
    if fg == WHITE:
        draw.rectangle((0, 0, right - 1, height - 1), fill=BLACK)
    top = _item_header(draw, view, x0, x1, 14, font(22, True), font(18), fg) + 10
    code_f = font(24, True)
    baseline = height - 16
    bottom = baseline - code_f.getmetrics()[0] - 8
    show_list = view.state != "out_of_service"
    left_w = (ITEM_LEFT - x0) if show_list else (x1 - x0)
    _item_main(draw, view, x0, left_w, top, bottom, (64, 56, 48, 40, 34, 28, 24), font(22), fg)
    _item_footer(draw, view, x0, x1, baseline, code_f, font(13), fg)
    if show_list:
        lx = ITEM_LEFT + 20
        draw.rectangle((ITEM_LEFT + 8, top, ITEM_LEFT + 9, bottom), fill=fg)
        head_f, row_f, code_row_f = font(18, True), font(19, True), font(19)
        draw.text((lx, top), SCHEDULE_AFTER, font=head_f, fill=fg)
        y = top + text_height(head_f) + 8
        if not view.upcoming:
            empty, empty_f = fit_text(draw, SCHEDULE_EMPTY, x1 - lx, (20, 16), bold=False)
            draw.text((lx, y), empty, font=empty_f, fill=fg)
        for slot in view.upcoming:
            times = ITEM_SLOT.format(start=_clock(slot.start, view.now),
                                     end=_clock(slot.end, view.now))
            draw.text((lx, y), times, font=row_f, fill=fg)
            tx = lx + draw.textlength(times, font=row_f) + 10
            if slot.code:
                draw.text((tx, y), truncate(draw, slot.code, x1 - tx, code_row_f),
                          font=code_row_f, fill=fg)
            y += line_step(row_f) + 10
    draw_hints(image, panel, HINT_REFRESH)
