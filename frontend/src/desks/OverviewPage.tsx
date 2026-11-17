// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, ChevronRight, DoorOpen, List, Map as MapIcon } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDayWithWeekday } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { FloorPlanView, type PlanPlace } from "./components/FloorPlanView";
import {
  BLOCK_BOOKED,
  BLOCK_MINE,
  BLOCK_POSSIBLY_FREE,
  PlaceTimeline,
  TimelineAxis,
  meetingRoomEntry,
  placeEntry,
  type TimelineBooking,
} from "./components/PlaceTimeline";
import { WeekDayBar } from "./components/WeekDayBar";
import { DayLoadLegend } from "./components/DayLoadBar";
import { dayLoad } from "./dayLoad";
import { PlaceSheet } from "./components/PlaceSheet";
import {
  AdminReservationActions,
  isManageable,
  useHolderText,
} from "./components/AdminReservationActions";
import { StateLegend, type DrawState } from "./components/placeStates";
import { useFavorites } from "./favorites";
import { useClosedDays } from "./useClosedDays";
import { useRememberedFloor } from "./location";
import { LocationPicker } from "./components/LocationPicker";
import { SortToggle } from "../components/SortToggle";
import { berlinNow } from "./time";
import { addDays, pad2 } from "./weekdays";
import type { DepartmentDay, ManageReservation, OverviewFloor, OverviewPlace } from "./types";

const pad = (h: number) => `${pad2(h)}:00`;

function stateAt(p: OverviewPlace, hour: number | null): DrawState {
  if (hour === null) return "closed";
  return p.hours.find((h) => h.hour === hour)?.state ?? "closed";
}

/** The plan symbol of a day that is not today: booked only when no open
 *  hour is left, possibly free when some taken hours may come free (the
 *  half rings tell morning from afternoon). */
function dayState(p: OverviewPlace): DrawState {
  const open = p.hours.filter((h) => h.state !== "closed");
  if (open.length === 0) return "closed";
  if (open.some((h) => h.state === "free")) return "free";
  return open.some((h) => h.state === "potentially_free") ? "potentially_free" : "booked";
}

