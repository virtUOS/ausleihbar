// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarDays } from "lucide-react";

import { MonthCalendar } from "./MonthCalendar";
import { useOutsideClose } from "../useOutsideClose";

interface DateFieldProps {
  value: string; // "YYYY-MM-DD" or ""
  onChange: (value: string) => void;
  id?: string;
  /** Accepted for API symmetry; the form guards emptiness itself. */
  required?: boolean;
  ariaLabel?: string;
  /** Layout classes for the wrapper (e.g. "mt-1 block"). */
  className?: string;
}

const todayIso = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD

/** "2026-06-13" → "13.06.2026" for display. */
function formatDe(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
}

function monthOf(iso: string): { year: number; month: number } {
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  const now = new Date();
  return m
    ? { year: Number(m[1]), month: Number(m[2]) - 1 }
    : { year: now.getFullYear(), month: now.getMonth() };
}

/**
 * The app's single date picker: a styled trigger that opens an in-app calendar
 * popover (our `MonthCalendar`, honey selection) instead of the browser's
 * native picker — so the picker matches the design instead of showing the
 * browser's blue popup. Reused wherever a day is chosen.
 */
export function DateField({
  value,
  onChange,
  id,
  ariaLabel,
  className = "",
}: DateFieldProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose<HTMLSpanElement>(open, () => setOpen(false));
  const [view, setView] = useState(() => monthOf(value));

  function toggle() {
    if (!open) setView(monthOf(value)); // reopen on the selected month
    setOpen((o) => !o);
  }

  // Read out the field's purpose *and* its current value/placeholder, so a
  // screen reader announces e.g. "Available from: 13.06.2026" rather than just
  // the "Available from" label (issue #7).
  const valueText = value ? formatDe(value) : t("Pick a date");
  const accessibleName = ariaLabel ? `${ariaLabel}: ${valueText}` : valueText;

  return (
    <span className={`relative inline-block ${className}`} ref={ref}>
      <button
        type="button"
        id={id}
        onClick={toggle}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={accessibleName}
        className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm text-slate-900 transition-colors duration-150 hover:border-slate-400 focus:border-brand-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:border-slate-500"
      >
        <CalendarDays aria-hidden className="h-4 w-4 shrink-0 text-slate-400" />
        <span className={value ? "text-slate-900 dark:text-slate-100" : "text-slate-400 dark:text-slate-300"}>
          {value ? formatDe(value) : t("Pick a date")}
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={ariaLabel ? `${ariaLabel}: ${t("Choose a date")}` : t("Choose a date")}
          className="absolute left-0 z-30 mt-2 w-80 animate-fade-up rounded-xl border border-slate-200 bg-white p-3 shadow-lg shadow-slate-900/5 dark:border-slate-700 dark:bg-slate-800"
        >
          <MonthCalendar
            quickNav
            year={view.year}
            month={view.month}
            onMonthChange={(year, month) => setView({ year, month })}
            onDayClick={(iso) => {
              onChange(iso);
              setOpen(false);
            }}
            isSelected={(iso) => iso === value}
          />
          <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 text-sm dark:border-slate-700">
            <button
              type="button"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
              className="text-slate-500 hover:text-slate-900 hover:underline dark:text-slate-300 dark:hover:text-slate-100"
            >
              {t("clear")}
            </button>
            <button
              type="button"
              onClick={() => {
                const iso = todayIso();
                onChange(iso);
                setView(monthOf(iso));
                setOpen(false);
              }}
              className="font-semibold text-brand-700 hover:underline dark:text-brand-400"
            >
              {t("Today")}
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
