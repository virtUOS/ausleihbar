// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, DoorOpen, Hand, List, Map as MapIcon } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDayWithWeekday, formatTime } from "../dates";
import { BottomSheet } from "../components/BottomSheet";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { FloorPlanView, type PlanPlace } from "./components/FloorPlanView";
import { StateLegend, stateLabel, stateMeta, type DrawState } from "./components/placeStates";
import { berlinNow } from "./time";
import { addDays } from "./weekdays";
import type { DepartmentDay, MeetingRoomDay, OverviewFloor, OverviewPlace } from "./types";

const pad = (h: number) => `${String(h).padStart(2, "0")}:00`;

function stateAt(p: OverviewPlace, hour: number | null): DrawState {
  if (hour === null) return "closed";
  return p.hours.find((h) => h.hour === hour)?.state ?? "closed";
}

function StatePill({ state }: { state: string }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${stateMeta(state).pill}`}
    >
      <span aria-hidden className="font-bold">
        {stateMeta(state).glyph}
      </span>
      {stateLabel(t, state)}
    </span>
  );
}

/** Department overview: plan or list per floor, meeting room timelines. */
export function OverviewPage() {
  const { t } = useTranslation();
  const { pool, isAdmin } = useDesks();
  const today = berlinNow();
  const [day, setDay] = useState(today.date);
  const [hour, setHour] = useState<number | null>(null);
  const [floorId, setFloorId] = useState<number | null>(null);
  const [mode, setMode] = useState<"plan" | "list">("plan");
  const [openId, setOpenId] = useState<number | null>(null);
  const [reload, setReload] = useState(0);

  const { data, loading, error } = useFetch(
    () => desksApi.overview(pool, day),
    [pool, day, reload],
  );

  // Default hour: now (today) or the first open hour; stays inside the opening hours.
  useEffect(() => {
    if (!data) return;
    const open = data.open_hours;
    if (!open) return setHour(null);
    const want = day === today.date ? today.hour : open[0];
    setHour((cur) =>
      cur !== null && cur >= open[0] && cur < open[1] ? cur : Math.min(Math.max(want, open[0]), open[1] - 1),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const floor: OverviewFloor | null =
    data?.floors.find((f) => f.id === floorId) ?? data?.floors[0] ?? null;
  const hasPlan = !!floor && floor.plan.shapes.length > 0;
  const showPlan = hasPlan && mode === "plan";

  const open = data?.open_hours ?? null;
  const hours = open ? Array.from({ length: open[1] - open[0] }, (_, i) => open[0] + i) : [];
  const minDay = isAdmin ? null : today.date;

  const found = useMemo(() => {
    if (!data || openId === null) return null;
    for (const f of data.floors) {
      const p = f.places.find((x) => x.id === openId);
      if (p) return { place: p, floor: f };
    }
    return null;
  }, [data, openId]);

  const input =
    "min-h-[44px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";
  const iconBtn =
    "flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";
  const chip = (on: boolean) =>
    `min-h-[44px] shrink-0 rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
      on
        ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
        : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
    }`;

  return (
    <div>
      {/* Day */}
      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          aria-label={t("Previous day")}
          disabled={minDay !== null && day <= minDay}
          onClick={() => setDay(addDays(day, -1))}
          className={iconBtn}
        >
          <ChevronLeft aria-hidden className="h-5 w-5" />
        </button>
        <label className="min-w-0 flex-1">
          <span className="sr-only">{t("Day")}</span>
          <input
            type="date"
            value={day}
            min={minDay ?? undefined}
            onChange={(e) => e.target.value && setDay(e.target.value)}
            className={`${input} w-full`}
          />
        </label>
        <button
          type="button"
          aria-label={t("Next day")}
          onClick={() => setDay(addDays(day, 1))}
          className={iconBtn}
        >
          <ChevronRight aria-hidden className="h-5 w-5" />
        </button>
        {day !== today.date && (
          <button type="button" onClick={() => setDay(today.date)} className={`${chip(false)} px-3`}>
            {t("Today")}
          </button>
        )}
      </div>
      <p className="mb-3 text-sm font-medium text-slate-800 dark:text-slate-100">
        {formatDayWithWeekday(day)}
      </p>

      {loading && !data && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <>
          {/* Floors */}
          {data.floors.length > 1 && (
            <div
              role="group"
              aria-label={t("Floor")}
              className="-mx-1 mb-3 flex gap-2 overflow-x-auto px-1 pb-1"
            >
              {data.floors.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={floor?.id === f.id}
                  onClick={() => setFloorId(f.id)}
                  className={chip(floor?.id === f.id)}
                >
                  {[f.building, f.name].filter(Boolean).join(" · ")}
                </button>
              ))}
            </div>
          )}

          {/* Hours */}
          {hours.length > 0 ? (
            <div
              role="group"
              aria-label={t("Hour")}
              className="-mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1"
            >
              {hours.map((h) => (
                <button
                  key={h}
                  type="button"
                  aria-pressed={hour === h}
                  onClick={() => setHour(h)}
                  className={`${chip(hour === h)} px-3`}
                >
                  {pad(h)}
                </button>
              ))}
            </div>
          ) : (
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
              {t("Closed on this day.")}
            </p>
          )}

          {floor && (
            <section aria-label={t("Places")} className="mb-8">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <StateLegend t={t} />
                {hasPlan && (
                  <div role="group" aria-label={t("View")} className="flex gap-1.5">
                    <button
                      type="button"
                      aria-pressed={showPlan}
                      onClick={() => setMode("plan")}
                      className={`${chip(showPlan)} inline-flex items-center gap-1.5 px-3`}
                    >
                      <MapIcon aria-hidden className="h-4 w-4" />
                      {t("Plan")}
                    </button>
                    <button
                      type="button"
                      aria-pressed={!showPlan}
                      onClick={() => setMode("list")}
                      className={`${chip(!showPlan)} inline-flex items-center gap-1.5 px-3`}
                    >
                      <List aria-hidden className="h-4 w-4" />
                      {t("List")}
                    </button>
                  </div>
                )}
              </div>
              {floor.places.length === 0 ? (
                <Empty icon={DoorOpen} label={t("No places on this floor.")} />
              ) : showPlan ? (
                <PlanPane floor={floor} hour={hour} onOpen={setOpenId} />
              ) : (
                <PlaceList floor={floor} hour={hour} onOpen={setOpenId} />
              )}
            </section>
          )}

          {data.floors.length === 0 && <Empty icon={DoorOpen} label={t("No places on this floor.")} />}

          {data.meeting_rooms.length > 0 && (
            <section aria-labelledby="mr-title" className="mb-8">
              <h2
                id="mr-title"
                className="mb-2 text-base font-bold text-slate-900 dark:text-slate-100"
              >
                {t("Meeting rooms")}
              </h2>
              <div className="space-y-3">
                {data.meeting_rooms.map((m) => (
                  <MeetingTimeline key={m.id} room={m} open={data.open_hours} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {data && found && (
        <PlaceSheet
          data={data}
          place={found.place}
          floor={found.floor}
          hour={hour}
          onClose={() => setOpenId(null)}
          onChanged={() => setReload((n) => n + 1)}
        />
      )}
    </div>
  );
}

function PlanPane({
  floor,
  hour,
  onOpen,
}: {
  floor: OverviewFloor;
  hour: number | null;
  onOpen: (id: number) => void;
}) {
  const { t } = useTranslation();
  const places: PlanPlace[] = floor.places.map((p) => ({
    id: p.id,
    name: p.name,
    kind: p.kind,
    symbol: p.plan_symbol,
    state: stateAt(p, hour),
    mine: hour !== null && !!p.hours.find((h) => h.hour === hour)?.mine,
  }));
  const unplaced = floor.places.filter((p) => !p.plan_symbol).length;
  return (
    <>
      <FloorPlanView
        shapes={floor.plan.shapes}
        places={places}
        onPlaceClick={onOpen}
      />
      {unplaced > 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          {t("{{count}} places are not on the plan. See the list.", { count: unplaced })}
        </p>
      )}
    </>
  );
}

function PlaceList({
  floor,
  hour,
  onOpen,
}: {
  floor: OverviewFloor;
  hour: number | null;
  onOpen: (id: number) => void;
}) {
  const { t } = useTranslation();
  const groups = floor.rooms
    .map((r) => ({ room: r.name, places: floor.places.filter((p) => p.room_id === r.id) }))
    .filter((g) => g.places.length > 0);
  const known = new Set(floor.rooms.map((r) => r.id));
  const rest = floor.places.filter((p) => !known.has(p.room_id));
  if (rest.length) groups.push({ room: "", places: rest });
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <div key={g.room}>
          {g.room && (
            <h3 className="mb-1 text-sm font-bold text-slate-800 dark:text-slate-100">{g.room}</h3>
          )}
          <ul className="space-y-2">
            {g.places.map((p) => {
              const s = stateAt(p, hour);
              const h = hour !== null ? p.hours.find((x) => x.hour === hour) : undefined;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => onOpen(p.id)}
                    aria-label={`${p.name}: ${stateLabel(t, s)}`}
                    className="flex min-h-[56px] w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-slate-900 dark:text-slate-100">
                        {p.name}
                        {p.kind === "meeting_room" && p.capacity
                          ? ` · ${t("{{count}} seats", { count: p.capacity })}`
                          : ""}
                      </span>
                      {h?.holder && (
                        <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                          {h.mine ? t("Your reservation") : h.holder}
                        </span>
                      )}
                    </span>
                    <StatePill state={s} />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function PlaceSheet({
  data,
  place,
  floor,
  hour,
  onClose,
  onChanged,
}: {
  data: DepartmentDay;
  place: OverviewPlace;
  floor: OverviewFloor;
  hour: number | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [showName, setShowName] = useState(false);
  const [busy, setBusy] = useState(false);
  const entry = hour !== null ? place.hours.find((h) => h.hour === hour) : undefined;
  const state = entry?.state ?? "closed";
  const room = floor.rooms.find((r) => r.id === place.room_id)?.name;
  const meeting = data.meeting_rooms.find((m) => m.id === place.id);
  const stretch = meeting?.reservations.find((r) => hour !== null && r.start_hour <= hour && hour < r.end_hour);
  const today = berlinNow();
  const bookable = state === "free" && hour !== null && (data.day > today.date || (data.day === today.date && hour >= today.hour));
  const releasable =
    !!entry?.reservation_id && !entry.mine && (state === "booked" || state === "potentially_free" || state === "late");

  function book() {
    const q = new URLSearchParams({
      place: String(place.id),
      kind: place.kind,
      day: data.day,
      start: String(hour),
      end: String(hour! + 1),
    });
    navigate(`/desks/book?${q}`);
  }

  async function sendRelease() {
    setBusy(true);
    try {
      await desksApi.requestRelease(entry!.reservation_id!, showName);
      toast.success(t("Release request sent."));
      onClose();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const holder = entry?.mine ? t("Your reservation") : entry?.holder;
  const btn =
    "inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold disabled:opacity-50";
  return (
    <BottomSheet open title={place.name} onClose={onClose}>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {[floor.building, floor.name, room].filter(Boolean).join(" · ")}
        {place.kind === "meeting_room" && place.capacity
          ? ` · ${t("{{count}} seats", { count: place.capacity })}`
          : ""}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatePill state={state} />
        {hour !== null && (
          <span className="text-sm text-slate-700 dark:text-slate-200">
            {t("at {{time}}", { time: pad(hour) })}
          </span>
        )}
      </div>
      {entry?.reservation_id !== null && entry && (
        <p className="mt-3 text-sm text-slate-800 dark:text-slate-100">
          {holder
            ? t("Booked by {{name}}", { name: holder })
            : t("Booked by {{name}}", { name: t("Person (hidden)") })}
        </p>
      )}
      {place.now?.until && state !== "closed" && data.day === today.date && hour === today.hour && (
        <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
          {state === "free" ? t("Free until {{time}}", { time: formatTime(place.now.until as string) }) : t("Until {{time}}", { time: formatTime(place.now.until as string) })}
        </p>
      )}
      {stretch?.comment && (
        <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{stretch.comment}</p>
      )}
      {place.fixed && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("Fixed desk")}</p>
      )}

      {/* The whole day of this place. */}
      <ul aria-label={t("Day")} className="mt-4 flex flex-wrap gap-1.5">
        {place.hours.map((h) => (
          <li
            key={h.hour}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${stateMeta(h.state).pill}`}
            title={`${pad(h.hour)} ${stateLabel(t, h.state)}`}
          >
            <span aria-hidden className="font-bold">{stateMeta(h.state).glyph}</span>
            <span>{h.hour}</span>
            <span className="sr-only">{`${pad(h.hour)} ${stateLabel(t, h.state)}`}</span>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap gap-2">
        {bookable && (
          <button type="button" onClick={book} className={`${btn} bg-brand-400 font-bold text-slate-900 hover:bg-brand-500`}>
            {t("Book")}
          </button>
        )}
        {releasable && (
          <button
            type="button"
            aria-expanded={asking}
            onClick={() => setAsking(!asking)}
            className={`${btn} border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
          >
            <Hand aria-hidden className="h-4 w-4" />
            {t("Ask to release")}
          </button>
        )}
        {entry?.mine && (
          <Link
            to="/desks/mine"
            className={`${btn} border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
          >
            {t("My reservations")}
          </Link>
        )}
      </div>
      {asking && releasable && (
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
            onClick={sendRelease}
            className={`${btn} mt-2 bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900`}
          >
            {t("Send request")}
          </button>
        </div>
      )}
    </BottomSheet>
  );
}

