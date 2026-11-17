// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// "Wiederkehrend" mode: today's series flow (start day, weekdays, hours, end
// date, one place), moved here from the former Book page unchanged except
// that the end date stays within the open booking window. Task 11 replaces it.

import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MonthCalendar } from "../../components/MonthCalendar";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { HourRangePicker, type HourRange } from "../components/HourRangePicker";
import type { BookingWindow, PersonChoice, PlaceKind } from "../types";
import { addDays, addMonths, parseIso, weekdayName, weekdayOf } from "../weekdays";
import { BookAction, limitWarnings } from "./BookAction";
import { BookPlaces, freeRows } from "./BookPlaces";
import { Step } from "./Step";

export function BookSeries({
  pool,
  kind,
  today,
  window: w,
  closedWeekdays,
  isClosed,
  holder,
  forOther,
  comment,
  onComment,
  initialDay,
  initialPlace,
}: {
  pool: number;
  kind: PlaceKind;
  today: string;
  window: BookingWindow;
  closedWeekdays: number[];
  isClosed: (iso: string) => boolean;
  holder: PersonChoice | null;
  /** "Book for another person", shown between place and comment. */
  forOther: ReactNode;
  comment: string;
  onComment: (text: string) => void;
  initialDay: string | null;
  initialPlace: number | null;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const [month, setMonth] = useState(() => {
    const base = parseIso(initialDay ?? today);
    return { year: base.getFullYear(), month: base.getMonth() };
  });
  const [day, setDay] = useState<string | null>(initialDay);
  const [weekdays, setWeekdays] = useState<number[]>(() =>
    initialDay && !closedWeekdays.includes(weekdayOf(initialDay)) ? [weekdayOf(initialDay)] : [],
  );
  const [range, setRange] = useState<HourRange | null>(null);
  const [until, setUntil] = useState<string | null>(null);
  const [features, setFeatures] = useState<number[]>([]);
  const [selected, setSelected] = useState<number[]>(initialPlace ? [initialPlace] : []);
  const [busy, setBusy] = useState(false);
  const [focusPending, setFocusPending] = useState(initialPlace !== null);

  // A series is checked against its first occurrence: the first selected
  // weekday on or after the start date.
  let effDay: string | null = null;
  if (day) {
    for (let i = 0; i < 7 && !effDay; i++) {
      const d = addDays(day, i);
      if (weekdays.includes(weekdayOf(d))) effDay = d;
    }
  }
  const seriesDays = weekdays.filter((d) => !closedWeekdays.includes(d));
  // At most three months, and never beyond the open booking window.
  const maxUntil = day
    ? addMonths(day, 3) < w.open_until
      ? addMonths(day, 3)
      : w.open_until
    : null;
  const untilEff = until && maxUntil && until < maxUntil ? until : maxUntil;
  // A series that would produce no date at all cannot be created.
  const noDates = !!effDay && !!untilEff && (untilEff < effDay || effDay > w.open_until);

  const featureList = useFetch(() => desksApi.poolFeatures(pool), [pool]);
  const dayHours = useFetch(
    () => (effDay ? desksApi.hours(pool, effDay) : Promise.resolve(null)),
    [pool, effDay],
  );
  const ready = !!effDay && !!range;
  const free = useFetch(
    () =>
      ready
        ? desksApi.free({
            pool,
            kind,
            day: effDay!,
            start_hour: range.start,
            end_hour: range.end,
            features,
            holder: holder?.id ?? null,
          })
        : Promise.resolve(null),
    [pool, kind, effDay, range?.start, range?.end, features.join(","), holder?.id],
  );
  const overview = useFetch(
    () => (effDay ? desksApi.overview(pool, effDay) : Promise.resolve(null)),
    [pool, effDay],
  );
  const rows = free.data ? freeRows(free.data) : null;
  const picked = selected.filter((id) => rows?.some((p) => p.id === id));

  async function bookSeries(placeId: number) {
    if (!day || !range || !untilEff) return;
    setBusy(true);
    try {
      const res = await desksApi.createSeries({
        place_id: placeId,
        weekdays: seriesDays,
        start_hour: range.start,
        end_hour: range.end,
        valid_from: day,
        valid_until: untilEff,
        comment: comment.trim(),
        ...(holder ? { holder_id: holder.id } : {}),
      });
      toast.success(
        holder ? t("Series created for {{name}}.", { name: holder.name }) : t("Series created."),
      );
      if (holder) for (const msg of limitWarnings(res.warnings ?? [], t, holder.name)) toast.warning(msg);
      navigate(`/desks/series/${res.series.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const chip = (on: boolean) =>
    `min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
      on
        ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
        : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
    }`;

  return (
    <>
      <Step n={2} title={t("Start date")}>
        <div className="max-w-sm">
          <MonthCalendar
            year={month.year}
            month={month.month}
            onMonthChange={(year, m) => setMonth({ year, month: m })}
            isDisabled={(iso) => iso < today || iso > w.open_until}
            isClosed={isClosed}
            isSelected={(iso) => iso === day}
            onDayClick={(iso) => {
              setDay(iso);
              setRange(null);
              setUntil(null);
              if (weekdays.length === 0 && !closedWeekdays.includes(weekdayOf(iso)))
                setWeekdays([weekdayOf(iso)]);
            }}
          />
        </div>
      </Step>

      {day && (
        <Step n={3} title={t("Which weekdays?")}>
          <div role="group" aria-label={t("Weekdays")} className="flex flex-wrap gap-2">
            {[0, 1, 2, 3, 4, 5, 6]
              .filter((d) => !closedWeekdays.includes(d))
              .map((d) => {
                const on = weekdays.includes(d);
                return (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={on}
                    aria-label={weekdayName(d, "long")}
                    onClick={() => {
                      setWeekdays(on ? weekdays.filter((x) => x !== d) : [...weekdays, d].sort());
                      setRange(null);
                    }}
                    className={`${chip(on)} min-w-[48px] px-3`}
                  >
                    {weekdayName(d)}
                  </button>
                );
              })}
          </div>
        </Step>
      )}

      {effDay && (
        <Step n={4} title={t("Which hours?")}>
          {dayHours.loading && <Loading />}
          {dayHours.error && <ErrorBox message={dayHours.error} />}
          {dayHours.data && dayHours.data.open === null && (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {t("Booking is not possible on this day.")}
            </p>
          )}
          {dayHours.data && dayHours.data.open !== null && (
            <HourRangePicker
              open={dayHours.data.open}
              closed={dayHours.data.closed}
              minHour={dayHours.data.min_hour}
              value={range}
              onChange={setRange}
            />
          )}
          {day && maxUntil && untilEff && (
            <div className="mt-4">
              <label
                htmlFor="series-until"
                className="mb-1 block text-sm font-medium text-slate-900 dark:text-slate-100"
              >
                {t("Series ends on")}
              </label>
              <input
                id="series-until"
                type="date"
                min={day}
                max={maxUntil}
                value={untilEff}
                onChange={(e) => setUntil(e.target.value || null)}
                className="min-h-[44px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                {t("A series lasts at most three months. You can extend it later.")}
              </p>
              {noDates && (
                <p role="alert" className="mt-2 text-sm font-medium text-amber-800 dark:text-amber-300">
                  {t("No date lies in this period. Choose a later end date.")}
                </p>
              )}
            </div>
          )}
        </Step>
      )}

      {ready && (
        <Step n={5} title={t("Choose a place for the series")}>
          <BookPlaces
            pool={pool}
            kind={kind}
            rows={rows}
            loading={free.loading || overview.loading}
            error={free.error}
            floors={overview.data?.floors ?? null}
            lastFloorId={overview.data?.last_floor_id ?? null}
            featureList={featureList.data}
            features={features}
            onFeatures={setFeatures}
            totalDays={1}
            selected={picked}
            onSelect={setSelected}
            multi={false}
            focusPlace={focusPending ? initialPlace : null}
            onFocused={() => setFocusPending(false)}
          />
        </Step>
      )}

      {ready && forOther}

      {ready && picked.length > 0 && (
        <Step n={6} title={t("Comment (optional)")}>
          <BookAction
            comment={comment}
            onComment={onComment}
            label={t("Create series")}
            disabled={busy || noDates}
            onSubmit={() => bookSeries(picked[0])}
          />
        </Step>
      )}
    </>
  );
}
