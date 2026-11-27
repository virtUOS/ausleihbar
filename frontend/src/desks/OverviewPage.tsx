// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { SegmentedControl } from "@basicbar/ui";
import { ArrowDown, ArrowUp, ChevronRight, DoorOpen, SearchX } from "lucide-react";
import { useFetch } from "../useFetch";
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
import { PlaceSheet } from "./components/PlaceSheet";
import {
  AdminReservationActions,
  isManageable,
  useHolderText,
} from "./components/AdminReservationActions";
import { DateNav } from "./components/DateNav";
import { LocationFilter } from "./components/LocationFilter";
import { PlaceFilterMenu } from "./components/PlaceFilterMenu";
import { PlanLegend } from "./components/PlanLegend";
import { PlaceSearch } from "./components/PlaceSearch";
import { compareBuildingCodes } from "./components/BuildingSelect";
import { featureNames } from "./components/FeatureFilter";
import { dayLoad } from "./dayLoad";
import {
  EMPTY_FILTER,
  dayState,
  floorsInScope,
  matchesFilter,
  stateAt,
  type PlaceFilter,
} from "./overviewFilter";
import { favoritesFirst, useFavorites } from "./favorites";
import { useClosedDays } from "./useClosedDays";
import { matchesPlace, useRememberedScope, type SearchablePlace } from "./location";
import { SortToggle } from "../components/SortToggle";
import { berlinNow } from "./time";
import { addDays, pad2 } from "./weekdays";
import type { DepartmentDay, ManageReservation, OverviewFloor, OverviewPlace } from "./types";

const pad = (h: number) => `${pad2(h)}:00`;

type ViewMode = "plan" | "list";
const VIEW_KEY = "desks.overviewView";

function storedView(): ViewMode {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "list" ? "list" : "plan";
  } catch {
    return "plan";
  }
}

const byLocation = (a: OverviewFloor, b: OverviewFloor) =>
  compareBuildingCodes(a.building, b.building) ||
  a.position - b.position ||
  a.name.localeCompare(b.name, undefined, { numeric: true });

/** A place of the overview as the text search sees it. */
function searchable(p: OverviewPlace, floor: OverviewFloor): SearchablePlace {
  return {
    name: p.name,
    room: floor.rooms.find((r) => r.id === p.room_id)?.name ?? "",
    floor: floor.name,
    floor_id: floor.id,
    building: floor.building,
    features: p.features,
  };
}

/** Department overview: a day, a building/floor scope, search and filters;
 *  the plan of one floor or the list of the floors in scope, plus meeting
 *  room timelines and (department admins) the day's reservations. */
