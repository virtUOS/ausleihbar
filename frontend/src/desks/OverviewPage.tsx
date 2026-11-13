// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, DoorOpen, List, Map as MapIcon } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDayWithWeekday } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { FloorPlanView, type PlanPlace } from "./components/FloorPlanView";
import { MeetingTimeline } from "./components/MeetingTimeline";
import { PlaceSheet } from "./components/PlaceSheet";
import {
  AdminReservationActions,
  isManageable,
  useHolderText,
} from "./components/AdminReservationActions";
import { StateLegend, StatePill, stateLabel, type DrawState } from "./components/placeStates";
import { berlinNow } from "./time";
import { addDays, pad2 } from "./weekdays";
import type { ManageReservation, OverviewFloor, OverviewPlace } from "./types";

const pad = (h: number) => `${pad2(h)}:00`;

function stateAt(p: OverviewPlace, hour: number | null): DrawState {
  if (hour === null) return "closed";
  return p.hours.find((h) => h.hour === hour)?.state ?? "closed";
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
  // Department admins act on others' reservations (by reservation id).
  const admin = useFetch(
    () => (isAdmin ? desksApi.manageReservations(pool, day) : Promise.resolve([])),
    [pool, day, reload, isAdmin],
  );
  const manageable = useMemo(
    () => (admin.data ?? []).filter((r) => isManageable(r)),
    [admin.data],
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

  const selectedId =
    reservationAt(data?.floors ?? [], openId, hour);
  const adminRow = manageable.find((r) => r.id === selectedId) ?? null;

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
                <PlanPane key={floor.id} floor={floor} hour={hour} onOpen={setOpenId} />
              ) : (
                <PlaceList floor={floor} hour={hour} onOpen={setOpenId} />
              )}
            </section>
          )}

          {data.floors.length === 0 && (
            <Empty icon={DoorOpen} label={t("This department has no places yet.")} />
          )}

          {isAdmin && manageable.length > 0 && (
            <AdminReservationList rows={manageable} onChanged={() => setReload((n) => n + 1)} />
          )}

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
          adminRow={adminRow}
          onClose={() => setOpenId(null)}
          onChanged={() => setReload((n) => n + 1)}
        />
      )}
    </div>
  );
}

/** The reservation of the opened place at the selected hour, if any. */
function reservationAt(
  floors: OverviewFloor[],
  placeId: number | null,
  hour: number | null,
): number | null {
  if (placeId === null || hour === null) return null;
  for (const f of floors) {
    const p = f.places.find((x) => x.id === placeId);
    if (p) return p.hours.find((h) => h.hour === hour)?.reservation_id ?? null;
  }
  return null;
}

/** Department admins: the day's current reservations of others, to move or
 *  cancel (also those of hidden holders, shown as "Person (verborgen)"). */
function AdminReservationList({
  rows,
  onChanged,
}: {
  rows: ManageReservation[];
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const holderText = useHolderText();
  const [openRow, setOpenRow] = useState<number | null>(null);
  return (
    <section aria-labelledby="admin-res-title" className="mb-8">
      <h2 id="admin-res-title" className="mb-2 text-base font-bold text-slate-900 dark:text-slate-100">
        {t("Manage reservations")}
      </h2>
      <ul className="space-y-2">
        {rows.map((r) => {
          const expanded = openRow === r.id;
          return (
            <li
              key={r.id}
              className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
            >
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpenRow(expanded ? null : r.id)}
                className="flex min-h-[56px] w-full items-center justify-between gap-3 p-3 text-left"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium text-slate-900 dark:text-slate-100">
                    {r.place.name} · {pad(r.start_hour)}–{pad(r.end_hour)}
                  </span>
                  <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                    {[holderText(r), r.place.room].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <ChevronRight
                  aria-hidden
                  className={`h-5 w-5 shrink-0 text-slate-500 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
                />
              </button>
              {expanded && (
                <div className="border-t border-slate-200 p-3 dark:border-slate-700">
                  <AdminReservationActions
                    reservation={r}
                    onChanged={() => {
                      setOpenRow(null);
                      onChanged();
                    }}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
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
  const places: PlanPlace[] = useMemo(
    () =>
      floor.places.map((p) => ({
        id: p.id,
        name: p.name,
        kind: p.kind,
        symbol: p.plan_symbol,
        state: stateAt(p, hour),
        mine: hour !== null && !!p.hours.find((h) => h.hour === hour)?.mine,
      })),
    [floor, hour],
  );
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
    .map((r) => ({ key: String(r.id), room: r.name, places: floor.places.filter((p) => p.room_id === r.id) }))
    .filter((g) => g.places.length > 0);
  const known = new Set(floor.rooms.map((r) => r.id));
  const rest = floor.places.filter((p) => !known.has(p.room_id));
  if (rest.length) groups.push({ key: "none", room: "", places: rest });
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <div key={g.key}>
          {g.room && (
            <h3 className="mb-1 text-sm font-bold text-slate-800 dark:text-slate-100">{g.room}</h3>
          )}
          <ul className="space-y-2">
            {g.places.map((p) => {
              const s = stateAt(p, hour);
              const h = hour !== null ? p.hours.find((x) => x.hour === hour) : undefined;
              const ownFixed = !!h?.mine && !h.reservation_id;
              const holderText = ownFixed
                ? t("Your fixed desk")
                : h?.holder
                  ? h.mine
                    ? t("Your reservation")
                    : h.holder
                  : "";
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => onOpen(p.id)}
                    aria-label={[`${p.name}: ${stateLabel(t, s)}`, holderText].filter(Boolean).join(", ")}
                    className="flex min-h-[56px] w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 text-left hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-slate-900 dark:text-slate-100">
                        {p.name}
                        {p.kind === "meeting_room" && p.capacity
                          ? ` · ${t("{{count}} seats", { count: p.capacity })}`
                          : ""}
                      </span>
                      {holderText && (
                        <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                          {holderText}
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
