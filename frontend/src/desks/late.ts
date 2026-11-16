// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

export interface LateOption {
  minutes: number;
  /** ISO timestamp the place is kept until. */
  until: string;
}

const STEP = 30;

/**
 * Late-arrival options for a reservation: 30-minute steps from 30 minutes up
 * to 50 % of the booked duration (floored to 30 minutes, at least 30), counted
 * from `max(start, now)`, and never past the end (options whose `until` would
 * lie after `end` are dropped).
 *
 * Examples:
 *  - 8-16 h, now before the start: 30, 60, ... 240.
 *  - 9-10 h: [30].
 *  - 8-16 h at 15:10: [30] only (until 15:40; +60 would end after 16:00).
 */
export function lateOptions(startIso: string, endIso: string, now: Date): LateOption[] {
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  const base = Math.max(start, now.getTime());
  const half = Math.floor((end - start) / 2 / 60_000 / STEP) * STEP;
  const max = Math.max(STEP, half);
  const options: LateOption[] = [];
  for (let minutes = STEP; minutes <= max; minutes += STEP) {
    const until = base + minutes * 60_000;
    if (until > end) break;
    options.push({ minutes, until: new Date(until).toISOString() });
  }
  return options;
}

/** Preselected option: 60 minutes if offered, else the largest one. */
export function defaultLate(options: LateOption[]): number {
  if (options.some((o) => o.minutes === 60)) return 60;
  return options.length ? options[options.length - 1].minutes : 0;
}