export function OverviewPage() {
  const { t } = useTranslation();
  const { pool, pools, select, isAdmin } = useDesks();
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
  const [mode, setModeState] = useState<ViewMode>(storedView);
  const setMode = (next: ViewMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // not persisted (private mode)
    }
  };
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
  const [query, setQuery] = useState("");
  const term = query.trim().toLocaleLowerCase();
  // The room lives in the URL (`?room=`), the other criteria here.
  const [criteria, setCriteria] = useState<PlaceFilter>(EMPTY_FILTER);

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

  // Building / floor scope: the one last used in this department ("all"
  // included), else the floor of the latest own booking, else the first.
  const [scope, chooseScope, showScope] = useRememberedScope(pool, data?.floors, data?.last_floor_id);

  // `?room=<id>` (QR code on a room's door sign): that room's floor, only its
  // places. The room may belong to another of the user's departments: look
  // through them and switch to the one whose floors hold the room.
  const [params, setParams] = useSearchParams();
  const roomParam = Number(params.get("room")) || null;
  const clearRoom = () =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("room");
        return next;
      },
      { replace: true },
    );
  const roomFloorIn = (d: DepartmentDay | null | undefined, room: number) =>
    d?.floors.find((f) => f.rooms.some((r) => r.id === room)) ?? null;
  const inCurrent = !!data && data.pool === pool && roomParam !== null && !!roomFloorIn(data, roomParam);
  const roomPools = useFetch(
    async () => {
      if (roomParam === null || inCurrent || !data) return null;
      const lists = await Promise.all(
        pools.filter((p) => p.id !== pool).map(async (p) => ({ pool: p.id, day: await desksApi.overview(p.id) })),
      );
      return lists.filter((l) => roomFloorIn(l.day, roomParam)).map((l) => l.pool);
    },
    // Asked once per link (and once the current pool's day is known).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [roomParam, inCurrent, !!data],
  );
  useEffect(() => {
    const other = roomPools.data?.[0];
    if (other !== undefined && other !== pool) select(other);
  }, [roomPools.data, pool, select]);
  // No department of the user holds the room: the normal page and a note.
  const roomMissing = roomParam !== null && !inCurrent && roomPools.data?.length === 0;
  const roomFloor = inCurrent ? roomFloorIn(data, roomParam!) : null;
  const roomId = roomFloor ? roomParam : null;
  const roomName = roomFloor?.rooms.find((r) => r.id === roomId)?.name;
  // Show the room's floor once per link; the user may move on from there.
  const shownRoom = useRef<string | null>(null);
  useEffect(() => {
    if (!roomFloor || roomId === null) return;
    const key = `${pool}:${roomId}`;
    if (shownRoom.current === key) return;
    shownRoom.current = key;
    showScope({ buildingId: roomFloor.building_id, floorId: roomFloor.id });
  }, [roomFloor, roomId, pool, showScope]);

  const filter: PlaceFilter = { ...criteria, roomId };
  const changeFilter = (next: PlaceFilter) => {
    setCriteria({ ...next, roomId: null });
    if (next.roomId === null && roomParam !== null) clearRoom();
  };

  const isToday = !!data && data.day === today.date;
  // "Nur freie" today: free at the hour the plan shows (now, inside the opening hours).
  const nowHour = isToday ? hour : null;
  const matches = (p: OverviewPlace) =>
    matchesFilter(p, filter, { nowHour, favorites: favorites.ids });

  const scopeFloors = data && scope ? floorsInScope(data.floors, scope).sort(byLocation) : [];
  // A search looks through every building and floor of the department.
  const floorById = useMemo(() => new Map((data?.floors ?? []).map((f) => [f.id, f])), [data]);
  const names = (ids: number[]) => featureNames(features.data ?? [], ids);
  const listFloors = (term ? [...(data?.floors ?? [])].sort(byLocation) : scopeFloors).map((f) => ({
    floor: f,
    places: f.places.filter((p) => matches(p) && (!term || matchesPlace(searchable(p, f), term, floorById, names))),
  }));
  const planFloor =
    !term && scopeFloors.length === 1 && scopeFloors[0].plan.shapes.length > 0 ? scopeFloors[0] : null;
  const showPlan = !!planFloor && mode === "plan";
  const dimmedIds = new Set((planFloor?.places ?? []).filter((p) => !matches(p)).map((p) => p.id));
  const floorRooms = (data?.meeting_rooms ?? []).filter((m) => m.floor_id === planFloor?.id);

  const minDay = isAdmin ? null : today.date;
  // Closed days for the arrows and the month calendar: a stable span around today.
  const closedDays = useClosedDays(addDays(today.date, -62), addDays(today.date, 400), pool);

  const found = useMemo(() => {
    if (!data || openId === null) return null;
    for (const f of data.floors) {
      const p = f.places.find((x) => x.id === openId);
      if (p) return { place: p, floor: f };
    }
    return null;
  }, [data, openId]);

  // Places can be booked right in their timeline.
  const shownDay = data?.day ?? day;
  const minHour = shownDay < today.date ? null : shownDay === today.date ? today.hour : 0;
  const timelineBooking: TimelineBooking | undefined = data
    ? { day: data.day, closed: data.closed_hours, minHour, onBooked: () => setReload((n) => n + 1) }
    : undefined;
  const placesInView = (term ? (data?.floors ?? []) : scopeFloors).reduce((n, f) => n + f.places.length, 0);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <DateNav day={day} today={today.date} minDay={minDay} closedDays={closedDays} onChange={setDay} />
        <span className="flex-1" />
        <SegmentedControl
          size="md"
          ariaLabel={t("View")}
          value={planFloor ? mode : "list"}
          onChange={setMode}
          disabled={!planFloor}
          options={[
            { value: "plan", label: t("Plan") },
            { value: "list", label: t("List") },
          ]}
        />
      </div>

      {data && data.floors.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {scope && <LocationFilter floors={data.floors} scope={scope} onChange={chooseScope} />}
          <div className="min-w-[12rem] flex-1">
            <PlaceSearch value={query} onChange={setQuery} />
          </div>
          <PlaceFilterMenu
            value={filter}
            onChange={changeFilter}
            features={features.data ?? []}
            hasFavorites={favorites.ids.size > 0}
            roomName={roomName}
            onClearRoom={clearRoom}
            isToday={isToday}
          />
        </div>
      )}

      {roomMissing && (
        <p role="status" className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          {t("This room has no free place for you right now.")}
        </p>
      )}

      {loading && !data && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <>
          {/* No opening hours, or a whole-day block (public holiday). */}
          {(!data.open_hours || closedDays.has(data.day)) && (
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{t("Closed on this day.")}</p>
          )}
          {term && (
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
              {t("Searching all buildings and floors.")}
            </p>
          )}

          {data.floors.length > 0 && (
            <section aria-label={t("Places")} className="mb-8">
              {placesInView === 0 ? (
                <Empty icon={DoorOpen} label={t("No places on this floor.")} />
              ) : showPlan && planFloor ? (
                <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                  <PlanPane
                    key={planFloor.id}
                    floor={planFloor}
                    hour={isToday ? hour : null}
                    dimmedIds={dimmedIds}
                    onOpen={(id) => openPlace(id, isToday ? today.hour : null)}
                  />
                  <div className="border-t border-slate-200 px-3 py-1 dark:border-slate-700">
                    <PlanLegend />
                  </div>
                </div>
              ) : listFloors.every((g) => g.places.length === 0) ? (
                <Empty icon={SearchX} label={t("No place matches the filters.")} />
              ) : (
                <PlaceList
                  floors={listFloors}
                  pool={pool}
                  open={data.open_hours}
                  booking={timelineBooking}
                  favorites={favorites.ids}
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
  dimmedIds,
  onOpen,
}: {
  floor: OverviewFloor;
  hour: number | null;
  /** Places that don't match the filters (drawn faded). */
  dimmedIds: Set<number>;
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
        dimmedIds={dimmedIds}
        className="!rounded-b-none !border-0"
      />
      {unplaced > 0 && (
        <p className="px-3 pt-2 text-xs text-slate-600 dark:text-slate-300">
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
  floors,
  pool,
  open,
  booking,
  favorites,
  onOpen,
}: {
  /** The floors to show with their (already filtered) places. */
  floors: { floor: OverviewFloor; places: OverviewPlace[] }[];
  pool: number;
  open: [number, number] | null;
  booking?: TimelineBooking;
  /** Favourite places come first within their room. */
  favorites: Set<number>;
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
  const byRoom = (a: { id: number; name: string }, b: { id: number; name: string }) => {
    const by =
      sort.key === "popularity"
        ? (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity) ||
          a.name.localeCompare(b.name, undefined, { numeric: true })
        : a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
    // Popularity: "descending" = most popular first (the natural reading).
    return sort.key === "popularity" ? (sort.desc ? by : -by) : sort.desc ? -by : by;
  };
  // Per floor its rooms with places left after filtering; emptied rooms and floors are hidden.
  const sections = floors
    .map(({ floor, places }) => {
      const groups = [...floor.rooms]
        .sort(byRoom)
        .map((r) => ({ key: String(r.id), room: r.name, places: places.filter((p) => p.room_id === r.id) }))
        .filter((g) => g.places.length > 0);
      const known = new Set(floor.rooms.map((r) => r.id));
      const rest = places.filter((p) => !known.has(p.room_id));
      if (rest.length) groups.push({ key: "none", room: "", places: rest });
      return { floor, groups: groups.map((g) => ({ ...g, places: favoritesFirst(g.places, favorites) })) };
    })
    .filter((s) => s.groups.length > 0);
  const withHeadings = sections.length > 1;
  const dirLabel =
    sort.key === "name"
      ? sort.desc
        ? t("Z–A")
        : t("A–Z")
      : sort.desc
        ? t("Most popular first")
        : t("Least popular first");
  // Room headings sit one level below the floor headings, when there are any.
  const RoomHeading = withHeadings ? "h4" : "h3";
  const roomGroup = (g: { key: string; room: string; places: OverviewPlace[] }) => (
    <div key={g.key}>
      <div className="mb-1 grid grid-cols-[6.5rem_1fr] items-end gap-2 sm:grid-cols-[9rem_1fr]">
        <RoomHeading className="truncate text-sm font-bold text-slate-800 dark:text-slate-100">{g.room}</RoomHeading>
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
  );
  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <TimelineLegend />
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
      {sections.map(({ floor, groups }) =>
        withHeadings ? (
          <section key={floor.id} aria-labelledby={`floor-${floor.id}`} className="space-y-4">
            <h3
              id={`floor-${floor.id}`}
              className="border-b border-slate-200 pb-1 text-base font-bold text-slate-900 dark:border-slate-700 dark:text-slate-100"
            >
              {[floor.building, floor.name].filter(Boolean).join(" · ")}
            </h3>
            {groups.map(roomGroup)}
          </section>
        ) : (
          groups.map(roomGroup)
        ),
      )}
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
        {t("Closed or already past")}
      </li>
    </ul>
  );
}
