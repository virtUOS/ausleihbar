# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Door display frames: a ``Screen`` rendered as a 1-bit Pillow image.

The device only shows what the server draws. This module holds the drawing
primitives (fonts, text fitting, QR codes, hint column, banner, confirm
screen), the frame encoding and the dispatch; the room layouts live in
``door_render_layouts``. Output is deterministic (same ``Screen`` → same
bytes), so frame ETags stay stable while nothing changes.
"""
import hashlib
from contextvars import ContextVar
from functools import lru_cache

import qrcode
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from .hours import TZ

SIZES = {"2.1": (250, 122), "5.79": (792, 272)}
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HINT_WIDTH = {"2.1": 18, "5.79": 20}

BLACK = 0
WHITE = 255
ELLIPSIS = "…"
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

# User-facing literals (German UI of the sign).
TEXT_PAIRING = "Kopplungscode"
TEXT_EMPTY = "Kein buchbarer Platz"
TEXT_CLOSED = "Geschlossen"
TEXT_STAND = "Stand {time}"
TEXT_OPENS = "Öffnet {day} {time}"
TEXT_FIRST_BOOKING = "Erste Buchung: {start}–{end} {label}"
TEXT_TODAY = "heute"
TEXT_TOMORROW = "morgen"
TEXT_CONFIRM_YES_NO = "Obere Taste = Ja · untere Taste = Nein"
TEXT_CONFIRM_AGAIN = "Nochmal drücken = Ja"
TEXT_CONFIRM_DESK_NOTE = "{name} wird für den Rest des Tages freigegeben."
TEXT_CONFIRM_MEETING_NOTE = "Die restliche Zeit wird freigegeben."
HINT_YES = "Ja"
HINT_YES_ANY = "Ja ▸"
HINT_NO = "Nein"
HINT_REFRESH = "↻"


# Whether the current ``render`` call draws "Stand HH:MM" (see ``render``).
_STAMP: ContextVar[bool] = ContextVar("door_render_stamp", default=True)


# --- fonts and time ---------------------------------------------------------

@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def hhmm(dt) -> str:
    return f"{timezone.localtime(dt, TZ):%H:%M}"


def stand(view) -> str:
    """"Stand HH:MM", or "" while rendering without the stamp."""
    return TEXT_STAND.format(time=hhmm(view.now)) if _STAMP.get() else ""


def text_height(f) -> int:
    ascent, descent = f.getmetrics()
    return ascent + descent


def line_step(f) -> int:
    """Distance between baselines of wrapped lines (tighter than the metrics)."""
    return round(f.size * 1.1)


# --- text fitting -----------------------------------------------------------

def clean(text) -> str:
    """One line: user texts (comments, names) may hold newlines or tabs,
    which Pillow cannot measure; collapse all whitespace to single spaces."""
    return " ".join(str(text or "").split())


def short_name(text: str) -> str | None:
    """``"Jana Hoffmann"`` → ``"J. Hoffmann"`` (None for single words)."""
    parts = text.split()
    if len(parts) < 2 or not parts[0][:1].isalpha():
        return None
    return f"{parts[0][0]}. {' '.join(parts[1:])}"


def truncate(draw, text: str, box_w: float, f) -> str:
    """Longest prefix of ``text`` plus "…" that fits ``box_w`` ("" if none)."""
    text = clean(text)
    if draw.textlength(text, font=f) <= box_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:  # largest n with prefix(n) + "…" fitting
        mid = (lo + hi + 1) // 2
        if draw.textlength(text[:mid].rstrip() + ELLIPSIS, font=f) <= box_w:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0 and draw.textlength(ELLIPSIS, font=f) > box_w:
        return ""
    return text[:lo].rstrip() + ELLIPSIS


def fit_text(draw, text: str, box_w: float, font_sizes, *, bold: bool = True, name: bool = False):
    """Fit one line into ``box_w``: the largest size of ``font_sizes`` that
    fits, then (names only) the short form "J. Hoffmann", then truncation
    with "…" at the smallest size. Returns ``(text, font)``."""
    text = clean(text)
    for size in font_sizes:
        f = font(size, bold)
        if draw.textlength(text, font=f) <= box_w:
            return text, f
    short = short_name(text) if name else None
    if short:
        for size in font_sizes:
            f = font(size, bold)
            if draw.textlength(short, font=f) <= box_w:
                return short, f
    f = font(font_sizes[-1], bold)
    return truncate(draw, short or text, box_w, f), f


def wrap(draw, text: str, f, box_w: float) -> list[str]:
    """Greedy word wrap (a single over-long word stays on its own line)."""
    lines: list[str] = []
    for word in text.split():
        if lines and draw.textlength(f"{lines[-1]} {word}", font=f) <= box_w:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines or [""]


def block_height(f, count: int) -> int:
    return (count - 1) * line_step(f) + text_height(f)


def fit_lines(draw, text, box_w, box_h, font_sizes, *, bold=True, name=False, max_lines=2):
    """Fit ``text`` into a box on up to ``max_lines`` lines, largest size
    first. Names try one line, then two, then the short form; the last
    resort truncates the last line with "…". Returns ``(lines, font)``."""
    for size in font_sizes:
        f = font(size, bold)
        allowed = min(max_lines, max(1, (box_h - text_height(f)) // line_step(f) + 1))
        if block_height(f, 1) > box_h:
            continue
        lines = wrap(draw, text, f, box_w)
        if len(lines) <= allowed and all(draw.textlength(l, font=f) <= box_w for l in lines):
            return lines, f
    short = short_name(text) if name else None
    if short:
        for size in font_sizes:
            f = font(size, bold)
            if block_height(f, 1) <= box_h and draw.textlength(short, font=f) <= box_w:
                return [short], f
    f = font(font_sizes[-1], bold)
    allowed = min(max_lines, max(1, (box_h - text_height(f)) // line_step(f) + 1))
    lines = wrap(draw, short or text, f, box_w)
    head, rest = lines[: allowed - 1], " ".join(lines[allowed - 1:])
    out = [truncate(draw, line, box_w, f) for line in head]
    if rest:
        out.append(truncate(draw, rest, box_w, f))
    return out or [""], f


def draw_lines(draw, x, y, lines, f, fill, *, align="left", box_w=0):
    for i, line in enumerate(lines):
        lx = x
        if align == "center":
            lx = x + (box_w - draw.textlength(line, font=f)) / 2
        elif align == "right":
            lx = x + box_w - draw.textlength(line, font=f)
        draw.text((round(lx), y + i * line_step(f)), line, font=f, fill=fill)


# --- shapes -----------------------------------------------------------------

def dashed_hline(draw, x0, x1, y, width, fill, dash=8, gap=6):
    x = x0
    while x < x1:
        draw.rectangle((x, y, min(x + dash, x1) - 1, y + width - 1), fill=fill)
        x += dash + gap


def dashed_vline(draw, x, y0, y1, width, fill, dash=8, gap=6):
    y = y0
    while y < y1:
        draw.rectangle((x, y, x + width - 1, min(y + dash, y1) - 1), fill=fill)
        y += dash + gap


def dashed_rect(draw, box, width, fill):
    x0, y0, x1, y1 = box
    dashed_hline(draw, x0, x1 + 1, y0, width, fill)
    dashed_hline(draw, x0, x1 + 1, y1 - width + 1, width, fill)
    dashed_vline(draw, x0, y0, y1 + 1, width, fill)
    dashed_vline(draw, x1 - width + 1, y0, y1 + 1, width, fill)


@lru_cache(maxsize=64)
def qr_image(url: str, max_px: int, min_module: int = 2) -> Image.Image | None:
    """Black-on-white QR code with an integer module size (None if the code
    would need modules smaller than ``min_module`` px to fit ``max_px``)."""
    code = qrcode.QRCode(border=1, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    code.add_data(url)
    code.make(fit=True)
    matrix = code.get_matrix()
    modules = len(matrix)
    box = max_px // modules
    if box < min_module:
        return None
    image = Image.new("1", (modules, modules), WHITE)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                image.putpixel((x, y), BLACK)
    return image.resize((modules * box, modules * box), Image.Resampling.NEAREST)


# --- shared frame parts -----------------------------------------------------

def content_right(panel: str) -> int:
    """First x of the hint column."""
    return SIZES[panel][0] - HINT_WIDTH[panel]


def _vertical_label(text: str, f, max_len: int) -> Image.Image:
    probe = ImageDraw.Draw(Image.new("1", (1, 1), WHITE))
    text = truncate(probe, text, max_len, f)
    w = max(1, round(probe.textlength(text, font=f)))
    h = text_height(f)
    label = Image.new("1", (w, h), WHITE)
    ImageDraw.Draw(label).text((0, 0), text, font=f, fill=BLACK)
    return label.transpose(Image.Transpose.ROTATE_270)  # reads top → bottom


def _upright(text: str, f) -> Image.Image:
    probe = ImageDraw.Draw(Image.new("1", (1, 1), WHITE))
    x0, y0, x1, y1 = probe.textbbox((0, 0), text, font=f)
    label = Image.new("1", (max(1, x1 - x0), max(1, y1 - y0)), WHITE)
    ImageDraw.Draw(label).text((-x0, -y0), text, font=f, fill=BLACK)
    return label


def _hint_label(text: str, panel: str, max_len: float) -> Image.Image:
    """One hint, stacked top → bottom: words rotated (reading top → bottom),
    symbols (▲ ▼ ▸ – + ↻) kept upright so arrows point the right way."""
    small = panel == "2.1"
    if len(text) == 1:
        return _upright(text, font(14 if small else 16, True))
    word_f = font(9 if small else 10, True)
    symbol_f = font(10 if small else 12, True)
    parts = text.split()
    symbols = [_upright(p, symbol_f) for p in parts if len(p) == 1 and not p.isalnum()]
    words_len = max_len - sum(s.height + 3 for s in symbols)
    pieces = []
    for part in parts:
        if len(part) == 1 and not part.isalnum():
            pieces.append(symbols.pop(0))
        else:
            pieces.append(_vertical_label(part, word_f, words_len))
    label = Image.new(
        "1", (max(p.width for p in pieces), sum(p.height for p in pieces) + 3 * (len(pieces) - 1)),
        WHITE,
    )
    y = 0
    for piece in pieces:
        label.paste(piece, ((label.width - piece.width) // 2, y))
        y += piece.height + 3
    return label


def draw_hints(image, panel: str, labels) -> None:
    """Right-edge hint column. ``labels`` is a 3-tuple (top button, rocker,
    bottom button) or one string shown centred for "any button"."""
    width, height = image.size
    x0 = content_right(panel)
    draw = ImageDraw.Draw(image)
    draw.rectangle((x0, 0, width - 1, height - 1), fill=WHITE)
    draw.rectangle((x0, 0, x0 + 1, height - 1), fill=BLACK)
    if isinstance(labels, str):
        slots = [(labels, height / 2, height - 8)]
    else:
        slots = [
            (label, height * (2 * i + 1) / 6, height / 3 - 6) for i, label in enumerate(labels)
        ]
    for label, center, max_len in slots:
        if not label:
            continue
        hint = _hint_label(label, panel, max_len)
        lx = x0 + 2 + (HINT_WIDTH[panel] - 2 - hint.width) // 2
        image.paste(hint, (lx, round(center - hint.height / 2)))


def draw_banner(image, panel: str, message: str) -> None:
    """A prominent black banner over the layout (e.g. "Eingecheckt ✓")."""
    draw = ImageDraw.Draw(image)
    _, height = image.size
    right = content_right(panel)
    if panel == "2.1":
        max_w, box_h, sizes, pad = right - 16, 46, (22, 18, 15, 12), 12
    else:
        max_w, box_h, sizes, pad = 600, 88, (44, 38, 32, 26, 22), 32
    text, f = fit_text(draw, message, max_w - 2 * pad, sizes)
    box_w = min(max_w, round(draw.textlength(text, font=f)) + 2 * pad)
    x0 = (right - box_w) // 2
    y0 = (height - box_h) // 2
    draw.rectangle((x0 - 5, y0 - 5, x0 + box_w + 4, y0 + box_h + 4), fill=WHITE)
    draw.rectangle((x0, y0, x0 + box_w - 1, y0 + box_h - 1), fill=BLACK)
    draw.text((x0 + box_w / 2, y0 + box_h / 2), text, font=f, fill=WHITE, anchor="mm")


def draw_confirm(image, panel: str, screen, *, header: str, note: str, any_button: bool):
    """The 5.79" confirm screen (replaces the whole layout)."""
    draw = ImageDraw.Draw(image)
    _, height = image.size
    x0, x1 = 22, content_right(panel) - 12
    box_w = x1 - x0
    top_f = font(16)
    head, _ = fit_text(draw, header, box_w - 90, (16,), bold=False)
    draw.text((x0, 14), head, font=top_f, fill=BLACK)
    draw.text((x1, 14 + top_f.getmetrics()[0]), stand(screen.view), font=font(11), fill=BLACK,
              anchor="rs")
    bottom = TEXT_CONFIRM_AGAIN if any_button else TEXT_CONFIRM_YES_NO
    bottom_f = font(16, True)
    bottom_y = height - 14 - text_height(bottom_f)
    draw.text((x0, bottom_y), bottom, font=bottom_f, fill=BLACK)
    note_lines, note_f = fit_lines(draw, note, box_w, 46, (18, 16, 14), bold=False)
    area_top, area_bottom = 14 + text_height(top_f) + 8, bottom_y - 8
    title_h = area_bottom - area_top - block_height(note_f, len(note_lines)) - 8
    lines, f = fit_lines(
        draw, screen.confirm_text or "", box_w, title_h, (40, 36, 32, 28, 24, 20)
    )
    total = block_height(f, len(lines)) + 8 + block_height(note_f, len(note_lines))
    y = area_top + (area_bottom - area_top - total) // 2
    draw_lines(draw, x0, y, lines, f, BLACK)
    y += block_height(f, len(lines)) + 8
    draw_lines(draw, x0, y, note_lines, note_f, BLACK)
    draw_hints(image, panel, HINT_YES_ANY if any_button else (HINT_YES, "", HINT_NO))


