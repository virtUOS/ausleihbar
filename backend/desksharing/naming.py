# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Name generation for batch-created rooms and places."""
import re
from itertools import count as _count

from .models import DeskAdminSetting, Place

MAX_BATCH = 200


class RangeError(ValueError):
    """Invalid range; ``field`` names the causing request field."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def room_range(prefix: str, start: str, end: str) -> list[str]:
    """``prefix`` + each number from ``start`` to ``end``; the zero padding of
    ``start`` is kept (``"01"``..``"09"``). At most ``MAX_BATCH`` names."""
    start, end = start.strip(), end.strip()
    for field, value in (("start", start), ("end", end)):
        if not (value.isascii() and value.isdigit()):
            raise RangeError(field, "Start and end must be numbers.")
    first, last = int(start), int(end)
    if first > last:
        raise RangeError("end", "Start must not be greater than end.")
    if last - first + 1 > MAX_BATCH:
        raise RangeError("end", "Too many names requested.")
    width = len(start) if start.startswith("0") else 0
    return [f"{prefix}{number:0{width}d}" for number in range(first, last + 1)]


def _letters(index: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA (bijective base 26)."""
    out = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _letters_index(text: str) -> int:
    value = 0
    for char in text:
        value = value * 26 + (ord(char) - 64)
    return value


def _suffix(pattern: str, index: int) -> str:
    """``" A"`` for the letter pattern, ``"-1"`` for the number pattern."""
    if pattern == DeskAdminSetting.PlaceNamePattern.NUMBER:
        return f"-{index}"
    return f" {_letters(index)}"


def _taken_names(room) -> set[str]:
    """Lower-cased place names (every language column) in the room's building
    (or on its floor when the floor has no building)."""
    from .serializers import NAME_COLUMNS

    floor = room.floor
    if floor.building_id is None:
        scope = Place.objects.filter(room__floor=floor)
    else:
        scope = Place.objects.filter(room__floor__building_id=floor.building_id)
    taken = set()
    for row in scope.rewrite(False).values_list(*NAME_COLUMNS):
        taken.update(value.strip().lower() for value in row if value)
    return taken


def next_place_names(room, count: int, pattern: str, *, extra_taken=()) -> list[str]:
    """``count`` names ``"<room> <letter>"`` or ``"<room>-<number>"``
    continuing after the room's existing places, skipping names taken anywhere
    in the building (and ``extra_taken``, e.g. names planned earlier in a dry
    run)."""
    taken = _taken_names(room) | {name.lower() for name in extra_taken}
    numeric = pattern == DeskAdminSetting.PlaceNamePattern.NUMBER
    matcher = re.compile(
        rf"^{re.escape(room.name.lower())}{'-([0-9]+)' if numeric else ' ([a-z]{1,2})'}$"
    )
    highest = 0
    for name in Place.objects.rewrite(False).filter(room=room).values_list("name", flat=True):
        found = matcher.match(name.strip().lower())
        if found:
            token = found.group(1)
            highest = max(highest, int(token) if numeric else _letters_index(token.upper()))
    names = []
    for index in _count(highest + 1):
        if len(names) >= count:
            break
        name = f"{room.name}{_suffix(pattern, index)}"
        if name.lower() not in taken:
            names.append(name)
    return names
