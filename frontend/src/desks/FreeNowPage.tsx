// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { LampDesk, Heart, Search } from "lucide-react";
import { useFetch } from "../useFetch";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { meetingRoomEntry, placeEntry, type TimelineEntry } from "./components/PlaceTimeline";
import { FreeNowCard, useNowHour } from "./components/FreeNowCard";
import { FavoriteToggle } from "./components/FavoriteToggle";
import { FeatureFilter, featureNames } from "./components/FeatureFilter";
import { favoritesFirst, useFavorites } from "./favorites";
import { LocationPicker } from "./components/LocationPicker";
import { matchesPlace, useRememberedFloor } from "./location";
import { PlaceSearch } from "./components/PlaceSearch";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import type { FreeNowPlace, PlaceKind } from "./types";

/** Start page of the area: what is free right now, filterable by kind and
 *  equipment, each place with today's occupancy (select hours to book) and
 *  quick bookings from now. */
export function FreeNowPage() {
  const { t } = useTranslation();
  const { pool } = useDesks();
  // A failed booking (taken meanwhile) reloads the list and the day; so
  // does a new full hour (what is free and bookable moves with it).
  const [reload, setReload] = useState(0);
  const refresh = () => setReload((n) => n + 1);
  const nowHour = useNowHour(refresh);
  const [kind, setKind] = useState<PlaceKind | "">("");
  const [features, setFeatures] = useState<number[]>([]);
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const favorites = useFavorites();
  const featureList = useFetch(() => desksApi.poolFeatures(pool), [pool]);
  const { data, loading, error } = useFetch(
    () => desksApi.freeNow(pool, kind || undefined, features),
    [pool, kind, features.join(","), reload],
  );

  // Today's occupancy of every place (the overview of the department).
  const day = useFetch(() => desksApi.overview(pool), [pool, reload]);
  const entries = useMemo(() => {
    const map = new Map<number, TimelineEntry>();
    for (const f of day.data?.floors ?? []) for (const p of f.places) map.set(p.id, placeEntry(p));
    for (const m of day.data?.meeting_rooms ?? []) map.set(m.id, meetingRoomEntry(m, ""));
    return map;
  }, [day.data]);

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
          {rows.map((place) => (
            <li key={place.id}>
              <FreeNowCard
                pool={pool}
                place={place}
                free={place}
                entry={entries.get(place.id)}
                day={day.data}
                nowHour={nowHour}
                onFailed={refresh}
                details={
                  <>
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
                  </>
                }
                action={
                  <FavoriteToggle
                    name={place.name}
                    active={favorites.ids.has(place.id)}
                    onToggle={() => favorites.toggle(place.id)}
                  />
                }
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
