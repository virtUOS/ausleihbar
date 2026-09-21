// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const pad = (n: number) => String(n).padStart(2, "0");
const isoOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

interface MonthCalendarProps {
  /** Shown month. `month` is 0-based. */
  year: number;
  month: number;
  onMonthChange: (year: number, month: number) => void;
  /** Content rendered below each day number (e.g. availability badge). */
  renderDay?: (iso: string) => ReactNode;
  onDayClick?: (iso: string) => void;
  // Pointer hooks for drag-to-select range behaviour (optional).
  onDayPointerDown?: (iso: string) => void;
  onDayPointerEnter?: (iso: string) => void;
  onDayPointerUp?: (iso: string) => void;
  isSelected?: (iso: string) => boolean;
  isDisabled?: (iso: string) => boolean;
  /** Days shown greyed as "out of range" but still interactive — unlike
   *  `isDisabled`, a muted day keeps firing pointer events (so drag-select
   *  doesn't stall on it) and can still be clicked. Used to mark days beyond
   *  the max lending duration (#47). */
  isMuted?: (iso: string) => boolean;
  /** Closed days (block / closed weekday) are greyed and not selectable. */
  isClosed?: (iso: string) => boolean;
  /** Show month + year dropdowns in the header for quick jumps (date picker). */
  quickNav?: boolean;
  /** Screen-reader label for a day. Receives the localized full date so the
   *  consumer can append the day's state (e.g. availability) without
   *  re-formatting it. Defaults to the date alone (plus "closed"). */
  dayLabel?: (iso: string, dateLabel: string) => string;
}

/** A reusable month grid. Purely presentational — the consumer supplies the
 *  per-day content, selection state and click handling. */
export function MonthCalendar({
  year,
  month,
  onMonthChange,
  renderDay,
  onDayClick,
  onDayPointerDown,
  onDayPointerEnter,
  onDayPointerUp,
  isSelected,
  isDisabled,
  isMuted,
  isClosed,
  quickNav = false,
  dayLabel,
}: MonthCalendarProps) {
  const { t, i18n } = useTranslation();
  // Localized full date ("Montag, 22. Juni 2026") for each day's screen-reader
  // label, so a day reads as a real date instead of a bare "22".
  const longDate = (y: number, m: number, d: number) =>
    new Date(y, m, d).toLocaleDateString(i18n.language, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7; // Monday-first
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const prev = () => onMonthChange(month === 0 ? year - 1 : year, (month + 11) % 12);
  const next = () => onMonthChange(month === 11 ? year + 1 : year, (month + 1) % 12);

  // A ±5-year window for the quick-nav year dropdown, always including the
  // currently viewed year (which may be further out via the arrows).
  const thisYear = new Date().getFullYear();
  const years = Array.from({ length: 11 }, (_, i) => thisYear - 5 + i);
  if (!years.includes(year)) years.push(year);
  years.sort((a, b) => a - b);

  const cells: (number | null)[] = [
    ...Array(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <button type="button" onClick={prev} aria-label={t("Previous month")} className="rounded-full px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-700">
          ‹
        </button>
        {quickNav ? (
          <div className="flex items-center gap-1">
            <select
              value={month}
              onChange={(e) => onMonthChange(year, Number(e.target.value))}
              aria-label={t("Month")}
              className="rounded-md border border-slate-200 bg-white py-1 pl-2 pr-1 text-sm font-semibold text-slate-900 focus:border-brand-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            >
              {MONTHS.map((name, i) => (
                <option key={name} value={i}>
                  {t(name)}
                </option>
              ))}
            </select>
            <select
              value={year}
              onChange={(e) => onMonthChange(Number(e.target.value), month)}
              aria-label={t("Year")}
              className="rounded-md border border-slate-200 bg-white py-1 pl-2 pr-1 text-sm font-semibold text-slate-900 focus:border-brand-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {t(MONTHS[month])} {year}
          </span>
        )}
        <button type="button" onClick={next} aria-label={t("Next month")} className="rounded-full px-2 py-1 hover:bg-slate-100 dark:hover:bg-slate-700">
          ›
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-xs text-slate-400 dark:text-slate-400">
        {WEEKDAYS.map((w) => (
          <div key={w} className="py-1">{t(w)}</div>
        ))}
      </div>

      <div className="grid select-none grid-cols-7 gap-1">
        {cells.map((day, idx) => {
          if (day === null) return <div key={`e${idx}`} />;
          const iso = isoOf(year, month, day);
          const closed = isClosed?.(iso) ?? false;
          const disabled = closed || (isDisabled?.(iso) ?? false);
          const selected = isSelected?.(iso) ?? false;
          const muted = !disabled && !selected && (isMuted?.(iso) ?? false);
          const base = longDate(year, month, day);
          const ariaLabel = dayLabel
            ? dayLabel(iso, base)
            : closed
              ? `${base}, ${t("Closed")}`
              : base;
          return (
            <button
              key={iso}
              type="button"
              disabled={disabled}
              aria-label={ariaLabel}
              aria-pressed={selected}
              onClick={() => onDayClick?.(iso)}
              onPointerDown={() => !closed && onDayPointerDown?.(iso)}
              onPointerEnter={() => !closed && onDayPointerEnter?.(iso)}
              onPointerUp={() => !closed && onDayPointerUp?.(iso)}
              title={closed ? t("Closed") : undefined}
              className={`flex min-h-12 flex-col items-center rounded-md border p-1 text-xs ${
                closed
                  ? "border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400"
                  : selected
                    ? "border-brand-500 bg-brand-100 text-slate-900"
                    : "border-slate-200 text-slate-900 dark:border-slate-700 dark:text-slate-100"
              } ${
                disabled
                  ? closed
                    ? "cursor-not-allowed"
                    : "cursor-not-allowed opacity-40"
                  : muted
                    ? "opacity-40 hover:border-brand-400"
                    : "hover:border-brand-400"
              }`}
            >
              {/* Visual only — the accessible name is the aria-label above. */}
              <span aria-hidden="true" className="font-medium">{day}</span>
              {renderDay && (
                <span aria-hidden="true" className="contents">
                  {renderDay(iso)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
