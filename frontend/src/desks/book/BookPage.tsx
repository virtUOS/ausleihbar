// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DoorOpen, LampDesk, X } from "lucide-react";
import { SegmentedControl } from "@basicbar/ui";
import { selectedDays, type DayRange } from "../../dayRanges";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { useShowBooked } from "../bookNow";
import { useDesks } from "../DesksLayout";
import { rememberFloor } from "../location";
import { berlinNow } from "../time";
import type { BookingWindow, PersonChoice, PlaceDay, PlaceKind } from "../types";
import { useClosedDays } from "../useClosedDays";
import { addDays, weekdayOf } from "../weekdays";
import {
  BookAction,
  bookProblem,
  datesByPlace,
  limitWarnings,
  RequestNotice,
  type BookProblem,
} from "./BookAction";
import { BookDates, BookHours, WindowLine } from "./BookDates";
import { availabilityRows, BookPlaces } from "./BookPlaces";
import { BookSeries } from "./BookSeries";
import { ForWhom } from "./ForWhom";
import { Step } from "./Step";

type Mode = "calendar" | "recurring";

/** What `POST /reservations/days/` accepts in one call. */
const MAX_DAYS = 366;
const MAX_PLACES = 20;
const MAX_SLOTS = 1000;
/** `GET /places/<id>/days/` answers at most this many days after `from`. */
const PLACE_DAYS_SPAN = 400;

/** Book flow: kind and mode → days → hours → places → (for another person) →
 *  comment → action. Kalender mode books several days and places at once;
 *  Wiederkehrend creates a series. */
