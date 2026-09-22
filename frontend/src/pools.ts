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

export interface CompactDayHours {
  label: string; // e.g. "Mo–Fr" or "Sa"
  ranges: string[];
}

// Short, locale-aware weekday names (Mon–Sun), via a reference week starting on
// a known Monday (2024-01-01). Ties the labels to the active UI language.
function shortWeekdayLabels(): string[] {
  return Array.from({ length: 7 }, (_, idx) =>
    new Date(2024, 0, 1 + idx).toLocaleDateString(i18n.language, {
      weekday: "short",
    }),
  );
}

/** Opening hours collapsed into runs of consecutive days that share the same
 *  hours, e.g. "Mo–Fr 09:00–17:00" + "Sa 10:00–14:00" (issue #17). Closed days
 *  are omitted and break a run. */
export function poolHoursCompact(
  opening: OpeningHours,
  closedWeekdays: number[],
): CompactDayHours[] {
  const days = poolHours(opening, closedWeekdays);
  const short = shortWeekdayLabels();
  const out: CompactDayHours[] = [];
  let i = 0;
  while (i < 7) {
    if (days[i].closed) {
      i++;
      continue;
    }
    const key = days[i].ranges.join("|");
    let j = i;
    while (j + 1 < 7 && !days[j + 1].closed && days[j + 1].ranges.join("|") === key) {
      j++;
    }
    out.push({
      label: i === j ? short[i] : `${short[i]}–${short[j]}`,
      ranges: days[i].ranges,
    });
    i = j + 1;
  }
  return out;
}
