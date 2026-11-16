// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { LampDesk, DoorOpen, Heart, Search } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatTime } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { freeEndHour, useBookNow, useShowBooked } from "./bookNow";
import { meetingRoomEntry, PlaceTimeline, placeEntry, type TimelineEntry } from "./components/PlaceTimeline";
import { berlinNow } from "./time";
import { pad2 } from "./weekdays";
import { FavoriteToggle } from "./components/FavoriteToggle";
import { FeatureFilter, featureNames } from "./components/FeatureFilter";
import { favoritesFirst, useFavorites } from "./favorites";
import { LocationPicker } from "./components/LocationPicker";
import { matchesPlace, useRememberedFloor } from "./location";
import { PlaceSearch } from "./components/PlaceSearch";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import type { FreeNowPlace, PlaceKind } from "./types";

/** Quick bookings from now: 4 and 8 hours, cut to the free stretch (then
 *  "until …" once). `hours` undefined = to the end of the stretch. */
function quickRanges(now: number, end: number | null): { hours?: number; end: number | null }[] {
  if (end === null) return [{ hours: 4, end: null }, { hours: 8, end: null }];
  if (end - now <= 4) return [{ end }];
  if (end - now < 8) return [{ hours: 4, end: now + 4 }, { end }];
  return [{ hours: 4, end: now + 4 }, { hours: 8, end: now + 8 }];
}

/** Start page of the area: what is free right now, filterable by kind and
 *  equipment, each place with today's occupancy (select hours to book) and
 *  quick bookings from now. */
