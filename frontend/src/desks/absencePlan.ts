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
 *  the way the calendar shows it. An existing absence identical to a wanted
 *  range — or whose pieces together cover exactly one — is kept; every other editable one is removed, and the wanted ranges
 *  not covered by a kept one are created. A created range that starts at
 *  `today` and continues a removed ongoing absence keeps that absence's
 *  original start, so its past part is not lost. Created ranges longer than
 *  {@link MAX_ABSENCE_DAYS} are split into pieces of at most that length.
 *
 *  Examples (days of one month):
 *  - existing [03–05], wanted [03–05, 10–12] → remove [], create [10–12]
 *  - existing [03–05],[07–09], wanted [03–09] → remove both, create [03–09]
 *  - today = 05, existing [03–08], wanted [05–08] → remove [], create []
 *  - today = 05, existing [03–08], wanted [05–10] → remove it, create [03–10]
 *  - existing [03–05],[06–08], wanted [03–08] → no changes (their union equals it)
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
    .map((a) => ({ id: a.id, original: a.start_date, start: a.start_date < today ? today : a.start_date, end: a.end_date }));

  // Days of other people's (assistant-entered) absences are never ours to create.
  let goal = normalizeRanges(wanted);
  for (const b of blocked) goal = removeRange(goal, b.start, b.end);

  const kept = new Set<number>();
  const toCreate: DayRange[] = [];
  for (const w of goal) {
    // Existing absences lying inside w; if together they cover exactly w
    // (e.g. adjacent pieces of a long absence), w is already satisfied.
    const inside = editable.filter((a) => a.start >= w.start && a.end <= w.end);
    const union = normalizeRanges(inside.map(({ start, end }) => ({ start, end })));
    if (union.length === 1 && union[0].start === w.start && union[0].end === w.end) {
      for (const a of inside) kept.add(a.id);
    } else toCreate.push(w);
  }
  const removed = editable.filter((a) => !kept.has(a.id));

  const create: DayRange[] = [];
  for (const w of toCreate) {
    let start = w.start;
    if (start === today) {
      for (const a of removed) if (a.original < start) start = a.original;
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