/** Department overview: plan or list per floor, meeting room timelines. */
export function OverviewPage() {
  const { t } = useTranslation();
  const { pool, isAdmin } = useDesks();
  // Re-render every minute so past hours stop being bookable while the page
  // stays open.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 60_000);
    return () => window.clearInterval(id);
  }, []);
  const today = berlinNow();
  const [day, setDay] = useState(today.date);
  const [hour, setHour] = useState<number | null>(null);
  const [mode, setMode] = useState<"plan" | "list">("plan");
  const [openId, setOpenId] = useState<number | null>(null);
  // Hour whose booking the place sheet shows first (a block clicked in the list).
  const [openHour, setOpenHour] = useState<number | null>(null);
  const openPlace = (id: number, at: number | null = null) => {
    setOpenHour(at);
    setOpenId(id);
  };
  const [reload, setReload] = useState(0);
  const favorites = useFavorites();
  const features = useFetch(() => desksApi.poolFeatures(pool), [pool]);

  const fetched = useFetch(
    () => desksApi.overview(pool, day),
    [pool, day, reload],
  );
  const { loading, error } = fetched;
  // A reload of the same day (after booking or an admin action) keeps the
  // page in place instead of collapsing it to the loading state.
  const [kept, setKept] = useState<DepartmentDay | null>(null);
  useEffect(() => {
    if (fetched.data) setKept(fetched.data);
  }, [fetched.data]);
  const data =
    fetched.data ?? (!error && kept?.day === day && kept.pool === pool ? kept : null);
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

  // The floor last used in this department, else the one of the latest own booking.
  const [floorId, setFloorId] = useRememberedFloor(pool, data?.floors, data?.last_floor_id);
  const floor: OverviewFloor | null = data?.floors.find((f) => f.id === floorId) ?? null;
  const floorRooms = (data?.meeting_rooms ?? []).filter((m) => m.floor_id === floor?.id);
  const hasPlan = !!floor && floor.plan.shapes.length > 0;
  const showPlan = hasPlan && mode === "plan";

  const minDay = isAdmin ? null : today.date;
  // The pills show the chosen day's week (or the coming one on a weekend).
  const closedDays = useClosedDays(addDays(day, -7), addDays(day, 7), pool);


  const found = useMemo(() => {
    if (!data || openId === null) return null;
    for (const f of data.floors) {
      const p = f.places.find((x) => x.id === openId);
      if (p) return { place: p, floor: f };
    }
    return null;
  }, [data, openId]);

  // Meeting rooms of the floor can be booked right in their timeline.
  const shownDay = data?.day ?? day;
  const minHour = shownDay < today.date ? null : shownDay === today.date ? today.hour : 0;
  const timelineBooking: TimelineBooking | undefined = data
    ? { day: data.day, closed: data.closed_hours, minHour, onBooked: () => setReload((n) => n + 1) }
    : undefined;
  const chip = (on: boolean) =>
    `min-h-[44px] shrink-0 rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
      on
        ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
        : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
    }`;

  return (
    <div>
      <WeekDayBar day={day} today={today.date} minDay={minDay} closedDays={closedDays} onChange={setDay} />
      <p className="mb-3 text-sm font-medium text-slate-800 dark:text-slate-100">
        {formatDayWithWeekday(day)}
      </p>

      {loading && !data && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <>
          <LocationPicker
            floors={data.floors}
            floorId={floor?.id ?? null}
            onChange={setFloorId}
            className="mb-3"
          />

          {!data.open_hours && (
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{t("Closed on this day.")}</p>
          )}

          {floor && (
            <section aria-label={t("Places")} className="mb-8">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                {showPlan ? (
                  <div className="flex flex-col gap-1">
                    <StateLegend t={t} />
                    <DayLoadLegend t={t} />
                  </div>
                ) : (
                  <TimelineLegend />
                )}
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
                <PlanPane
                  key={floor.id}
                  floor={floor}
                  hour={data.day === today.date ? hour : null}
                  onOpen={(id) => openPlace(id, data.day === today.date ? today.hour : null)}
                />
              ) : (
                <PlaceList
                  floor={floor}
                  pool={pool}
                  open={data.open_hours}
                  booking={timelineBooking}
                  onOpen={openPlace}
                />
              )}
            </section>
          )}

          {data.floors.length === 0 && (
            <Empty icon={DoorOpen} label={t("This department has no places yet.")} />
          )}

          {isAdmin && manageable.length > 0 && (
            <AdminReservationList rows={manageable} onChanged={() => setReload((n) => n + 1)} />
          )}

          {/* The list shows meeting rooms with their room; the plan view lists them here. */}
          {showPlan && floorRooms.length > 0 && (
            <section aria-labelledby="mr-title" className="mb-8">
              <h2
                id="mr-title"
                className="mb-2 text-base font-bold text-slate-900 dark:text-slate-100"
              >
                {t("Meeting rooms")}
              </h2>
              <div className="space-y-3">
                {floorRooms.map((m) => (
                  <PlaceTimeline
                    key={m.id}
                    entry={meetingRoomEntry(
                      m,
                      [m.floor, m.room].filter(Boolean).join(" · ") +
                        (m.capacity ? ` · ${t("{{count}} seats", { count: m.capacity })}` : ""),
                    )}
                    open={data.open_hours}
                    booking={timelineBooking}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {data && found && (
        <PlaceSheet
          key={`${found.place.id}-${openHour}`}
          data={data}
          place={found.place}
          floor={found.floor}
          focusHour={openHour}
          manageable={isAdmin ? manageable : []}
          features={features.data ?? []}
          booking={timelineBooking}
          favorite={{
            active: favorites.ids.has(found.place.id),
            onToggle: () => favorites.toggle(found.place.id),
          }}
          onClose={() => setOpenId(null)}
          onChanged={() => setReload((n) => n + 1)}
        />
      )}
    </div>
  );
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
        state: hour === null ? dayState(p) : stateAt(p, hour),
        // Today: the current hour; another day: any own booking that day.
        mine:
          hour !== null
            ? !!p.hours.find((h) => h.hour === hour)?.mine
            : p.hours.some((h) => h.mine && h.reservation_id !== null),
        load: dayLoad(p.hours),
      })),
    [floor, hour],
  );
  const unplaced = floor.places.filter((p) => !p.plan_symbol).length;
  return (
    <>
      <FloorPlanView
        shapes={floor.plan.shapes}
        places={places}
        scalePxPerM={floor.scale_px_per_m}
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

/** List view: per room a slim timeline row per place (others' bookings honey,
 *  own ones green); free hours can be selected and booked right there. */
type RoomSort = { key: "name" | "popularity"; desc: boolean };
const SORT_KEY = "desks.roomSort";

function storedSort(): RoomSort {
  try {
    const v = JSON.parse(window.localStorage.getItem(SORT_KEY) ?? "null");
    if (v && (v.key === "name" || v.key === "popularity")) return { key: v.key, desc: !!v.desc };
  } catch {
    // ignore: default order
  }
  return { key: "name", desc: false };
}

function PlaceList({
  floor,
  pool,
  open,
  booking,
  onOpen,
}: {
  floor: OverviewFloor;
  pool: number;
  open: [number, number] | null;
  booking?: TimelineBooking;
  /** Opens a place's details, at the hour of a clicked booking. */
  onOpen: (id: number, at?: number | null) => void;
}) {
  const { t } = useTranslation();
  // Room order: name or popularity, each ascending or descending (remembered).
  const [sort, setSortState] = useState<RoomSort>(storedSort);
  const setSort = (next: RoomSort) => {
    setSortState(next);
    try {
      window.localStorage.setItem(SORT_KEY, JSON.stringify(next));
    } catch {
      // not persisted (private mode)
    }
  };
  const popularity = useFetch(
    () => (sort.key === "popularity" ? desksApi.roomPopularity(pool) : Promise.resolve(null)),
    [pool, sort.key],
  );
  const rank = new Map((popularity.data?.order ?? []).map((id, i) => [id, i]));
  const rooms = [...floor.rooms].sort((a, b) => {
    const by =
      sort.key === "popularity"
        ? (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity) ||
          a.name.localeCompare(b.name, undefined, { numeric: true })
        : a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
    // Popularity: "descending" = most popular first (the natural reading).
    return sort.key === "popularity" ? (sort.desc ? by : -by) : sort.desc ? -by : by;
  });
  const groups = rooms
    .map((r) => ({ key: String(r.id), room: r.name, places: floor.places.filter((p) => p.room_id === r.id) }))
    .filter((g) => g.places.length > 0);
  const known = new Set(floor.rooms.map((r) => r.id));
  const rest = floor.places.filter((p) => !known.has(p.room_id));
  if (rest.length) groups.push({ key: "none", room: "", places: rest });
  const dirLabel =
    sort.key === "name"
      ? sort.desc
        ? t("Z–A")
        : t("A–Z")
      : sort.desc
        ? t("Most popular first")
        : t("Least popular first");
  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">{t("Sort rooms")}</span>
        <SortToggle
          value={sort.key}
          onChange={(key) => setSort({ key, desc: key === "popularity" })}
          options={[
            { value: "name", label: t("Name") },
            { value: "popularity", label: t("Popularity") },
          ]}
          label={t("Sort rooms")}
        />
        <button
          type="button"
          onClick={() => setSort({ ...sort, desc: !sort.desc })}
          aria-label={t("Reverse order, now: {{order}}", { order: dirLabel })}
          className="inline-flex min-h-[44px] items-center gap-1 rounded-full px-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {(sort.key === "name" ? sort.desc : !sort.desc) ? (
            <ArrowUp aria-hidden className="h-4 w-4" />
          ) : (
            <ArrowDown aria-hidden className="h-4 w-4" />
          )}
          {dirLabel}
        </button>
      </div>
      {open && booking?.minHour !== null && (
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {t("Tap the start and end hour to book, or drag across free hours with the mouse.")}
        </p>
      )}
      {groups.map((g) => (
        <div key={g.key}>
          <div className="mb-1 grid grid-cols-[6.5rem_1fr] items-end gap-2 sm:grid-cols-[9rem_1fr]">
            <h3 className="truncate text-sm font-bold text-slate-800 dark:text-slate-100">{g.room}</h3>
          </div>
          {open && <TimelineAxis open={open} />}
          <ul className="space-y-1.5">
            {g.places.map((p) => (
              <PlaceTimeline
                key={p.id}
                entry={placeEntry(p)}
                open={open}
                booking={booking}
                compact
                onOpen={(id) => onOpen(id)}
                onBlockClick={(b) => onOpen(p.id, b.start_hour)}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Legend of the list timelines. */
function TimelineLegend() {
  const { t } = useTranslation();
  const swatch = "inline-block h-4 w-5 rounded border";
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700 dark:text-slate-200">
      <li className="inline-flex items-center gap-1.5">
        <span aria-hidden className={`${swatch} ${BLOCK_BOOKED}`} />
        {t("Booked")}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <span aria-hidden className={`${swatch} ${BLOCK_MINE}`} />
        {t("Your reservation")}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <span aria-hidden className={`${swatch} ${BLOCK_POSSIBLY_FREE}`} />
        {t("Possibly free")}
      </li>
      <li className="inline-flex items-center gap-1.5">
        <span aria-hidden className={`${swatch} border-slate-200 bg-slate-200/80 dark:border-slate-700 dark:bg-slate-700/70`} />
        {t("Closed")}
      </li>
    </ul>
  );
}
