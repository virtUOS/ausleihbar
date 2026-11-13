// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

const FIRST_HOUR = 6;
const LAST_HOUR = 20;
const pad = (h: number) => String(h).padStart(2, "0");

export interface HourRange {
  start: number;
  end: number;
}

interface Props {
  /** Business hours of the day (`[start, end)`); null = closed. */
  open: [number, number] | null;
  /** Grid hours blocked by a closure. */
  closed: number[];
  /** First selectable hour (the current one when the day is today). */
  minHour?: number | null;
  value: HourRange | null;
  onChange: (range: HourRange | null) => void;
}

/** Full-hour range picker for 06–20: tap one hour, then another to extend.
 *  Hours outside the business hours or closed are disabled. */
export function HourRangePicker({ open, closed, minHour, value, onChange }: Props) {
  const { t } = useTranslation();
  const hours = Array.from({ length: LAST_HOUR - FIRST_HOUR }, (_, i) => FIRST_HOUR + i);
  const enabled = (h: number) => !!open && h >= open[0] && h >= (minHour ?? 0) && h < open[1] && !closed.includes(h);
  const rangeOk = (start: number, end: number) => {
    for (let h = start; h < end; h++) if (!enabled(h)) return false;
    return end > start;
  };

  function pick(h: number) {
    if (value && value.end - value.start === 1 && h !== value.start) {
      const start = Math.min(h, value.start);
      const end = Math.max(h, value.start) + 1;
      if (rangeOk(start, end)) return onChange({ start, end });
    }
    onChange({ start: h, end: h + 1 });
  }

  // Quick ranges start no earlier than the first selectable hour.
  const lo = Math.max(open?.[0] ?? 0, minHour ?? 0);
  const clamp = (start: number, end: number): HourRange | null => {
    const s = Math.max(start, lo);
    return end > s ? { start: s, end } : null;
  };
  const quick: { label: string; range: HourRange | null }[] = open
    ? [
        { label: t("Whole day"), range: clamp(open[0], open[1]) },
        { label: t("8 hours"), range: clamp(open[0], Math.min(Math.max(open[0], lo) + 8, open[1])) },
        { label: t("Morning (4 h)"), range: clamp(open[0], open[0] + 4) },
        { label: t("Afternoon (4 h)"), range: clamp(open[1] - 4, open[1]) },
      ]
    : [];

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        {quick.map((q) => {
          const ok = q.range !== null && rangeOk(q.range.start, q.range.end);
          const active = !!value && !!q.range && value.start === q.range.start && value.end === q.range.end;
          return (
            <button
              key={q.label}
              type="button"
              disabled={!ok}
              aria-pressed={active}
              onClick={() => q.range && onChange(q.range)}
              className={`min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40 ${
                active
                  ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              }`}
            >
              {q.label}
            </button>
          );
        })}
      </div>
      <div role="group" aria-label={t("Hours")} className="grid grid-cols-4 gap-1.5 sm:grid-cols-7">
        {hours.map((h) => {
          const selected = !!value && h >= value.start && h < value.end;
          return (
            <button
              key={h}
              type="button"
              disabled={!enabled(h)}
              aria-pressed={selected}
              onClick={() => pick(h)}
              className={`min-h-[44px] rounded-lg border text-sm tabular-nums transition-colors duration-150 ${
                selected
                  ? "border-brand-500 bg-brand-100 font-semibold text-slate-900"
                  : "border-slate-200 text-slate-800 hover:border-brand-400 dark:border-slate-700 dark:text-slate-100"
              } disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:border-slate-200 dark:disabled:bg-slate-800/60 dark:disabled:text-slate-300`}
            >
              {pad(h)}:00
            </button>
          );
        })}
      </div>
      <p aria-live="polite" className="mt-2 min-h-[1.25rem] text-sm font-medium text-slate-900 dark:text-slate-100">
        {value ? `${pad(value.start)}:00–${pad(value.end)}:00` : ""}
      </p>
    </div>
  );
}
