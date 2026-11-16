// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { DayRange } from "../dayRanges";
import type { Absence } from "./types";
import { addDays } from "./weekdays";

/** The backend caps one absence at this many days. */
export const MAX_ABSENCE_DAYS = 366;

/** Turn the wanted absence periods into the minimal API calls.
 *
 *  Only `existing` absences that end on or after `today` are editable (the
 *  caller passes the person's own ones); past ones are never removed. An
 *  ongoing absence (starting before `today`) counts as starting at `today`,
 *  the way the calendar shows it. An existing absence identical to a wanted
 *  range is kept; every other editable one is removed, and the wanted ranges
 *  not covered by a kept one are created. A created range that starts at
 *  `today` and continues a removed ongoing absence keeps that absence's
 *  original start, so its past part is not lost. Created ranges longer than
 *  {@link MAX_ABSENCE_DAYS} are split into pieces of at most that length.
 *
 *  Examples (days of one month):
 *  - existing [03–05], wanted [03–05, 10–12] → remove [], create [10–12]
 *  - existing [03–05],[07–09], wanted [03–09] → remove both, create [03–09]
 *  - today = 05, existing [03–08], wanted [05–08] → remove [], create []
 *  - today = 05, existing [03–08], wanted [05–10] → remove it, create [03–10] */
export function planAbsenceChanges(
  existing: Absence[],
  wanted: DayRange[],
  today: string,
): { remove: number[]; create: DayRange[] } {
  const editable = existing.filter((a) => a.end_date >= today);
  const clampedStart = (a: Absence) => (a.start_date < today ? today : a.start_date);

  const kept = new Set<number>();
  const toCreate: DayRange[] = [];
  for (const w of wanted) {
    const same = editable.find(
      (a) => !kept.has(a.id) && clampedStart(a) === w.start && a.end_date === w.end,
    );
    if (same) kept.add(same.id);
    else toCreate.push(w);
  }
  const removed = editable.filter((a) => !kept.has(a.id));

  const create: DayRange[] = [];
  for (const w of toCreate) {
    let start = w.start;
    if (start === today) {
      for (const a of removed) if (a.start_date < start) start = a.start_date;
    }
    for (let s = start; s <= w.end; ) {
      const cap = addDays(s, MAX_ABSENCE_DAYS - 1);
      const e = cap < w.end ? cap : w.end;
      create.push({ start: s, end: e });
      s = addDays(e, 1);
    }
  }
  return { remove: removed.map((a) => a.id), create };
}
