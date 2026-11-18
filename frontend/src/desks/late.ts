// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import { formatTime } from "../dates";

export interface LateOption {
  minutes: number;
  /** ISO timestamp the place is kept until. */
  until: string;
  /** True for the final option that ends exactly at the reservation end. */
  capped?: boolean;
}

const STEP = 30;

/**
 * Late-arrival options for a reservation: 30-minute steps from 30 minutes up
 * to 50 % of the booked duration (floored to 30 minutes, at least 30), counted
 * from `max(start, now)`, and capped at the end (when the next step would
 * pass `end`, one final option ends exactly at `end`).
 *
 * Examples:
 *  - 8-16 h, now before the start: 30, 60, ... 240.
 *  - 9-10 h: [30].
 *  - 8-16 h at 15:10: [30 (15:40), 50 (16:00, capped)].
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
    if (until > end) {
      // Capped at the end: one last option ending exactly at the reservation end.
      const last = options.length ? new Date(options[options.length - 1].until).getTime() : base;
      if (end > last && end > now.getTime()) {
        options.push({ minutes: Math.round((end - base) / 60_000), until: new Date(end).toISOString(), capped: true });
      }
      break;
    }
    options.push({ minutes, until: new Date(until).toISOString() });
  }
  return options;
}

/** Preselected option: 60 minutes if offered, else the largest one. */
export function defaultLate(options: LateOption[]): number {
  if (options.some((o) => o.minutes === 60)) return 60;
  return options.length ? options[options.length - 1].minutes : 0;
}

/** The option to use: `selected` if still offered, else the default. */
export function pickLate(options: LateOption[], selected: number | null | undefined): LateOption | undefined {
  const wanted = options.some((o) => o.minutes === selected) ? selected : defaultLate(options);
  return options.find((o) => o.minutes === wanted);
}

/** Button label of an option: "30 min", "1,5 h" or "until 16:00" (capped). */
export function lateOptionLabel(o: LateOption, t: TFunction, language: string): string {
  if (o.capped) return t("until {{time}}", { time: formatTime(o.until) });
  if (o.minutes < 60) return t("{{value}} min", { value: o.minutes });
  return t("{{value}} h", { value: (o.minutes / 60).toLocaleString(language) });
}
