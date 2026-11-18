// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// "Wiederkehrend" mode: weekdays (from today up to an end date, by default
// the end of the booking window) → hours → one place → (for another person)
// → comment → "Create series", or "Request room swap" when some dates of the
// chosen place are taken by someone else.

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { formatDate } from "../../dates";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { berlinNow } from "../time";
import type { BookingWindow, DaysAvailability, PersonChoice, PlaceKind } from "../types";
import { addDays, weekdayName, weekdayOf } from "../weekdays";
import { BookAction, bookProblem, datesByPlace, limitWarnings, RequestNotice, type BookProblem } from "./BookAction";
import { BookHours } from "./BookDates";
import { availabilityRows, BookPlaces } from "./BookPlaces";
import { Step } from "./Step";

/** `GET /availability/` answers at most this many days per call. */
const AVAILABILITY_DAYS = 366;

/** Availability over any number of days: chunks the endpoint accepts,
 *  merged per place. */
async function availabilityOver(
  p: Omit<Parameters<typeof desksApi.availability>[0], "days">,
  days: string[],
): Promise<DaysAvailability[]> {
  const chunks: string[][] = [];
  for (let i = 0; i < days.length; i += AVAILABILITY_DAYS) chunks.push(days.slice(i, i + AVAILABILITY_DAYS));
  const parts = await Promise.all(chunks.map((c) => desksApi.availability({ ...p, days: c })));
  const byId = new Map<number, DaysAvailability>();
  for (const part of parts) {
    for (const r of part) {
      const seen = byId.get(r.id);
      byId.set(
        r.id,
        seen
          ? {
              ...seen,
              taken_days: [...seen.taken_days, ...r.taken_days],
              unavailable_days: [...seen.unavailable_days, ...r.unavailable_days],
            }
          : r,
      );
    }
  }
  return [...byId.values()];
}