# --- whole frames -----------------------------------------------------------

def _canvas(panel: str):
    if panel not in SIZES:
        raise ValueError(f"unknown panel {panel!r}")
    image = Image.new("1", SIZES[panel], WHITE)
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    return image, draw


def _centered_message(panel, title, lines=(), now_text=None) -> Image.Image:
    image, draw = _canvas(panel)
    _, height = image.size
    right = content_right(panel)
    small = panel == "2.1"
    box_w = right - (16 if small else 48)
    title_lines, title_f = fit_lines(
        draw, title, box_w, (60 if not lines else 34) if small else 110,
        (24, 20, 16, 13) if small else (56, 48, 40, 32, 26),
    )
    line_f = font(11 if small else 20)
    fitted = []
    for line in lines:
        fitted += fit_lines(draw, line, box_w, 2 * line_step(line_f) + 4, (line_f.size,),
                            bold=False)[0]
    gap = 6 if small else 14
    total = block_height(title_f, len(title_lines))
    if fitted:
        total += gap + block_height(line_f, len(fitted))
    x0 = (right - box_w) // 2
    y = (height - total) // 2
    draw_lines(draw, x0, y, title_lines, title_f, BLACK, align="center", box_w=box_w)
    if fitted:
        y += block_height(title_f, len(title_lines)) + gap
        draw_lines(draw, x0, y, fitted, line_f, BLACK, align="center", box_w=box_w)
    if now_text and _STAMP.get():
        stand_f = font(9 if small else 11)
        draw.text((right - 4, height - 3), now_text, font=stand_f, fill=BLACK, anchor="rd")
    draw_hints(image, panel, ("", "", HINT_REFRESH))
    return image


