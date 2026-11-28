// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { MonthCalendar } from "../../components/MonthCalendar";
import { formatDayWithWeekday } from "../../dates";
import { useOutsideClose } from "../../useOutsideClose";
import { addDays, parseIso } from "../weekdays";

// The hit area is 44 px, the visible control smaller (inner span).
const stepBtn =
  "group flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center disabled:cursor-not-allowed";
const stepFace =
  "flex h-9 w-9 items-center justify-center rounded-full border border-slate-300 text-slate-700 transition-colors duration-150 group-hover:bg-slate-100 group-disabled:opacity-40 group-disabled:hover:bg-transparent dark:border-slate-600 dark:text-slate-200 dark:group-hover:bg-slate-800";

const todayBtn =
  "min-h-[44px] shrink-0 rounded-full border border-slate-300 px-3.5 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

/** Day choice of the overview: ‹ date › with the date as a button opening a
 *  month calendar (closed days marked, days before `minDay` disabled), and a
 *  "Heute" shortcut while another day is shown (on phones inside the
 *  calendar, the bar has no room for it). */
export function DateNav({
  day,
  today,
  minDay,
  closedDays,
  onChange,
}: {
  day: string;
  today: string;
  /** Earliest selectable day (null: past days allowed, e.g. department admins). */
  minDay: string | null;
  /** Days closed by blocks (public holidays): greyed, not selectable. */
  closedDays: Set<string>;
  onChange: (day: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState({ year: 0, month: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const rootRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));

  const prev = addDays(day, -1);
  const prevDisabled = minDay !== null && prev < minDay;

  function toggle() {
    if (!open) {
      const d = parseIso(day);
      setView({ year: d.getFullYear(), month: d.getMonth() });
    }
    setOpen(!open);
  }

  // Another day picked while the calendar is open closes it (its month would go stale).
  const go = (next: string) => {
    setOpen(false);
    onChange(next);
  };

  // The whole bar anchors the calendar, so on phones it starts at the gutter.
  return (
    <div
      ref={rootRef}
      className="relative flex flex-wrap items-center gap-x-0.5 gap-y-1"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(false);
          buttonRef.current?.focus();
        }
      }}
    >
      <button
        type="button"
        aria-label={t("Previous day")}
        disabled={prevDisabled}
        onClick={() => go(prev)}
        className={stepBtn}
      >
        <span className={stepFace}>
          <ChevronLeft aria-hidden className="h-5 w-5" />
        </span>
      </button>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${t("Pick a date")}: ${formatDayWithWeekday(day)}`}
        onClick={toggle}
        className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-slate-300 bg-white px-3.5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:border-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-slate-500"
      >
        <CalendarDays aria-hidden className="hidden h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400 sm:block" />
        {formatDayWithWeekday(day)}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={t("Pick a date")}
          className="absolute left-0 top-full z-30 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-3 shadow-lg dark:border-slate-700 dark:bg-slate-800"
        >
          <MonthCalendar
            year={view.year}
            month={view.month}
            onMonthChange={(year, month) => setView({ year, month })}
            isSelected={(iso) => iso === day}
            isClosed={(iso) => closedDays.has(iso)}
            isDisabled={(iso) => minDay !== null && iso < minDay}
            onDayClick={(iso) => {
              onChange(iso);
              setOpen(false);
              buttonRef.current?.focus();
            }}
          />
          {/* Phones: "Heute" lives here, the bar has no room for it. */}
          {day !== today && (
            <button
              type="button"
              onClick={() => {
                go(today);
                buttonRef.current?.focus();
              }}
              className={`${todayBtn} mt-2 w-full sm:hidden`}
            >
              {t("Today")}
            </button>
          )}
        </div>
      )}
      <button
        type="button"
        aria-label={t("Next day")}
        onClick={() => go(addDays(day, 1))}
        className={stepBtn}
      >
        <span className={stepFace}>
          <ChevronRight aria-hidden className="h-5 w-5" />
        </span>
      </button>
      {day !== today && (
        <button type="button" onClick={() => go(today)} className={`${todayBtn} hidden sm:inline-flex sm:items-center`}>
          {t("Today")}
        </button>
      )}
    </div>
  );
}
