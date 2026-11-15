// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { addDays, parseIso, weekdayName, weekdayOf } from "../weekdays";

const WORKDAYS = [0, 1, 2, 3, 4];

/** Day choice of the overview: a compact date field (any day) with week
 *  arrows, plus Monday–Friday pills of the chosen day's week (on a weekend:
 *  the coming week). Today is marked; past days are greyed and, below
 *  `minDay`, not selectable. */
export function WeekDayBar({
  day,
  today,
  minDay,
  onChange,
}: {
  day: string;
  today: string;
  /** Earliest selectable day (null: past days allowed, e.g. department admins). */
  minDay: string | null;
  onChange: (day: string) => void;
}) {
  const { t } = useTranslation();
  // On a weekend the pills show the coming week (the past one is over).
  const wd = weekdayOf(day);
  const monday = wd >= 5 ? addDays(day, 7 - wd) : addDays(day, -wd);
  const clamp = (d: string) => (minDay && d < minDay ? minDay : d);
  const prevWeek = clamp(addDays(day, -7));

  const iconBtn =
    "flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          aria-label={t("Previous week")}
          disabled={prevWeek >= day}
          onClick={() => onChange(prevWeek)}
          className={iconBtn}
        >
          <ChevronLeft aria-hidden className="h-5 w-5" />
        </button>
        <label>
          <span className="sr-only">{t("Day")}</span>
          <input
            type="date"
            value={day}
            min={minDay ?? undefined}
            onChange={(e) => e.target.value && onChange(clamp(e.target.value))}
            className="min-h-[44px] w-[9.5rem] rounded-lg border border-slate-300 bg-white px-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
        </label>
        <button
          type="button"
          aria-label={t("Next week")}
          onClick={() => onChange(addDays(day, 7))}
          className={iconBtn}
        >
          <ChevronRight aria-hidden className="h-5 w-5" />
        </button>
      </div>
      <div role="group" aria-label={t("Weekday")} className="flex gap-1.5">
        {WORKDAYS.map((i) => {
          const d = addDays(monday, i);
          const selected = d === day;
          const isToday = d === today;
          const past = d < today;
          return (
            <button
              key={d}
              type="button"
              aria-pressed={selected}
              aria-current={isToday ? "date" : undefined}
              disabled={!!minDay && d < minDay}
              onClick={() => onChange(d)}
              title={isToday ? t("Today") : undefined}
              className={`relative flex min-h-[44px] min-w-[3rem] flex-col items-center justify-center rounded-full border px-2.5 text-xs leading-tight transition-colors duration-150 disabled:cursor-not-allowed ${
                selected
                  ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : past
                    ? "border-slate-200 text-slate-400 dark:border-slate-700 dark:text-slate-500"
                    : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              } ${isToday && !selected ? "ring-2 ring-brand-400 ring-offset-1 dark:ring-offset-slate-900" : ""}`}
            >
              <span className="font-semibold">{weekdayName(i)}</span>
              <span>{parseIso(d).getDate()}.</span>
            </button>
          );
        })}
      </div>
      {day !== today && (
        <button
          type="button"
          onClick={() => onChange(today)}
          className="min-h-[44px] shrink-0 rounded-full border border-slate-300 px-3 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {t("Today")}
        </button>
      )}
    </div>
  );
}
