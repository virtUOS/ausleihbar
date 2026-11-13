// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Armchair, DoorOpen, Hand, List, Map as MapIcon, Repeat } from "lucide-react";
import { ApiError } from "../api";
import { useFetch } from "../useFetch";
import { MonthCalendar } from "../components/MonthCalendar";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { FeatureFilter, featureNames } from "./components/FeatureFilter";
import { HourRangePicker, type HourRange } from "./components/HourRangePicker";
import { FavoriteToggle } from "./components/FavoriteToggle";
import { FloorPlanView, type PlanPlace } from "./components/FloorPlanView";
import { favoritesFirst, useFavorites } from "./favorites";
import { PersonPicker } from "./components/PersonPicker";
import { StateLegend } from "./components/placeStates";
import { addDays, addMonths, isoOf, parseIso, weekdayName, weekdayOf } from "./weekdays";
import type { BookConflict, FreePlace, PersonChoice, PlaceBrief, PlaceKind } from "./types";


function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`step-${n}`} className="mb-6">
      <h2
        id={`step-${n}`}
        className="mb-2 flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100"
      >
        <span
          aria-hidden
          className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-slate-900"
        >
          {n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

interface TakenPlace {
  id: number;
  name: string;
  where: string;
  holder: string | null;
  reservationId: number;
}

/** Book flow: kind → day → hours → equipment → places → comment. */
export function BookPage() {
  const { t } = useTranslation();
  const { pool, isAssistant } = useDesks();
  const toast = useToast();
  const navigate = useNavigate();
  const today = new Date();
  const todayIso = isoOf(today);
  // Prefill from the overview (?place=&kind=&day=&start=&end=).
  const [params] = useSearchParams();
  const pre = (() => {
    const d = params.get("day");
    const start = Number(params.get("start"));
    const end = Number(params.get("end"));
    const place = Number(params.get("place"));
    if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d) || d < todayIso) return null;
    return {
      day: d,
      kind: params.get("kind") === "meeting_room" ? ("meeting_room" as PlaceKind) : ("desk" as PlaceKind),
      range: start >= 0 && end > start && end <= 24 && params.has("start") ? { start, end } : null,
      place: place > 0 ? place : null,
    };
  })();

  const [kind, setKind] = useState<PlaceKind>(pre?.kind ?? "desk");
  const [month, setMonth] = useState(() => {
    const base = pre ? parseIso(pre.day) : today;
    return { year: base.getFullYear(), month: base.getMonth() };
  });
  const [day, setDay] = useState<string | null>(pre?.day ?? null);
  const [range, setRange] = useState<HourRange | null>(pre?.range ?? null);
  const [features, setFeatures] = useState<number[]>([]);
  const favorites = useFavorites();
  const [selected, setSelected] = useState<number[]>(pre?.place ? [pre.place] : []);
  const [mode, setMode] = useState<"list" | "plan">("list");
  const [floorId, setFloorId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  // Assistants may book for another member of the department.
  const [holder, setHolder] = useState<PersonChoice | null>(null);
  useEffect(() => setHolder(null), [pool]);
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState<BookConflict | null>(null);
  const [requesting, setRequesting] = useState<number | null>(null);
  const [showName, setShowName] = useState(false);
  const [reload, setReload] = useState(0);
  const [recurring, setRecurring] = useState(false);
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [until, setUntil] = useState<string | null>(null);

  const featureList = useFetch(() => desksApi.poolFeatures(pool), [pool]);
  // Booking horizon and closed weekdays do not depend on the day.
  const meta = useFetch(() => desksApi.hours(pool, todayIso), [pool, todayIso]);
  // A series is checked against its first occurrence: the first selected
  // weekday on or after the start date.
  let effDay = day;
  if (recurring && day) {
    effDay = null;
    for (let i = 0; i < 7 && !effDay; i++) {
      const d = addDays(day, i);
      if (weekdays.includes(weekdayOf(d))) effDay = d;
    }
  }
  const seriesDays = weekdays.filter((d) => !meta.data?.closed_weekdays.includes(d));
  const maxUntil = day ? addMonths(day, 3) : null;
  const untilEff = until && maxUntil && until < maxUntil ? until : maxUntil;
  // A series that would produce no date at all cannot be created.
  const noDates =
    recurring && !!effDay && !!untilEff && (untilEff < effDay || (!!meta.data?.max_day && effDay > meta.data.max_day));
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
    [pool, kind, effDay, range?.start, range?.end, features.join(","), reload, holder?.id],
  );
  const overview = useFetch(
    () => (ready ? desksApi.overview(pool, effDay!) : Promise.resolve(null)),
    [pool, effDay, reload, ready],
  );

  const freePlaces: FreePlace[] = free.data ?? [];
  const freeIds = new Set(freePlaces.map((p) => p.id));
  const picked = selected.filter((id) => freeIds.has(id));

  const taken: TakenPlace[] = [];
  if (ready && overview.data) {
    for (const floor of overview.data.floors) {
      for (const p of floor.places) {
        if (p.kind !== kind || freeIds.has(p.id)) continue;
        if (!features.every((id) => p.features.includes(id))) continue;
        const blocker = p.hours.find(
          (h) =>
            h.hour >= range.start && h.hour < range.end && h.reservation_id !== null && !h.mine,
        );
        if (!blocker || blocker.reservation_id === null) continue;
        const room = floor.rooms.find((r) => r.id === p.room_id)?.name;
        taken.push({
          id: p.id,
          name: p.name,
          where: [floor.building, floor.name, room].filter(Boolean).join(" · "),
          holder: blocker.holder,
          reservationId: blocker.reservation_id,
        });
      }
    }
  }

  const planFloors = (overview.data?.floors ?? []).filter(
    (f) => f.plan.shapes.length > 0 && f.places.some((p) => p.kind === kind && p.plan_symbol),
  );
  const planFloor = planFloors.find((f) => f.id === floorId) ?? planFloors[0] ?? null;
  const showPlan = mode === "plan" && !!planFloor;
  const freeKey = freePlaces.map((p) => p.id).join(",");
  const planPlaces = useMemo(
    () =>
      (planFloor?.places ?? [])
        .filter((p) => p.kind === kind)
        .map(
          (p): PlanPlace => ({
            id: p.id,
            name: p.name,
            kind: p.kind,
            symbol: p.plan_symbol,
            state: freeIds.has(p.id) ? "free" : "booked",
          }),
        ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [planFloor, kind, freeKey],
  );

  function toggle(id: number) {
    if (recurring) return setSelected([id]);
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

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
      navigate(`/desks/series/${res.series.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function book(placeIds: number[]) {
    if (!day || !range) return;
    setBusy(true);
    setConflict(null);
    try {
      const res = await desksApi.book({
        place_ids: placeIds,
        day,
        start_hour: range.start,
        end_hour: range.end,
        comment: comment.trim(),
        ...(holder ? { holder_id: holder.id } : {}),
      });
      toast.success(holder ? t("Booked for {{name}}.", { name: holder.name }) : t("Booked."));
      if (res.warnings.includes("absent")) {
        toast.warning(
          holder
            ? t("{{name}} is marked absent on this day. The booking was still made.", { name: holder.name })
            : t("You are marked absent on this day. The booking was still made."),
        );
      }
      navigate(holder ? "/desks/overview" : "/desks/mine");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const body = e.data as Partial<BookConflict> | undefined;
        setConflict({
          code: body?.code ?? "",
          detail: e.message,
          alternatives: body?.alternatives ?? [],
        });
        setReload((n) => n + 1);
      } else {
        toast.error(e instanceof Error ? e.message : t("The request failed."));
      }
    } finally {
      setBusy(false);
    }
  }

  async function sendRelease(t_: TakenPlace) {
    setBusy(true);
    try {
      await desksApi.requestRelease(t_.reservationId, showName);
      toast.success(t("Release request sent."));
      setRequesting(null);
      setShowName(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const kinds: { value: PlaceKind; label: string; Icon: typeof Armchair }[] = [
    { value: "desk", label: t("Desk"), Icon: Armchair },
    { value: "meeting_room", label: t("Meeting room"), Icon: DoorOpen },
  ];
  const chip = (on: boolean) =>
    `min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
      on
        ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
        : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
    }`;
  const btn =
    "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

  return (
    <div>
      {isAssistant && (
        <div className="mb-6 max-w-md">
          <PersonPicker pool={pool} value={holder} onChange={setHolder} label={t("Book for another person (optional)")} />
          {holder && (
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              {t("Free places are shown for {{name}}.", { name: holder.name })}
            </p>
          )}
        </div>
      )}
      <Step n={1} title={t("What do you need?")}>
        <div role="group" aria-label={t("Kind")} className="flex flex-wrap gap-2">
          {kinds.map(({ value, label, Icon }) => (
            <button
              key={value}
              type="button"
              aria-pressed={kind === value}
              onClick={() => setKind(value)}
              className={`${chip(kind === value)} inline-flex items-center gap-2`}
            >
              <Icon aria-hidden className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>
      </Step>

      <Step n={2} title={recurring ? t("Start date") : t("Which day?")}>
        <label className="mb-3 flex min-h-[44px] cursor-pointer items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-100">
          <input
            type="checkbox"
            checked={recurring}
            onChange={(e) => {
              setRecurring(e.target.checked);
              setRange(null);
              setSelected([]);
              setConflict(null);
              setUntil(null);
              setWeekdays(
                e.target.checked && day && !meta.data?.closed_weekdays.includes(weekdayOf(day))
                  ? [weekdayOf(day)]
                  : [],
              );
            }}
            className="h-5 w-5 accent-brand-600"
          />
          <Repeat aria-hidden className="h-4 w-4" />
          {t("Recurring")}
        </label>
        <div className="max-w-sm">
          <MonthCalendar
            year={month.year}
            month={month.month}
            onMonthChange={(year, m) => setMonth({ year, month: m })}
            isDisabled={(iso) =>
              iso < todayIso || (!!meta.data?.max_day && iso > meta.data.max_day)
            }
            isClosed={(iso) => {
              const [y, m, d] = iso.split("-").map(Number);
              const weekday = (new Date(y, m - 1, d).getDay() + 6) % 7;
              return !!meta.data?.closed_weekdays.includes(weekday);
            }}
            isSelected={(iso) => iso === day}
            onDayClick={(iso) => {
              setDay(iso);
              setRange(null);
              setConflict(null);
              setUntil(null);
              if (recurring && weekdays.length === 0 && !meta.data?.closed_weekdays.includes(weekdayOf(iso)))
                setWeekdays([weekdayOf(iso)]);
            }}
          />
        </div>
      </Step>

      {recurring && day && (
        <Step n={3} title={t("Which weekdays?")}>
          <div role="group" aria-label={t("Weekdays")} className="flex flex-wrap gap-2">
            {[0, 1, 2, 3, 4, 5, 6]
              .filter((d) => !meta.data?.closed_weekdays.includes(d))
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
                      setSelected([]);
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
        <Step n={recurring ? 4 : 3} title={t("Which hours?")}>
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
              onChange={(r) => {
                setRange(r);
                setConflict(null);
              }}
            />
          )}
          {recurring && day && maxUntil && untilEff && (
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
        <Step n={recurring ? 5 : 4} title={recurring ? t("Choose a place for the series") : t("Choose a place")}>
          {featureList.data && featureList.data.length > 0 && (
            <div className="mb-3">
              <FeatureFilter features={featureList.data} value={features} onChange={setFeatures} />
            </div>
          )}
          {conflict && (
            <div
              role="alert"
              className="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
            >
              <p className="font-medium">{conflict.detail}</p>
              {conflict.alternatives.length > 0 && (
                <>
                  <p className="mt-2">{t("These places are free instead:")}</p>
                  <ul className="mt-2 space-y-2">
                    {conflict.alternatives.map((alt: PlaceBrief) => (
                      <li key={alt.id}>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => book([alt.id])}
                          className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg border border-amber-400 bg-white px-3 py-2 text-left text-slate-900 hover:bg-amber-100 disabled:opacity-50 dark:bg-slate-900 dark:text-slate-100"
                        >
                          <span className="min-w-0">
                            <span className="block truncate font-medium">{alt.name}</span>
                            <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                              {[alt.floor, alt.room].filter(Boolean).join(" · ")}
                            </span>
                          </span>
                          <span className="shrink-0 text-sm font-semibold">{t("Book this")}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
          {(free.loading || overview.loading) && <Loading />}
          {free.error && <ErrorBox message={free.error} />}
          {free.data && freePlaces.length === 0 && taken.length === 0 && !overview.loading && (
            <Empty icon={Armchair} label={t("Nothing is available for this time.")} />
          )}
          {planFloors.length > 0 && free.data && (
            <div role="group" aria-label={t("View")} className="mb-3 flex gap-2">
              {(["list", "plan"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={(m === "plan") === showPlan}
                  onClick={() => setMode(m)}
                  className={`${chip((m === "plan") === showPlan)} inline-flex items-center gap-1.5`}
                >
                  {m === "plan" ? <MapIcon aria-hidden className="h-4 w-4" /> : <List aria-hidden className="h-4 w-4" />}
                  {m === "plan" ? t("Plan") : t("List")}
                </button>
              ))}
            </div>
          )}
          {showPlan && free.data && planFloor && (
            <div className="mb-4">
              {planFloors.length > 1 && (
                <div role="group" aria-label={t("Floor")} className="mb-2 flex gap-2 overflow-x-auto pb-1">
                  {planFloors.map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      aria-pressed={planFloor.id === f.id}
                      onClick={() => setFloorId(f.id)}
                      className={`${chip(planFloor.id === f.id)} shrink-0`}
                    >
                      {[f.building, f.name].filter(Boolean).join(" · ")}
                    </button>
                  ))}
                </div>
              )}
              <div className="mb-2">
                <StateLegend t={t} />
              </div>
              <FloorPlanView
                key={planFloor.id}
                shapes={planFloor.plan.shapes}
                places={planPlaces}
                selectedIds={picked}
                onPlaceClick={(id) => freeIds.has(id) && toggle(id)}
                describe={(p) => (freeIds.has(p.id) ? t("Free") : t("Not available for this time."))}
              />
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
                {t("Tap free places on the plan to select them.")}
              </p>
            </div>
          )}
          {free.data && (
            <ul className="space-y-2">
              {(showPlan ? [] : favoritesFirst(freePlaces, favorites.ids)).map((p) => {
                const on = picked.includes(p.id);
                return (
                  <li key={p.id}>
                    <label
                      className={`flex min-h-[56px] cursor-pointer items-center gap-3 rounded-xl border p-3 ${
                        on
                          ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20"
                          : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                      }`}
                    >
                      <input
                        type={recurring ? "radio" : "checkbox"}
                        name="series-place"
                        checked={on}
                        onChange={() => toggle(p.id)}
                        className="h-5 w-5 shrink-0 accent-brand-600"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium text-slate-900 dark:text-slate-100">
                          {p.name}
                          {p.kind === "meeting_room" && p.capacity
                            ? ` · ${t("{{count}} seats", { count: p.capacity })}`
                            : ""}
                        </span>
                        <span className="block truncate text-sm text-slate-600 dark:text-slate-300">
                          {[p.building, p.floor, p.room].filter(Boolean).join(" · ")}
                        </span>
                        {p.features.length > 0 && (
                          <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                            {featureNames(featureList.data ?? [], p.features).join(", ")}
                          </span>
                        )}
                      </span>
                      <span className="shrink-0 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                        {t("Free")}
                      </span>
                      <FavoriteToggle
                        name={p.name}
                        active={favorites.ids.has(p.id)}
                        onToggle={() => favorites.toggle(p.id)}
                      />
                    </label>
                  </li>
                );
              })}
              {(recurring ? [] : taken).map((p) => (
                <li
                  key={p.id}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60"
                >
                  <div className="flex items-center gap-3">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-slate-700 dark:text-slate-200">
                        {p.name}
                      </span>
                      <span className="block truncate text-sm text-slate-600 dark:text-slate-300">
                        {p.where}
                      </span>
                      <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                        {t("Booked by {{name}}", { name: p.holder ?? t("Person (hidden)") })}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setRequesting(requesting === p.id ? null : p.id)}
                      aria-expanded={requesting === p.id}
                      className={`${btn} inline-flex shrink-0 items-center gap-1.5`}
                    >
                      <Hand aria-hidden className="h-4 w-4" />
                      {t("Ask to release")}
                    </button>
                  </div>
                  {requesting === p.id && (
                    <div className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-700">
                      <label className="flex min-h-[44px] items-center gap-2 text-sm text-slate-800 dark:text-slate-100">
                        <input
                          type="checkbox"
                          checked={showName}
                          onChange={(e) => setShowName(e.target.checked)}
                          className="h-5 w-5 accent-brand-600"
                        />
                        {t("Show my name")}
                      </label>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => sendRelease(p)}
                        className="mt-2 min-h-[44px] rounded-full bg-slate-900 px-5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
                      >
                        {t("Send request")}
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Step>
      )}

      {ready && picked.length > 0 && (
        <Step n={recurring ? 6 : 5} title={t("Comment (optional)")}>
          <label htmlFor="book-comment" className="sr-only">
            {t("Comment")}
          </label>
          <input
            id="book-comment"
            type="text"
            maxLength={200}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            type="button"
            disabled={busy || noDates}
            onClick={() => (recurring ? bookSeries(picked[0]) : book(picked))}
            className="mt-4 min-h-[48px] w-full rounded-full bg-brand-500 px-6 text-base font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50 sm:w-auto"
          >
            {recurring ? t("Create series") : t("Book {{count}} places", { count: picked.length })}
          </button>
        </Step>
      )}
    </div>
  );
}
