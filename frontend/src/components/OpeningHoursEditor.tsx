// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import type { OpeningHours } from "../types";

const DAYS: [string, () => string][] = [
  ["mon", () => i18n.t("Monday")],
  ["tue", () => i18n.t("Tuesday")],
  ["wed", () => i18n.t("Wednesday")],
  ["thu", () => i18n.t("Thursday")],
  ["fri", () => i18n.t("Friday")],
  ["sat", () => i18n.t("Saturday")],
  ["sun", () => i18n.t("Sunday")],
];

/** Per-weekday editor for opening-hour time ranges (each [from, to] in HH:MM).
 *  Days listed in `closedWeekdays` (0 = Monday … 6 = Sunday) are hidden — no
 *  point entering hours for a day the pool is marked closed. */
export function OpeningHoursEditor({
  value,
  onChange,
  closedWeekdays = [],
}: {
  value: OpeningHours;
  onChange: (next: OpeningHours) => void;
  closedWeekdays?: number[];
}) {
  const { t } = useTranslation();
  function update(day: string, ranges: [string, string][]) {
    const next = { ...value };
    if (ranges.length === 0) delete next[day];
    else next[day] = ranges;
    onChange(next);
  }

  const openDays = DAYS.filter((_, idx) => !closedWeekdays.includes(idx));
  if (openDays.length === 0) {
    return (
      <p className="text-xs text-slate-400 dark:text-slate-500">
        {t("All weekdays are marked closed.")}
      </p>
    );
  }

  return (
    <div className="space-y-1.5">
      {openDays.map(([key, label]) => {
        const ranges = value[key] ?? [];
        return (
          <div key={key} className="flex items-start gap-2 text-sm">
            <span className="mt-1 w-24 shrink-0 text-slate-600 dark:text-slate-300">{label()}</span>
            <div className="flex flex-1 flex-wrap items-center gap-2">
              {ranges.length === 0 && (
                <span className="mt-1 text-xs text-slate-400 dark:text-slate-500">{t("closed")}</span>
              )}
              {ranges.map(([from, to], idx) => (
                <span key={idx} className="flex items-center gap-1">
                  <input
                    type="time"
                    value={from}
                    onChange={(e) => {
                      const next = ranges.map((r, i): [string, string] =>
                        i === idx ? [e.target.value, r[1]] : r,
                      );
                      update(key, next);
                    }}
                    className="rounded-md border border-slate-300 px-1.5 py-0.5 text-xs dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <span className="text-slate-400 dark:text-slate-500">–</span>
                  <input
                    type="time"
                    value={to}
                    onChange={(e) => {
                      const next = ranges.map((r, i): [string, string] =>
                        i === idx ? [r[0], e.target.value] : r,
                      );
                      update(key, next);
                    }}
                    className="rounded-md border border-slate-300 px-1.5 py-0.5 text-xs dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <button
                    type="button"
                    onClick={() => update(key, ranges.filter((_, i) => i !== idx))}
                    className="text-slate-400 hover:text-red-600 dark:text-slate-500"
                    aria-label={t("Remove range")}
                  >
                    ×
                  </button>
                </span>
              ))}
              <button
                type="button"
                onClick={() => update(key, [...ranges, ["09:00", "17:00"]])}
                className="rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-800"
              >
                {t("+ add")}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