function MeetingTimeline({ room, open }: { room: MeetingRoomDay; open: [number, number] | null }) {
  const { t } = useTranslation();
  let from = open ? open[0] : 6;
  let to = open ? open[1] : 20;
  for (const r of room.reservations) {
    from = Math.min(from, r.start_hour);
    to = Math.max(to, r.end_hour);
  }
  const span = Math.max(to - from, 1);
  const cols = Array.from({ length: span }, (_, i) => from + i);
  const pct = (h: number) => `${((h - from) / span) * 100}%`;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2">
        <p className="font-medium text-slate-900 dark:text-slate-100">{room.name}</p>
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {[room.floor, room.room].filter(Boolean).join(" · ")}
          {room.capacity ? ` · ${t("{{count}} seats", { count: room.capacity })}` : ""}
        </p>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[560px]">
          <div className="relative h-5 text-[11px] text-slate-600 dark:text-slate-300" aria-hidden>
            {cols.map((h) => (
              <span key={h} className="absolute" style={{ left: pct(h) }}>
                {h}
              </span>
            ))}
          </div>
          <div className="relative h-16 rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
            {cols.slice(1).map((h) => (
              <span
                key={h}
                aria-hidden
                className="absolute inset-y-0 border-l border-slate-200 dark:border-slate-700"
                style={{ left: pct(h) }}
              />
            ))}
            {room.reservations.map((r) => (
              <div
                key={r.id}
                className={`absolute inset-y-1 overflow-hidden rounded-md border px-1.5 py-0.5 text-[11px] leading-tight ${stateMeta(r.state).pill} ${r.mine ? "ring-2 ring-brand-500" : ""}`}
                style={{ left: pct(r.start_hour), width: `calc(${((r.end_hour - r.start_hour) / span) * 100}% - 2px)` }}
                title={[`${pad(r.start_hour)}–${pad(r.end_hour)}`, r.holder ?? t("Person (hidden)"), r.comment].filter(Boolean).join(" · ")}
              >
                <span className="block truncate font-semibold">
                  {r.mine ? t("Your reservation") : (r.holder ?? t("Person (hidden)"))}
                </span>
                {r.comment && <span className="block truncate">{r.comment}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
      {room.reservations.length === 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">{t("No reservations this day.")}</p>
      )}
      <ul className="sr-only">
        {room.reservations.map((r) => (
          <li key={r.id}>
            {`${pad(r.start_hour)}–${pad(r.end_hour)}: ${r.holder ?? t("Person (hidden)")} ${r.comment}`}
          </li>
        ))}
      </ul>
    </div>
  );
}
