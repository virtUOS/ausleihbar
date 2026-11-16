// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Pure helpers for sets of calendar days kept as inclusive day ranges.
 *  Days are ISO dates (`YYYY-MM-DD`), which sort lexicographically in date
 *  order. Every function that returns ranges returns them normalized: sorted
 *  by start, with overlapping **and adjacent** ranges merged, so two
 *  selections covering the same days always compare equal. */

/** An inclusive range of days, `start <= end`. */
export type DayRange = { start: string; end: string };

/** Shift an ISO day by `delta` days. Uses UTC so DST changes can't skip or
 *  repeat a day. */
function shiftDay(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + delta)).toISOString().slice(0, 10);
}

const nextDay = (iso: string) => shiftDay(iso, 1);
const prevDay = (iso: string) => shiftDay(iso, -1);

/** Sort the ranges and merge overlapping and adjacent ones (e.g. 03–05 and
 *  06–06 become 03–06). Ranges given end-before-start are flipped. */
export function normalizeRanges(r: DayRange[]): DayRange[] {
  const sorted = r
    .map(({ start, end }) => (start <= end ? { start, end } : { start: end, end: start }))
    .sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
  const out: DayRange[] = [];
  for (const cur of sorted) {
    const last = out[out.length - 1];
    if (last && cur.start <= nextDay(last.end)) {
      if (cur.end > last.end) last.end = cur.end;
    } else {
      out.push({ ...cur });
    }
  }
  return out;
}

/** Whether `iso` lies in any of the ranges. */
export function rangesContain(r: DayRange[], iso: string): boolean {
  return r.some(({ start, end }) => start <= iso && iso <= end);
}

/** Add the days from `a` to `b` (inclusive, either order). */
export function addRange(r: DayRange[], a: string, b: string): DayRange[] {
  const [start, end] = a <= b ? [a, b] : [b, a];
  return normalizeRanges([...r, { start, end }]);
}

/** Remove the days from `a` to `b` (inclusive, either order); ranges that
 *  straddle the removed span are cut, possibly into two. */
export function removeRange(r: DayRange[], a: string, b: string): DayRange[] {
  const [lo, hi] = a <= b ? [a, b] : [b, a];
  const out: DayRange[] = [];
  for (const { start, end } of normalizeRanges(r)) {
    if (end < lo || start > hi) {
      out.push({ start, end });
      continue;
    }
    if (start < lo) out.push({ start, end: prevDay(lo) });
    if (end > hi) out.push({ start: nextDay(hi), end });
  }
  return out;
}

/** Add `iso` if it isn't covered, otherwise remove it (splitting its range). */
export function toggleDay(r: DayRange[], iso: string): DayRange[] {
  return rangesContain(r, iso) ? removeRange(r, iso, iso) : addRange(r, iso, iso);
}

/** Every covered day, in order and without duplicates. */
export function rangeDays(r: DayRange[]): string[] {
  const days: string[] = [];
  for (const { start, end } of normalizeRanges(r)) {
    for (let d = start; d <= end; d = nextDay(d)) days.push(d);
  }
  return days;
}