def render_message(title: str, panel: str, lines=(), now=None) -> Image.Image:
    """A centred notice ("Kein buchbarer Platz", "Geschlossen" …)."""
    now_text = TEXT_STAND.format(time=hhmm(now)) if now else None
    return _centered_message(panel, title, lines, now_text)


def render_pairing(code: str, panel: str) -> Image.Image:
    """The pairing screen: "Kopplungscode" and the code as ``XXXX-XXXX``."""
    image, draw = _canvas(panel)
    _, height = image.size
    right = content_right(panel)
    small = panel == "2.1"
    shown = f"{code[:4]}-{code[4:]}" if len(code) == 8 else code
    label_f = font(14 if small else 28)
    box_w = right - (12 if small else 48)
    code_text, code_f = fit_text(
        draw, shown, box_w, (40, 34, 28, 22) if small else (96, 84, 72, 60, 48)
    )
    gap = 6 if small else 16
    total = text_height(label_f) + gap + text_height(code_f)
    y = (height - total) // 2
    draw.text((right / 2, y), TEXT_PAIRING, font=label_f, fill=BLACK, anchor="ma")
    draw.text((right / 2, y + text_height(label_f) + gap), code_text, font=code_f, fill=BLACK,
              anchor="ma")
    draw_hints(image, panel, ("", "", HINT_REFRESH))
    return image