export function BookPage() {
  const { t } = useTranslation();
  const { pool, isAssistant } = useDesks();
  const toast = useToast();
  const navigate = useNavigate();
  const showBooked = useShowBooked();
  const today = berlinNow().date;

  // Prefill from links (?kind=&day=&start=&end=&place=&comment=).
  const [params] = useSearchParams();
  const [pre] = useState(() => {
    const d = params.get("day");
    const start = Number(params.get("start"));
    const end = Number(params.get("end"));
    const place = Number(params.get("place"));
    const day = d && /^\d{4}-\d{2}-\d{2}$/.test(d) && d >= today ? d : null;
    return {
      kind: params.get("kind") === "meeting_room" ? ("meeting_room" as PlaceKind) : ("desk" as PlaceKind),
      day,
      range:
        day && params.has("start") && start >= 0 && end > start && end <= 24 ? { start, end } : null,
      place: place > 0 ? place : null,
    };
  });

  const [kind, setKind] = useState<PlaceKind>(pre.kind);
  const [mode, setMode] = useState<Mode>("calendar");
  const [ranges, setRanges] = useState<DayRange[]>(pre.day ? [{ start: pre.day, end: pre.day }] : []);
  const [hours, setHours] = useState<{ start: number; end: number } | null>(pre.range);
  const [features, setFeatures] = useState<number[]>([]);
  const [selected, setSelected] = useState<number[]>(pre.place ? [pre.place] : []);
  // A place handed over in the link (removable): mutes the days it is taken
  // and shades the hours. Its floor is shown once in the places step.
  const [place, setPlace] = useState<number | null>(pre.place);
  const [focusPending, setFocusPending] = useState(pre.place !== null);
  const clearPlace = useCallback(() => {
    if (place !== null) setSelected((s) => s.filter((x) => x !== place));
    setPlace(null);
    setFocusPending(false);
  }, [place]);
  // Another department or kind drops the preselection.
  const scope = useRef({ pool, kind });
  useEffect(() => {
    if (scope.current.pool !== pool || scope.current.kind !== kind) clearPlace();
    scope.current = { pool, kind };
  }, [pool, kind, clearPlace]);
  const [showName, setShowName] = useState(false);
  const [comment, setComment] = useState(() => (params.get("comment") ?? "").slice(0, 200));
  // Assistants may book for another member of the department.
  const [holder, setHolder] = useState<PersonChoice | null>(null);
  useEffect(() => setHolder(null), [pool]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<BookProblem | null>(null);
  const [reload, setReload] = useState(0);

  const win = useFetch(() => desksApi.window(pool, holder?.id), [pool, holder?.id]);
  // While the window is fetched again (another holder), keep showing the
  // last one so that the steps below stay mounted.
  const [lastWin, setLastWin] = useState<BookingWindow | null>(null);
  useEffect(() => {
    if (win.data) setLastWin(win.data);
  }, [win.data]);
  useEffect(() => setLastWin(null), [pool]);
  const w = win.data ?? (win.loading ? lastWin : null);
  // Closed weekdays do not depend on the day.
  const meta = useFetch(() => desksApi.hours(pool, today), [pool, today]);
  const closedDays = useClosedDays(today, w?.advance_until ?? null, pool);
  // A prefilled day beyond the horizon can't be booked: drop it once the
  // window is known.
  // The calendar fixes its shown month at mount: remount it then, so that
  // it opens on today's month.
  const clamped = useRef(false);
  const [calendarKey, setCalendarKey] = useState(0);
  useEffect(() => {
    if (!w || clamped.current) return;
    clamped.current = true;
    if (pre.day && pre.day > w.advance_until) {
      setRanges([]);
      setCalendarKey((k) => k + 1);
    }
  }, [w, pre.day]);
  const closedWeekdays = meta.data?.closed_weekdays;
  const isClosed = useCallback(
    (iso: string) => !!closedWeekdays?.includes(weekdayOf(iso)) || closedDays.has(iso),
    [closedWeekdays, closedDays],
  );
  // The preselected place over the whole horizon (chunks the endpoint
  // accepts), so that month navigation needs no further requests.
  const advanceUntil = w?.advance_until ?? null;
  const placeDays = useFetch(() => {
    if (place === null || advanceUntil === null) return Promise.resolve(null);
    const calls: Promise<PlaceDay[]>[] = [];
    for (let from = today; from <= advanceUntil; from = addDays(from, PLACE_DAYS_SPAN + 1)) {
      const to = addDays(from, PLACE_DAYS_SPAN);
      calls.push(desksApi.placeDays(place, from, to < advanceUntil ? to : advanceUntil, holder?.id));
    }
    return Promise.all(calls).then((rows) => new Map(rows.flat().map((d) => [d.day, d])));
  }, [place, today, advanceUntil, holder?.id, reload]);
  // A place that can't be looked up (gone, other department) is dropped.
  useEffect(() => {
    if (placeDays.error) clearPlace();
  }, [placeDays.error, clearPlace]);
  const placeByDay = place !== null ? placeDays.data : null;
  const isMuted = useMemo(() => {
    if (!placeByDay) return undefined;
    return (iso: string) => {
      const d = placeByDay.get(iso);
      if (!d) return false;
      if (d.closed) return true;
      return hours ? d.taken.some((h) => h >= hours.start && h < hours.end) : d.taken.length > 0;
    };
  }, [placeByDay, hours]);
  const days = useMemo(
    () => (closedWeekdays ? selectedDays(ranges, (iso) => iso < today || isClosed(iso)) : []),
    [ranges, isClosed, closedWeekdays, today],
  );
  const daysKey = days.join(",");
  // Per hour: on how many chosen days the preselected place is taken.
  const hourCounts = useMemo(() => {
    if (!placeByDay) return undefined;
    const out: Record<number, number> = {};
    for (const day of days) for (const h of placeByDay.get(day)?.taken ?? []) out[h] = (out[h] ?? 0) + 1;
    return out;
  }, [placeByDay, days]);
  const tooManyDays = days.length > MAX_DAYS;
  const ready = mode === "calendar" && days.length > 0 && !!hours && !tooManyDays;

  const featureList = useFetch(() => desksApi.poolFeatures(pool), [pool]);
  const avail = useFetch(
    () =>
      ready
        ? desksApi.availability({
            pool,
            kind,
            days,
            start_hour: hours.start,
            end_hour: hours.end,
            features,
            holder: holder?.id ?? null,
          })
        : Promise.resolve(null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, pool, kind, daysKey, hours?.start, hours?.end, features.join(","), holder?.id, reload],
  );
  // Floors, plans and seats (structure only) from the first chosen day.
  const overview = useFetch(
    () => (ready ? desksApi.overview(pool, days[0]) : Promise.resolve(null)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, pool, days[0]],
  );
  const rows = avail.data ? availabilityRows(avail.data, overview.data?.floors ?? null, kind) : null;
  const rowById = new Map((rows ?? []).map((r) => [r.id, r]));
  // Only places that can be booked on every chosen day count as chosen.
  const picked = selected.filter((id) => {
    const r = rowById.get(id);
    return !!r && r.unavailableDays.length === 0;
  });
  const takenPicked = picked.map((id) => rowById.get(id)!).filter((r) => r.takenDays.length > 0);
  const tooManySlots = picked.length > MAX_PLACES || picked.length * days.length > MAX_SLOTS;
  // Taken dates (none unavailable: those places can't be chosen) are asked
  // of their holders; the free ones are booked at once.
  const requestMode = takenPicked.length > 0;
  const requestedCount = takenPicked.reduce((n, r) => n + r.takenDays.length, 0);
  const bookedCount = picked.length * days.length - requestedCount;
  const placeName = (id: number) => rowById.get(id)?.name ?? `#${id}`;

  /** A change of what is asked for drops the last refusal. */
  const changed =
    <A extends unknown[]>(fn: (...a: A) => void) =>
    (...a: A) => {
      setProblem(null);
      fn(...a);
    };

  async function book() {
    if (!hours || picked.length === 0) return;
    setBusy(true);
    setProblem(null);
    try {
      const res = await desksApi.bookDays({
        place_ids: picked,
        days,
        start_hour: hours.start,
        end_hour: hours.end,
        comment: comment.trim(),
        on_taken: requestMode ? "request" : "fail",
        ...(requestMode ? { show_name: showName } : {}),
        ...(holder ? { holder_id: holder.id } : {}),
      });
      if (res.requests.length > 0) {
        const parts = [];
        const n = res.reservations.length;
        if (n > 0)
          parts.push(
            holder
              ? t("{{count}} dates booked for {{name}}.", { count: n, name: holder.name })
              : t("{{count}} dates booked.", { count: n }),
          );
        parts.push(t("{{count}} release requests sent.", { count: res.requests.length }));
        toast.success(parts.join(" "));
      } else {
        toast.success(holder ? t("Booked for {{name}}.", { name: holder.name }) : t("Booked."));
      }
      const bookedFloor = rowById.get(picked[0])?.floor_id;
      if (bookedFloor) rememberFloor(pool, bookedFloor);
      if (res.warnings.includes("absent")) {
        const several = days.length > 1;
        toast.warning(
          holder
            ? several
              ? t("{{name}} is marked absent on some of these days. The bookings were still made.", { name: holder.name })
              : t("{{name}} is marked absent on this day. The booking was still made.", { name: holder.name })
            : several
              ? t("You are marked absent on some of these days. The bookings were still made.")
              : t("You are marked absent on this day. The booking was still made."),
        );
      }
      if (holder) for (const w of limitWarnings(res.warnings, t, holder.name)) toast.warning(w);
      if (holder) navigate("/desks");
      else showBooked(res);
    } catch (e) {
      const p = bookProblem(e, t, placeName);
      if (p) {
        setProblem(p);
        setReload((n) => n + 1);
      } else {
        toast.error(e instanceof Error ? e.message : t("The request failed."));
      }
    } finally {
      setBusy(false);
    }
  }

  const kindOptions = [
    {
      value: "desk" as PlaceKind,
      label: (
        <span className="inline-flex items-center gap-2">
          <LampDesk aria-hidden className="h-4 w-4" />
          {t("Desk")}
        </span>
      ),
      title: t("Desk"),
    },
    {
      value: "meeting_room" as PlaceKind,
      label: (
        <span className="inline-flex items-center gap-2">
          <DoorOpen aria-hidden className="h-4 w-4" />
          {t("Meeting room")}
        </span>
      ),
      title: t("Meeting room"),
    },
  ];

  let notice = null;
  if (tooManySlots) {
    notice = (
      <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
        {t("At most {{count}} places and 1000 bookings can be made at once. Choose fewer days or places.", {
          count: MAX_PLACES,
        })}
      </p>
    );
  } else if (requestMode) {
    notice = (
      <RequestNotice
        lines={datesByPlace(
          takenPicked.flatMap((r) => r.takenDays.map((day) => ({ day, place_id: r.id }))),
          placeName,
        )}
        bookedCount={bookedCount}
        requestedCount={requestedCount}
        showName={showName}
        onShowName={setShowName}
      />
    );
  }

  return (
    <div>
      <Step n={1} title={t("What do you need?")}>
        <div className="flex flex-col gap-3">
          {isAssistant && <ForWhom pool={pool} value={holder} onChange={changed(setHolder)} />}
          <SegmentedControl
            size="md"
            ariaLabel={t("Kind")}
            value={kind}
            onChange={changed(setKind)}
            options={kindOptions}
            className="w-full sm:w-max"
          />
          <SegmentedControl
            size="md"
            ariaLabel={t("Booking mode")}
            value={mode}
            onChange={changed(setMode)}
            options={[
              { value: "calendar" as Mode, label: t("Calendar") },
              { value: "recurring" as Mode, label: t("Recurring") },
            ]}
            className="w-full sm:w-max"
          />
          {w && <WindowLine window={w} />}
        </div>
      </Step>

      {((!w && win.loading) || meta.loading) && <Loading />}
      {win.error && <ErrorBox message={win.error} />}
      {meta.error && <ErrorBox message={meta.error} />}

      {w && meta.data && mode === "recurring" && (
        <BookSeries
          key={`${pool}-${kind}`}
          pool={pool}
          kind={kind}
          today={today}
          window={w}
          closedWeekdays={meta.data.closed_weekdays}
          isClosed={isClosed}
          holder={holder}
          comment={comment}
          onComment={setComment}
          initialDay={pre.day}
          initialPlace={place}
        />
      )}

      {w && meta.data && mode === "calendar" && (
        <>
          <Step n={2} title={t("Which days?")}>
            {place !== null && (
              <button
                type="button"
                onClick={changed(clearPlace)}
                className="mb-3 inline-flex min-h-[44px] items-center gap-1.5 rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <X aria-hidden className="h-4 w-4" />
                {t("Remove place")}
              </button>
            )}
            <BookDates
              key={calendarKey}
              value={ranges}
              onChange={changed(setRanges)}
              today={today}
              window={w}
              isClosed={isClosed}
              isMuted={isMuted}
              mutedLegend={
                isMuted ? t("Greyed days: the preselected place is taken or closed then. They can still be chosen.") : undefined
              }
              dayCount={days.length}
            />
            {tooManyDays && (
              <p role="alert" className="mt-2 text-sm font-medium text-amber-800 dark:text-amber-300">
                {t("Choose at most {{count}} days at once.", { count: MAX_DAYS })}
              </p>
            )}
          </Step>

          {days.length > 0 && !tooManyDays && (
            <Step n={3} title={t("Which hours?")}>
              <BookHours
                pool={pool}
                kind={kind}
                days={days}
                value={hours}
                onChange={changed(setHours)}
                counts={hourCounts}
              />
            </Step>
          )}

          {ready && (
            <Step n={4} title={t("Choose a place")}>
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
                totalDays={days.length}
                selected={picked}
                onSelect={changed(setSelected)}
                multi
                focusPlace={focusPending ? place : null}
                onFocused={() => setFocusPending(false)}
              />
            </Step>
          )}


          {ready && (picked.length > 0 || problem) && (
            <Step n={5} title={t("Comment (optional)")}>
              <BookAction
                comment={comment}
                onComment={setComment}
                label={requestMode ? t("Request room swap") : t("Book {{count}} places", { count: picked.length })}
                disabled={busy || picked.length === 0 || tooManySlots}
                onSubmit={book}
                notice={notice}
                problem={problem}
              />
            </Step>
          )}
        </>
      )}
    </div>
  );
}