export function FreeNowPage() {
  const { t } = useTranslation();
  const { pool } = useDesks();
  const { booking, bookNow } = useBookNow(pool);
  const [kind, setKind] = useState<PlaceKind | "">("");
  const [features, setFeatures] = useState<number[]>([]);
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const favorites = useFavorites();
  const featureList = useFetch(() => desksApi.poolFeatures(pool), [pool]);
  const { data, loading, error } = useFetch(
    () => desksApi.freeNow(pool, kind || undefined, features),
    [pool, kind, features.join(",")],
  );

  // Today's occupancy of every place (the overview of the department).
  const [reload, setReload] = useState(0);
  const day = useFetch(() => desksApi.overview(pool), [pool, reload]);
  const showBooked = useShowBooked();
  const entries = useMemo(() => {
    const map = new Map<number, TimelineEntry>();
    for (const f of day.data?.floors ?? []) for (const p of f.places) map.set(p.id, placeEntry(p));
    for (const m of day.data?.meeting_rooms ?? []) map.set(m.id, meetingRoomEntry(m, ""));
    return map;
  }, [day.data]);
  const nowHour = berlinNow().hour;

  const floors = useFetch(() => desksApi.poolFloors(pool), [pool]);
  const [floorId, setFloorId] = useRememberedFloor(pool, floors.data?.floors, floors.data?.last_floor_id);
  // Text search looks through every building and floor (replaces the picker).
  const [query, setQuery] = useState("");
  const term = query.trim().toLocaleLowerCase();
  const floorById = new Map((floors.data?.floors ?? []).map((f) => [f.id, f]));
  const names = (ids: number[]) => featureNames(featureList.data ?? [], ids);
  const matches = (p: FreeNowPlace) => matchesPlace(p, term, floorById, names);
  const located = (data ?? []).filter((p) =>
    term ? matches(p) : floorId === null || p.floor_id === floorId,
  );
  const rows = favoritesFirst(
    located.filter((p) => !onlyFavorites || favorites.ids.has(p.id)),
    favorites.ids,
  );

  const filters: { value: PlaceKind | ""; label: string }[] = [
    { value: "", label: t("All") },
    { value: "desk", label: t("Desks") },
    { value: "meeting_room", label: t("Meeting rooms") },
  ];

  return (
    <section aria-labelledby="free-now-title">
      <h2 id="free-now-title" className="sr-only">
        {t("Free now")}
      </h2>
      <div className="mb-3">
        <PlaceSearch value={query} onChange={setQuery} />
      </div>
      {term ? (
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{t("Searching all buildings and floors.")}</p>
      ) : (
        floors.data && (
          <LocationPicker floors={floors.data.floors} floorId={floorId} onChange={setFloorId} className="mb-3" />
        )
      )}
      <SegmentedControl
        size="md"
        ariaLabel={t("Show")}
        value={kind || "all"}
        onChange={(v) => setKind(v === "all" ? "" : v)}
        options={filters.map((f) => ({ value: (f.value || "all") as PlaceKind | "all", label: f.label }))}
        className="mb-4 w-full sm:w-max"
      />
      {featureList.data && (
        <div className="mb-4">
          <FeatureFilter
            features={featureList.data}
            value={features}
            onChange={setFeatures}
            favorites={
              favorites.ids.size > 0 || onlyFavorites
                ? { active: onlyFavorites, onToggle: () => setOnlyFavorites((v) => !v) }
                : undefined
            }
          />
        </div>
      )}
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && data.length === 0 && <Empty icon={LampDesk} label={t("Nothing is free right now.")} />}
      {data && data.length > 0 && located.length === 0 && (
        <Empty
          icon={term ? Search : LampDesk}
          label={term ? t("No free place matches.") : t("Nothing is free on this floor right now.")}
        />
      )}
      {located.length > 0 && rows.length === 0 && (
        <Empty icon={Heart} label={t("None of your favorites is free right now.")} />
      )}
      {rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((place) => {
            const Icon = place.kind === "meeting_room" ? DoorOpen : LampDesk;
            const entry = entries.get(place.id);
            const end = freeEndHour(place, day.data?.open_hours?.[1] ?? null);
            return (
              <li
                key={place.id}
                className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
              >
                <div className="flex items-center gap-3">
                <FavoriteToggle
                  name={place.name}
                  active={favorites.ids.has(place.id)}
                  onToggle={() => favorites.toggle(place.id)}
                />
                <Icon aria-hidden className="h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-900 dark:text-slate-100">
                    {place.name}
                    {place.kind === "meeting_room" && place.capacity
                      ? ` · ${t("{{count}} seats", { count: place.capacity })}`
                      : ""}
                  </p>
                  <p className="truncate text-sm text-slate-600 dark:text-slate-300">
                    {(term ? [place.building, place.floor, place.room] : [place.room]).filter(Boolean).join(" · ")}
                  </p>
                  {place.features.length > 0 && (
                    <p className="truncate text-xs text-slate-600 dark:text-slate-300">
                      {featureNames(featureList.data ?? [], place.features).join(", ")}
                    </p>
                  )}
                </div>
                <p className="shrink-0 self-start text-sm tabular-nums text-slate-600 dark:text-slate-300">
                  {place.free_until
                    ? t("free until {{time}}", { time: formatTime(place.free_until) })
                    : t("free all day")}
                </p>
                </div>
                {entry && day.data?.open_hours && (
                  <div className="mt-2">
                    <PlaceTimeline
                      entry={entry}
                      open={day.data.open_hours}
                      bare
                      slim
                      booking={{
                        day: day.data.day,
                        closed: day.data.closed_hours,
                        minHour: nowHour,
                        onBooked: (res) => (res ? showBooked(res) : setReload((n) => n + 1)),
                      }}
                    />
                  </div>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="basis-full text-sm text-slate-600 sm:basis-auto dark:text-slate-300">{t("Book from now:")}</span>
                  {quickRanges(nowHour, end).map((q) => {
                    const label = q.hours ? (q.hours === 4 ? t("4 hours") : t("8 hours")) : t("until {{time}}", { time: `${pad2(q.end!)}:00` });
                    return (
                      <button
                        key={q.hours ?? "rest"}
                        type="button"
                        disabled={booking !== null}
                        onClick={() => bookNow(place, q.hours)}
                        aria-label={
                          q.end !== null
                            ? t("Book {{name}} {{from}}–{{to}}", {
                                name: place.name,
                                from: `${pad2(nowHour)}:00`,
                                to: `${pad2(q.end)}:00`,
                              })
                            : `${place.name}: ${label}`
                        }
                        className="min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50"
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