def _closed_lines(view) -> list[str]:
    lines = []
    if view.next_open is not None:
        opening = timezone.localtime(view.next_open, TZ)
        today = timezone.localtime(view.now, TZ).date()
        delta = (opening.date() - today).days
        day = {0: TEXT_TODAY, 1: TEXT_TOMORROW}.get(delta, WEEKDAYS[opening.weekday()])
        lines.append(TEXT_OPENS.format(day=day, time=f"{opening:%H:%M}"))
    if view.next_booking is not None:
        slot = view.next_booking
        lines.append(TEXT_FIRST_BOOKING.format(
            start=hhmm(slot.start), end=hhmm(slot.end), label=slot.label,
        ))
    return lines


def render(screen, panel: str, *, stamp: bool = True) -> Image.Image:
    """The frame for ``screen`` on ``panel`` (mode "1", exact panel size).
    ``stamp=False`` leaves out "Stand HH:MM": that render is the basis of
    the ETag, so the panel only redraws when the content changes."""
    token = _STAMP.set(stamp)
    try:
        return _render(screen, panel)
    finally:
        _STAMP.reset(token)


def _render(screen, panel: str) -> Image.Image:
    from . import door_render_layouts as layouts

    view = screen.view
    degenerate = not view.desks and (view.kind != "meeting" or view.meeting is None)
    if view.kind == "empty" or (view.kind != "closed" and degenerate):
        image = render_message(TEXT_EMPTY, panel, now=view.now)
    elif view.kind == "closed":
        image = render_message(TEXT_CLOSED, panel, _closed_lines(view), now=view.now)
    else:
        image, draw = _canvas(panel)
        if view.kind == "single":
            layouts.single(image, draw, screen, panel)
        elif panel == "2.1":
            layouts.summary(image, draw, screen, panel)
        elif view.meeting is not None:
            layouts.meeting(image, draw, screen, panel)
        else:
            layouts.office(image, draw, screen, panel)
    if screen.message:
        draw_banner(image, panel, screen.message)
    return image


# --- frame encoding ---------------------------------------------------------

_INVERT = bytes(255 - b for b in range(256))


def to_frame(image: Image.Image) -> bytes:
    """Raw 1-bit buffer: row-major, MSB = leftmost pixel, bit 1 = black,
    row stride ``ceil(width / 8)`` bytes (padding bits 0)."""
    if image.mode != "1":
        image = image.convert("1", dither=Image.Dither.NONE)
    width, height = image.size
    stride = (width + 7) // 8
    data = bytearray(image.tobytes().translate(_INVERT))  # Pillow packs bit 1 = white
    pad = stride * 8 - width
    if pad:
        mask = (0xFF << pad) & 0xFF
        for row in range(height):
            data[row * stride + stride - 1] &= mask
    return bytes(data)


def frame_etag(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
