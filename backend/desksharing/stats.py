# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Anonymous usage figures per department.

Standard places are reported as a quota per kind (desks, meeting rooms);
places flagged ``is_special`` individually. Only reservation counts and hours
are used: the reservation ``holder`` is never selected (``.values()`` without
it), so no person data can reach the figures or the CSV.

Definitions (see the Task 11 rulings):

- ``booked_h``: active and released reservations (a released one counts fully
  as booked); cancelled ones are withdrawn before use and never counted.
- ``checked_in_h``: booked hours of checked-in reservations, from the check-in
  hour (not before the start) to the end, or to ``released_at`` if released
  after the check-in.
- ``released_h``: the released part ``[max(released_at, start), end)``.
- ``rebooked_after_release_h``: hours of other reservations of the same place
  overlapping a released part, clipped to it.
- ``assigned_h``: fixed desks: business hours (minus lending blocks such as
  holidays) minus days fully covered by an owner absence. Absences are deleted
  after the retention period, so for long-past periods only the absences still
  stored can be subtracted (assigned hours are then overestimated).
- Heatmap: occupancy % per weekday x hour = occupied place-hours / available
  place-hours; fixed desks count as occupied during their assigned hours.

Aggregation: the reservation rows of the period are fetched with a single
``values()`` query and folded in Python in one pass (about one dict update per
booked hour); a year for a 100-place department stays well below a second.
"""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Q

from lending.models import Block

from . import hours
from .models import Absence, DeskSettings, Place, Reservation

MAX_DAYS = 5 * 366  # lending's stats allow 5 years; same limit here
FIGURE_KEYS = (
    "booked_h", "checked_in_h", "no_show_count", "no_show_h", "released_h",
    "rebooked_after_release_h", "assigned_h",
)


def _h(delta: timedelta) -> float:
    return max(delta.total_seconds(), 0) / 3600


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _open_hours(pool, start: date, end: date) -> dict[date, list[int]]:
    """Open grid hours per day: business hours minus lending blocks."""
    settings_ = DeskSettings.objects.filter(pool=pool).first()
    week = (settings_.business_hours if settings_ else None) or {}
    window = DateTimeTZRange(hours.local_dt(start, 0), hours.local_dt(end, 24))
    blocks = list(
        Block.objects.filter(
            Q(resource_pool__isnull=True) | Q(resource_pool=pool),
            product__isnull=True, resource__isnull=True, period__overlap=window,
        ).values_list("period", flat=True)
    )
    out = {}
    for day in _days(start, end):
        span = week.get(str(day.weekday()))
        if not span:
            out[day] = []
            continue
        first, last = max(hours.FIRST_HOUR, int(span[0])), min(hours.LAST_HOUR, int(span[1]))
        open_ = []
        for hour in range(first, last):
            lo, hi = hours.local_dt(day, hour), hours.local_dt(day, hour + 1)
            if not any(
                (b.lower is None or b.lower < hi) and (b.upper is None or b.upper > lo)
                for b in blocks
            ):
                open_.append(hour)
        out[day] = open_
    return out


def _empty():
    return {k: 0 for k in FIGURE_KEYS}


def _figures(places, rows_by_place, open_hours, absent, start, end):
    """Figures for one group of places (``rows_by_place``: place id ->
    reservation dicts)."""
    fig = _empty()
    occupied = defaultdict(int)  # (weekday, hour) -> occupied place-hours
    taken = set()  # (place_id, day, hour) occupied by a reservation
    released = defaultdict(list)  # place_id -> [(from, to)]
    by_place = defaultdict(list)
    rows = [row for p in places for row in rows_by_place.get(p["id"], ())]
    for row in rows:
        period = row["period"]
        lower, upper = period.lower, period.upper
        day, first, last = hours.local_day_hours(period)
        booked = last - first
        fig["booked_h"] += booked
        for hour in range(first, last):
            taken.add((row["place_id"], day, hour))
        if row["no_show"]:
            fig["no_show_count"] += 1
            fig["no_show_h"] += booked
        end_at = upper
        if row["status"] == Reservation.Status.RELEASED and row["released_at"]:
            from_ = max(row["released_at"], lower)
            if from_ < upper:
                fig["released_h"] += _h(upper - from_)
                released[row["place_id"]].append((from_, upper, row))
            end_at = from_ if row["checked_in_at"] and row["released_at"] > row["checked_in_at"] else upper
        if row["checked_in_at"]:
            checked = row["checked_in_at"].astimezone(hours.TZ).replace(
                minute=0, second=0, microsecond=0
            )
            fig["checked_in_h"] += _h(min(end_at, upper) - max(checked, lower))
        by_place[row["place_id"]].append((lower, upper, row))
    for place_id, parts in released.items():
        others = by_place[place_id]
        for from_, to, own in parts:
            for lower, upper, row in others:
                if row is own:  # the released reservation itself is not "rebooked"
                    continue
                fig["rebooked_after_release_h"] += _h(min(to, upper) - max(from_, lower))
    # Occupancy (+ assigned hours of fixed desks).
    for place in places:
        if place["fixed_owner_id"] is None or place["kind"] != Place.Kind.DESK:
            continue
        away = absent.get(place["fixed_owner_id"], set())
        for day in _days(start, end):
            if day in away:
                continue
            for hour in open_hours[day]:
                fig["assigned_h"] += 1
                taken.add((place["id"], day, hour))
    for _place, day, hour in taken:
        occupied[(day.weekday(), hour)] += 1
    # Availability per (day, hour): open hours, plus hours that had occupancy
    # although closed now (blocks, changed business hours), so that
    # occupied <= available holds for every cell.
    day_hours = {(day, hour) for day in _days(start, end) for hour in open_hours[day]}
    day_hours.update((day, hour) for _place, day, hour in taken)
    available = defaultdict(int)
    for day, hour in day_hours:
        available[(day.weekday(), hour)] += len(places)
    heatmap = defaultdict(dict)
    for (weekday, hour), total in sorted(available.items()):
        if total:
            heatmap[weekday][hour] = round(occupied[(weekday, hour)] / total * 100, 1)
    for key in ("released_h", "rebooked_after_release_h", "checked_in_h"):
        fig[key] = round(fig[key], 2)
    fig["heatmap"] = {wd: dict(sorted(h.items())) for wd, h in sorted(heatmap.items())}
    return fig


def department_stats(pool, start: date, end: date) -> dict:
    window = DateTimeTZRange(hours.local_dt(start, 0), hours.local_dt(end, 24))
    pool_places = Place.objects.filter(room__floor__pool=pool).select_related("room__floor")
    rows = list(
        Reservation.objects.filter(place__room__floor__pool=pool, period__overlap=window)
        .exclude(status=Reservation.Status.CANCELLED)
        .values("place_id", "period", "status", "checked_in_at", "released_at", "no_show")
    )
    used = {r["place_id"] for r in rows}
    places = [
        {
            "id": p.pk, "name": p.name, "kind": p.kind, "is_special": p.is_special,
            "fixed_owner_id": p.fixed_owner_id,
        }
        for p in pool_places
        if p.is_bookable or p.pk in used
    ]
    owners = {p["fixed_owner_id"] for p in places if p["fixed_owner_id"]}
    absent = defaultdict(set)
    for user_id, a_start, a_end in Absence.objects.filter(
        user_id__in=owners, start_date__lte=end, end_date__gte=start
    ).values_list("user_id", "start_date", "end_date"):
        for day in _days(max(a_start, start), min(a_end, end)):
            absent[user_id].add(day)
    open_hours = _open_hours(pool, start, end)

    rows_by_place = defaultdict(list)
    for row in rows:
        rows_by_place[row["place_id"]].append(row)

    def figures(group):
        return _figures(group, rows_by_place, open_hours, absent, start, end)

    quota = {
        kind: figures([p for p in places if p["kind"] == kind and not p["is_special"]])
        for kind in (Place.Kind.DESK, Place.Kind.MEETING_ROOM)
    }
    special = [
        {"place": {"id": p["id"], "name": p["name"], "kind": p["kind"]}, **figures([p])}
        for p in places
        if p["is_special"]
    ]
    return {"quota": quota, "special": special}


def _safe(value) -> str:
    """Neutralise spreadsheet formula injection in text cells."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def stats_csv(pool, start: date, end: date) -> str:
    data = department_stats(pool, start, end)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["group", "place", *FIGURE_KEYS, "weekday", "hour", "occupancy_pct"])
    groups = [(kind, "", fig) for kind, fig in data["quota"].items()] + [
        ("special", entry["place"]["name"], entry) for entry in data["special"]
    ]
    for group, place, fig in groups:
        writer.writerow([group, _safe(place), *(fig[k] for k in FIGURE_KEYS), "", "", ""])
        for weekday, per_hour in fig["heatmap"].items():
            for hour, pct in per_hour.items():
                writer.writerow(
                    [group, _safe(place), *([""] * len(FIGURE_KEYS)), weekday, hour, pct]
                )
    return out.getvalue()
