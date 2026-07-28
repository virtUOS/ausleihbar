// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import i18n from "./i18n";
import type { OpeningHours } from "./types";

// Weekday keys as stored in `opening_hours`; index matches `closed_weekdays`
// (0 = Monday … 6 = Sunday).
const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export interface DayHours {
  label: string;
  closed: boolean;
  ranges: string[]; // e.g. ["09:00–13:00", "14:00–17:00"]
}

/** A Mon–Sun opening-hours table for a pool, ready to render. */
export function poolHours(
  opening: OpeningHours,
  closedWeekdays: number[],
): DayHours[] {
  const labels = [
    i18n.t("Monday"),
    i18n.t("Tuesday"),
    i18n.t("Wednesday"),
    i18n.t("Thursday"),
    i18n.t("Friday"),
    i18n.t("Saturday"),
    i18n.t("Sunday"),
  ];
  return WEEKDAY_KEYS.map((key, idx) => {
    const ranges = (opening?.[key] ?? []).map(([from, to]) => `${from}–${to}`);
    return {
      label: labels[idx],
      closed: closedWeekdays.includes(idx) || ranges.length === 0,
      ranges,
    };
  });
}

/** Whether a pool has any opening-hours info worth showing. */
export function hasHours(opening: OpeningHours): boolean {
  return Object.values(opening ?? {}).some((ranges) => ranges.length > 0);
}
