// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { formatDate } from "../../dates";
import type { DayRange } from "../../dayRanges";
import { MultiDayCalendar } from "../../components/MultiDayCalendar";
import { ErrorBox, Loading } from "../../components/Status";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { PlaceTimeline, type TimelineEntry } from "../components/PlaceTimeline";
import type { BookingWindow, PlaceKind } from "../types";
import { pad2, weekdayOf } from "../weekdays";

const pad = (h: number) => `${pad2(h)}:00`;

/** The booking window in words: how far bookings are open, when the next
 *  period opens, and what the advance quota still allows beyond that. */
export function WindowLine({ window: w }: { window: BookingWindow }) {
  const { t } = useTranslation();
  const beyond = w.advance_until > w.open_until;
  return (
    <div className="space-y-0.5 text-sm text-slate-600 dark:text-slate-300">
      <p>
        {t("Bookable until {{date}}", { date: formatDate(w.open_until) })}
        {w.today < w.transition_from && (
          <> · {t("From {{date}} the next period can be booked, too.", { date: formatDate(w.transition_from) })}</>
        )}
      </p>
      {beyond && (
        <p>
          {t("Beyond that up to {{date}}: {{count}} more days", {
            date: formatDate(w.advance_until),
            count: w.advance_days_left,
          })}
        </p>
      )}
    </div>
  );
}

/** Kalender mode: several days or ranges between today and the end of the
 *  advance horizon. Days beyond the open window carry a dot ("Advance
 *  booking"); closed days can't be chosen. */
export function BookDates({
  value,
  onChange,
  today,
  window: w,
  isClosed,
  dayCount,
}: {
  value: DayRange[];
  onChange: (next: DayRange[]) => void;
  today: string;
  window: BookingWindow;
  isClosed: (iso: string) => boolean;
  /** Bookable days in the selection (closed ones left out). */
  dayCount: number;
}) {
  const { t } = useTranslation();
  const beyond = w.advance_until > w.open_until;
  return (
    <div>
      <MultiDayCalendar
        value={value}
        onChange={onChange}
        minDay={today}
        maxDay={w.advance_until}
        isClosed={isClosed}
        renderDay={(iso) =>
          iso > w.open_until && !isClosed(iso) ? (
            <span className="mt-1 block h-1.5 w-1.5 rounded-full bg-current opacity-70" />
          ) : null
        }
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-300">
        <p aria-live="polite">
          {dayCount > 0
            ? t("{{count}} days chosen", { count: dayCount })
            : t("Tap a day, or the first and the last day of a period.")}
        </p>
        {beyond && (
          <p className="inline-flex items-center gap-1.5">
            <span aria-hidden className="block h-1.5 w-1.5 rounded-full bg-slate-700 dark:bg-slate-200" />
            {t("Advance booking (limited number of days)")}
          </p>
        )}
      </div>
    </div>
  );
}

/** The common open hours of the chosen days: the first day's open span,
 *  closed hours and (today) first bookable hour; when the weekdays differ,
 *  the intersection of their spans (one request per distinct weekday). */
function useCommonHours(pool: number, days: string[]) {
  const reps = useMemo(() => {
    const seen = new Set<number>();
    const out: string[] = [];
    for (const d of days) {
      const wd = weekdayOf(d);
      if (!seen.has(wd)) {
        seen.add(wd);
        out.push(d);
      }
    }
    return out;
  }, [days]);
  const res = useFetch(
    () => (reps.length ? Promise.all(reps.map((d) => desksApi.hours(pool, d))) : Promise.resolve(null)),
    [pool, reps.join(",")],
  );
  const info = useMemo(() => {
    const rows = res.data;
    if (!rows || rows.length === 0) return null;
    const first = rows[0];
    let open: [number, number] | null = first.open;
    let differs = false;
    for (const r of rows.slice(1)) {
      if (!r.open || !open) continue;
      if (r.open[0] !== open[0] || r.open[1] !== open[1]) differs = true;
      open = [Math.max(open[0], r.open[0]), Math.min(open[1], r.open[1])];
    }
    if (open && open[0] >= open[1]) open = null;
    return { open, closed: first.closed, minHour: first.min_hour ?? 0, differs };
  }, [res.data]);
  return { ...res, info };
}

/** One hour range for every chosen day, picked on the timeline (select
 *  mode, no place: no per-hour counts). A range that no longer fits the
 *  common hours of a new selection is dropped. */
export function BookHours({
  pool,
  kind,
  days,
  value,
  onChange,
}: {
  pool: number;
  kind: PlaceKind;
  days: string[];
  value: { start: number; end: number } | null;
  onChange: (r: { start: number; end: number } | null) => void;
}) {
  const { t } = useTranslation();
  const { loading, error, info } = useCommonHours(pool, days);

  useEffect(() => {
    if (!info || !value) return;
    const fits =
      !!info.open &&
      value.start >= info.open[0] &&
      value.end <= info.open[1] &&
      value.start >= info.minHour &&
      !info.closed.some((h) => h >= value.start && h < value.end);
    if (!fits) onChange(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info]);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!info) return null;
  if (!info.open) {
    return (
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {t("The chosen days have no business hours in common.")}
      </p>
    );
  }
  if (info.minHour >= info.open[1]) {
    return (
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {t("No hours are left today. Choose later days.")}
      </p>
    );
  }
  const entry: TimelineEntry = {
    id: 0,
    name: t("the chosen days"),
    kind,
    bookable: true,
    blocks: [],
  };
  return (
    <div>
      <PlaceTimeline
        entry={entry}
        open={info.open}
        booking={{ day: days[0], closed: info.closed, minHour: info.minHour, onBooked: () => {} }}
        bare
        slim
        select={{ value, onChange }}
      />
      <p className="mt-2 text-sm text-slate-700 dark:text-slate-200" aria-live="polite">
        {value ? (
          <span className="font-semibold text-slate-900 dark:text-slate-100">
            {pad(value.start)}–{pad(value.end)}
          </span>
        ) : (
          t("Tap the start and end hour, or drag across the hours with the mouse.")
        )}
      </p>
      {info.differs && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {t("The business hours differ between the chosen days; only the hours open on all of them are shown.")}
        </p>
      )}
    </div>
  );
}
