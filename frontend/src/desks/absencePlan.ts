// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { normalizeRanges, removeRange, type DayRange } from "../dayRanges";
import type { Absence } from "./types";
import { addDays } from "./weekdays";

/** The backend caps one absence at this many days. */
export const MAX_ABSENCE_DAYS = 366;

/** Turn the wanted absence periods into the minimal API calls.
 *
 *  Only `existing` absences that end on or after `today` are editable (the
 *  caller passes the person's own ones); past ones are never removed. An
 *  ongoing absence (starting before `today`) counts as starting at `today`,
 *  the way the calendar shows it.
 *
 *  - kept: every editable absence whose days (from `today`, minus `blocked`)
 *    all lie inside the wanted days;
 *  - remove: the other editable absences;
 *  - create: the wanted days (minus `blocked`) not covered by a kept absence,
 *    as ranges of at most {@link MAX_ABSENCE_DAYS} days.
 *
 *  A removed ongoing absence keeps its past: a created range starting at
 *  `today` takes over its original start; otherwise its past days
 *  (original start .. yesterday) are created as well.
 *
 *  Examples (days of one month, today before them):
 *  - existing [03–05], wanted [03–05, 10–12] → remove [], create [10–12]
 *  - existing [03–05], wanted [03–09] → remove [], create [06–09]
 *  - existing [03–05],[07–09], wanted [03–09] → remove [], create [06–06]
 *  - existing [03–05],[06–08], wanted [03–08] → no changes
 *  - today = 05, existing [03–08], wanted [05–08] → no changes
 *  - today = 05, existing [03–08], wanted [05–10] → remove [], create [09–10]
 *  - today = 05, existing [03–08], wanted [06–08] → remove it, create [06–08], [03–04]
 *
 *  `blocked` are days that can't be created (other people's absences); the
 *  wanted ranges are split around them. */
export function planAbsenceChanges(
  existing: Absence[],
  wanted: DayRange[],
  today: string,
  blocked: DayRange[] = [],
): { remove: number[]; create: DayRange[] } {
  const editable = existing
    .filter((a) => a.end_date >= today)
    .map((a) => {
      const start = a.start_date < today ? today : a.start_date;
      let ps: DayRange[] = [{ start, end: a.end_date }];
      for (const bl of blocked) ps = removeRange(ps, bl.start, bl.end);
      return { id: a.id, original: a.start_date, ps };
    });

  // Days of other people's (assistant-entered) absences are never ours to create.
  let goal = normalizeRanges(wanted);
  for (const b of blocked) goal = removeRange(goal, b.start, b.end);
  const inGoal = (r: DayRange) => goal.some((w) => r.start >= w.start && r.end <= w.end);

  const keptAbs = editable.filter((a) => a.ps.every(inGoal));
  const removed = editable.filter((a) => !keptAbs.includes(a));

  let toCreate = goal;
  for (const a of keptAbs) for (const p of a.ps) toCreate = removeRange(toCreate, p.start, p.end);

  // Removed ongoing absences keep their past part.
  for (const a of removed) {
    if (a.original >= today) continue;
    const cont = toCreate.find((w) => w.start === today);
    if (cont) {
      if (a.original < cont.start) cont.start = a.original;
    } else {
      toCreate = normalizeRanges([...toCreate, { start: a.original, end: addDays(today, -1) }]);
    }
  }

  const create: DayRange[] = [];
  for (const w of toCreate) {
    for (let s = w.start; s <= w.end; ) {
      const cap = addDays(s, MAX_ABSENCE_DAYS - 1);
      const e = cap < w.end ? cap : w.end;
      create.push({ start: s, end: e });
      s = addDays(e, 1);
    }
  }
  return { remove: removed.map((a) => a.id), create };
}