export function BookSeries({
  pool,
  kind,
  today,
  window: w,
  closedWeekdays,
  isClosed,
  holder,
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
  comment: string;
  onComment: (text: string) => void;
  /** A day handed over in the link: its weekday is preselected. */
  initialDay: string | null;
  initialPlace: number | null;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const [weekdays, setWeekdays] = useState<number[]>(() =>
    initialDay && !closedWeekdays.includes(weekdayOf(initialDay)) ? [weekdayOf(initialDay)] : [],
  );
  // The end date as typed (kept while typing, e.g. a year digit by digit);
  // only a complete date within the limits counts.
  const [untilInput, setUntilInput] = useState<string | null>(null);
  const [hours, setHours] = useState<{ start: number; end: number } | null>(null);
  const [features, setFeatures] = useState<number[]>([]);
  const [selected, setSelected] = useState<number[]>(initialPlace ? [initialPlace] : []);
  const [focusPending, setFocusPending] = useState(initialPlace !== null);
  const [showName, setShowName] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<BookProblem | null>(null);
  const [reload, setReload] = useState(0);

  // The series starts today and ends at the latest with the open booking
  // window; booking for another person may reach up to the advance horizon
  // (with a warning).
  const maxUntil = holder ? w.advance_until : w.open_until;
  const untilEff =
    untilInput && /^\d{4}-\d{2}-\d{2}$/.test(untilInput) && untilInput >= today && untilInput <= maxUntil
      ? untilInput
      : w.open_until;
  const untilInvalid = untilInput !== null && untilInput !== untilEff;
  const beyondWindow = untilEff > w.open_until;

  // Its dates: the chosen weekdays up to the end, without closed days.
  const occurrences = useMemo(() => {
    const out: string[] = [];
    if (weekdays.length === 0) return out;
    for (let d = today; d <= untilEff; d = addDays(d, 1)) {
      if (weekdays.includes(weekdayOf(d)) && !isClosed(d)) out.push(d);
    }
    return out;
  }, [weekdays, today, untilEff, isClosed]);
  // Today only counts while the chosen hours have not begun (later its date
  // can't be booked any more): it neither narrows the hours to what is left
  // of today nor the places.
  const nowHour = berlinNow().hour;
  const hourDays = occurrences.length > 1 && occurrences[0] === today ? occurrences.slice(1) : occurrences;
  const days =
    hours && occurrences[0] === today && hours.start < nowHour ? occurrences.slice(1) : occurrences;
  const daysKey = days.join(",");
  const ready = days.length > 0 && !!hours && !untilInvalid;

  const featureList = useFetch(() => desksApi.poolFeatures(pool), [pool]);
  const avail = useFetch(
    () =>
      ready
        ? availabilityOver(
            {
              pool,
              kind,
              start_hour: hours.start,
              end_hour: hours.end,
              features,
              holder: holder?.id ?? null,
            },
            days,
          )
        : Promise.resolve(null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, pool, kind, daysKey, hours?.start, hours?.end, features.join(","), holder?.id, reload],
  );
  const overview = useFetch(
    () => (ready ? desksApi.overview(pool, days[0]) : Promise.resolve(null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, pool, days[0]],
  );
  // Dates no place can be booked on at these hours (e.g. partly blocked)
  // are left out: they neither count nor block a place.
  const skipped = useMemo(() => {
    const all = avail.data ?? [];
    if (all.length === 0) return new Set<string>();
    return new Set(days.filter((d) => all.every((r) => r.unavailable_days.includes(d))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avail.data, daysKey]);
  const countDays = days.length - skipped.size;
  const rows = avail.data
    ? availabilityRows(avail.data, overview.data?.floors ?? null, kind).map((r) => ({
        ...r,
        unavailableDays: r.unavailableDays.filter((d) => !skipped.has(d)),
      }))
    : null;
  // A place is selectable unless no date can be booked there; dates it is
  // unavailable on stay conflicts of the series.
  const row = rows?.find((r) => r.id === selected[0] && r.unavailableDays.length < countDays) ?? null;
  const openCount = row?.unavailableDays.length ?? 0;
  // Taken dates (one other booking each) are asked of their holders.
  const requestMode = !!row && row.takenDays.length > 0;
  const placeName = (id: number) => rows?.find((r) => r.id === id)?.name ?? `#${id}`;

  /** A change of what is asked for drops the last refusal. */
  const changed =
    <A extends unknown[]>(fn: (...a: A) => void) =>
    (...a: A) => {
      setProblem(null);
      fn(...a);
    };

  async function create() {
    if (!row || !hours) return;
    setBusy(true);
    setProblem(null);
    try {
      const res = await desksApi.createSeries({
        place_id: row.id,
        weekdays,
        start_hour: hours.start,
        end_hour: hours.end,
        valid_from: today,
        valid_until: untilEff,
        comment: comment.trim(),
        on_taken: requestMode ? "request" : "conflict",
        ...(requestMode ? { show_name: showName } : {}),
        ...(holder ? { holder_id: holder.id } : {}),
      });
      const n = res.created.length;
      const parts = [
        holder ? t("Series created for {{name}}.", { name: holder.name }) : t("Series created."),
        holder
          ? t("{{count}} dates booked for {{name}}.", { count: n, name: holder.name })
          : t("{{count}} dates booked.", { count: n }),
      ];
      if (res.requests.length > 0)
        parts.push(t("{{count}} release requests sent.", { count: res.requests.length }));
      if (res.conflicts.length > 0)
        parts.push(t("{{count}} dates could not be booked.", { count: res.conflicts.length }));
      toast.success(parts.join(" "));
      if (holder) for (const msg of limitWarnings(res.warnings ?? [], t, holder.name)) toast.warning(msg);
      navigate(`/desks/series/${res.series.id}`);
    } catch (e) {
      const p = bookProblem(e, t, placeName);
      if (p) {
        setProblem(p);
        setReload((x) => x + 1);
      } else {
        toast.error(e instanceof Error ? e.message : t("The request failed."));
      }
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
      <Step n={2} title={t("Which weekdays?")}>
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
                  onClick={changed(() => setWeekdays(on ? weekdays.filter((x) => x !== d) : [...weekdays, d].sort()))}
                  className={`${chip(on)} min-w-[48px] px-3`}
                >
                  {weekdayName(d)}
                </button>
              );
            })}
        </div>
        <div className="mt-4">
          <label htmlFor="series-until" className="mb-1 block text-sm font-medium text-slate-900 dark:text-slate-100">
            {t("Series ends on")}
          </label>
          <input
            id="series-until"
            type="date"
            min={today}
            max={maxUntil}
            value={untilInput ?? w.open_until}
            onChange={(e) => changed(setUntilInput)(e.target.value)}
            className="min-h-[44px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {t("The series starts today and can run until {{date}}, the end of the booking window. You can extend it later.", {
              date: formatDate(w.open_until),
            })}
          </p>
          {untilInvalid && (
            <p role="alert" className="mt-1 text-sm font-medium text-amber-800 dark:text-amber-300">
              {t("Choose an end date between {{from}} and {{until}}.", {
                from: formatDate(today),
                until: formatDate(maxUntil),
              })}
            </p>
          )}
          {holder && beyondWindow && (
            <p className="mt-1 text-sm font-medium text-amber-800 dark:text-amber-300">
              {t("The series for {{name}} reaches beyond the booking window.", { name: holder.name })}
            </p>
          )}
          {weekdays.length > 0 && !untilInvalid && (
            <p className="mt-1 text-sm text-slate-700 dark:text-slate-200" aria-live="polite">
              {occurrences.length > 0
                ? t("{{count}} dates in this period", { count: occurrences.length })
                : t("No date lies in this period. Choose a later end date.")}
            </p>
          )}
        </div>
      </Step>

      {hourDays.length > 0 && (
        <Step n={3} title={t("Which hours?")}>
          <BookHours pool={pool} kind={kind} days={hourDays} value={hours} onChange={changed(setHours)} />
        </Step>
      )}

      {ready && (
        <Step n={4} title={t("Choose a place for the series")}>
          <BookPlaces
            pool={pool}
            kind={kind}
            rows={rows}
            loading={avail.loading || overview.loading}
            error={avail.error}
            floors={overview.data?.floors ?? null}
            lastFloorId={overview.data?.last_floor_id ?? null}
            featureList={featureList.data}
            features={features}
            onFeatures={changed(setFeatures)}
            totalDays={countDays}
            selected={row ? [row.id] : []}
            onSelect={changed(setSelected)}
            multi={false}
            partial
            focusPlace={focusPending ? initialPlace : null}
            onFocused={() => setFocusPending(false)}
          />
          {skipped.size > 0 && (
            <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">
              {t("{{count}} dates can't be booked at these hours on any place and are left out.", {
                count: skipped.size,
              })}
            </p>
          )}
        </Step>
      )}


      {ready && (row || problem) && (
        <Step n={5} title={t("Comment (optional)")}>
          <BookAction
            comment={comment}
            onComment={onComment}
            label={requestMode ? t("Request room swap") : t("Create series")}
            disabled={busy || !row}
            onSubmit={create}
            problem={problem}
            notice={
              requestMode || openCount > 0 ? (
                <>
                  {openCount > 0 && (
                    <p className="mb-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
                      {t("{{count}} dates can't be booked and stay open on the series page.", { count: openCount })}
                    </p>
                  )}
                  {requestMode && (
                    <RequestNotice
                      lines={datesByPlace(
                        row.takenDays.map((day) => ({ day, place_id: row.id })),
                        placeName,
                      )}
                      bookedCount={countDays - row.takenDays.length - openCount}
                      requestedCount={row.takenDays.length}
                      showName={showName}
                      onShowName={setShowName}
                    />
                  )}
                </>
              ) : null
            }
          />
        </Step>
      )}
    </>
  );
}
