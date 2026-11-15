// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { pad2 } from "../weekdays";

const pad = (h: number) => `${pad2(h)}:00`;
/** Thumb width in px (mirrors `.hour-scrubber` in index.css). */
const THUMB = 24;

/** Horizontal position of hour index `i` of `n`, aligned with the thumb centre. */
const at = (i: number, n: number) =>
  n <= 1 ? "50%" : `calc(${THUMB / 2}px + (100% - ${THUMB}px) * ${i / (n - 1)})`;

/** A drawn timeline of the open hours with a draggable scrubber (a native
 *  range input: drag, tap, arrow keys, screen readers). Behind it, bars show
 *  how full the floor is each hour; closed hours are greyed, the current
 *  hour is marked. */
export function HourScrubber({
  hours,
  value,
  onChange,
  closed,
  load,
  nowHour,
}: {
  /** The open hours of the day, ascending and contiguous. */
  hours: number[];
  value: number;
  onChange: (hour: number) => void;
  closed: number[];
  /** Share of the floor's places taken per hour (0..1). */
  load: Record<number, number>;
  /** The current hour when the day is today. */
  nowHour: number | null;
}) {
  const { t } = useTranslation();
  const n = hours.length;
  const first = hours[0];
  const last = hours[n - 1];
  const barWidth = n <= 1 ? "40%" : `calc((100% - ${THUMB}px) / ${n - 1} * 0.6)`;

  return (
    <div className="mb-3">
      <p className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100" aria-hidden>
        {pad(value)}–{pad(value + 1)}
        {nowHour === value && (
          <span className="ml-2 text-xs font-medium text-slate-600 dark:text-slate-300">{t("now")}</span>
        )}
      </p>
      <div className="relative">
        {/* Track: occupancy bars, closed hours, the current hour. */}
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-11">
          <div className="absolute inset-x-0 bottom-2 h-px bg-slate-300 dark:bg-slate-600" />
          {hours.map((h, i) => {
            const isClosed = closed.includes(h);
            const share = load[h] ?? 0;
            return (
              <div
                key={h}
                className="absolute bottom-2 -translate-x-1/2"
                style={{ left: at(i, n), width: barWidth, height: "28px" }}
              >
                {isClosed ? (
                  <div className="absolute inset-x-0 bottom-0 h-full rounded-sm bg-slate-200/70 dark:bg-slate-700/60" />
                ) : (
                  <div
                    className={`absolute inset-x-0 bottom-0 rounded-sm ${
                      h === value ? "bg-slate-500 dark:bg-slate-300" : "bg-slate-300 dark:bg-slate-600"
                    }`}
                    style={{ height: `${Math.max(share, 0.04) * 100}%` }}
                  />
                )}
              </div>
            );
          })}
          {nowHour !== null && nowHour >= first && nowHour <= last && (
            <div
              className="absolute -translate-x-1/2 bottom-0 h-2 w-2 rounded-full bg-brand-600 dark:bg-brand-300"
              style={{ left: at(nowHour - first, n) }}
            />
          )}
        </div>
        <input
          type="range"
          min={first}
          max={last}
          step={1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label={t("Hour")}
          aria-valuetext={`${pad(value)}–${pad(value + 1)}`}
          className="hour-scrubber relative block w-full"
        />
        {/* Hour labels (every second one on narrow screens). */}
        <div aria-hidden className="relative h-4 text-[11px] text-slate-600 dark:text-slate-300">
          {hours.map((h, i) => (
            <span
              key={h}
              className={`absolute -translate-x-1/2 ${i % 2 ? "hidden sm:inline" : ""} ${h === value ? "font-bold text-slate-900 dark:text-slate-100" : ""}`}
              style={{ left: at(i, n) }}
            >
              {h}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
