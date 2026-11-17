// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { LampDesk, List, Map as MapIcon, Search } from "lucide-react";
import { Empty, ErrorBox, Loading } from "../../components/Status";
import { FavoriteToggle } from "../components/FavoriteToggle";
import { FeatureFilter, featureNames } from "../components/FeatureFilter";
import { FloorPlanView, type PlanPlace } from "../components/FloorPlanView";
import { LocationPicker } from "../components/LocationPicker";
import { PlaceSearch } from "../components/PlaceSearch";
import { StateLegend } from "../components/placeStates";
import { favoritesFirst, useFavorites } from "../favorites";
import { matchesPlace, useRememberedFloor } from "../location";
import type { DaysAvailability, Feature, FreePlace, OverviewFloor, PlaceKind } from "../types";

/** A place as the Book page lists it, over all chosen days. */
export interface PlaceRow {
  id: number;
  name: string;
  kind: PlaceKind;
  capacity: number | null;
  floor_id: number;
  room: string;
  floor: string;
  building: string;
  features: number[];
  /** Chosen days on which someone else holds it (can be requested later). */
  takenDays: string[];
  /** Chosen days on which it can't be booked at all. */
  unavailableDays: string[];
}

/** Multi-day availability joined with the overview's structure (capacity,
 *  floor and building names). */
export function availabilityRows(
  rows: DaysAvailability[],
  floors: OverviewFloor[] | null,
  kind: PlaceKind,
): PlaceRow[] {
  const floorById = new Map((floors ?? []).map((f) => [f.id, f]));
  return rows.map((r) => {
    const f = floorById.get(r.floor_id);
    return {
      id: r.id,
      name: r.name,
      kind,
      capacity: f?.places.find((p) => p.id === r.id)?.capacity ?? null,
      floor_id: r.floor_id,
      room: r.room,
      floor: f?.name ?? "",
      building: f?.building ?? "",
      features: r.features,
      takenDays: r.taken_days,
      unavailableDays: r.unavailable_days,
    };
  });
}

/** Free places of one day (series: its first occurrence). */
export function freeRows(rows: FreePlace[]): PlaceRow[] {
  return rows.map((p) => ({ ...p, takenDays: [], unavailableDays: [] }));
}

export const isFree = (p: PlaceRow) => p.takenDays.length === 0 && p.unavailableDays.length === 0;

/** Step "Choose a place": equipment and favourites filter, text search or
 *  floor picker, list or floor plan. Free places are selectable (several when
 *  `multi`); places taken on some days stay selectable with a note; places
 *  unavailable on a chosen day are listed but can't be chosen. Changing the
 *  floor or the search drops chosen places that are no longer shown. */
export function BookPlaces({
  pool,
  kind,
  rows,
  loading,
  error,
  floors,
  lastFloorId,
  featureList,
  features,
  onFeatures,
  totalDays,
  selected,
  onSelect,
  multi,
  focusPlace,
  onFocused,
}: {
  pool: number;
  kind: PlaceKind;
  rows: PlaceRow[] | null;
  loading: boolean;
  error: string | null;
  floors: OverviewFloor[] | null;
  lastFloorId: number | null;
  featureList: Feature[] | null;
  features: number[];
  onFeatures: (ids: number[]) => void;
  totalDays: number;
  selected: number[];
  onSelect: (ids: number[]) => void;
  multi: boolean;
  /** A place handed over in the link: its floor is shown once — the caller
   *  keeps that "once" (`onFocused`), so a remount (e.g. after the hours
   *  changed) does not override a floor picked meanwhile. */
  focusPlace: number | null;
  onFocused?: () => void;
}) {
  const { t } = useTranslation();
  const favorites = useFavorites();
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [mode, setMode] = useState<"list" | "plan">("list");
  // Text search looks through every building and floor (replaces the picker).
  const [query, setQuery] = useState("");
  const [floorId, setFloorId, showFloor] = useRememberedFloor(pool, floors, lastFloorId);

  useEffect(() => {
    if (!focusPlace || !floors) return;
    const home = floors.find((f) => f.places.some((p) => p.id === focusPlace));
    if (home) showFloor(home.id);
    onFocused?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floors, focusPlace, showFloor]);

  const term = query.trim().toLocaleLowerCase();
  const floorById = new Map((floors ?? []).map((f) => [f.id, f]));
  const names = (ids: number[]) => featureNames(featureList ?? [], ids);
  const all = rows ?? [];
  const byId = new Map(all.map((p) => [p.id, p]));
  const located = (p: PlaceRow, q: string, floor: number | null) =>
    q ? matchesPlace(p, q, floorById, names) : floor === null || p.floor_id === floor;
  const isShown = (id: number) => !onlyFavorites || favorites.ids.has(id);
  const listed = favoritesFirst(
    all.filter((p) => located(p, term, floorId) && isShown(p.id)),
    favorites.ids,
  );
  // Selectable first (favourites first within), then the unavailable ones.
  const ordered = [...listed.filter((p) => p.unavailableDays.length === 0), ...listed.filter((p) => p.unavailableDays.length > 0)];

  /** Keep only chosen places still shown after a floor or search change. */
  function prune(q: string, floor: number | null) {
    const kept = selected.filter((id) => {
      const p = byId.get(id);
      return !p || located(p, q, floor);
    });
    if (kept.length !== selected.length) onSelect(kept);
  }

  const currentFloor = floors?.find((f) => f.id === floorId) ?? null;
  const planFloor =
    currentFloor &&
    currentFloor.plan.shapes.length > 0 &&
    currentFloor.places.some((p) => p.kind === kind && p.plan_symbol)
      ? currentFloor
      : null;
  const showPlan = mode === "plan" && !!planFloor && !term;
  const stateKey = all.map((p) => `${p.id}:${isFree(p) ? 1 : 0}`).join(",");
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
            state: byId.has(p.id) && isFree(byId.get(p.id)!) ? "free" : "booked",
          }),
        ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [planFloor, kind, stateKey],
  );

  function toggle(id: number) {
    if (!multi) return onSelect(selected.includes(id) ? [] : [id]);
    onSelect(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }

  const chip = (on: boolean) =>
    `min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
      on
        ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
        : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
    }`;

  return (
    <div>
      {featureList && (
        <div className="mb-3">
          <FeatureFilter
            features={featureList}
            value={features}
            onChange={onFeatures}
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
      {rows && all.length === 0 && (
        <Empty icon={LampDesk} label={t("Nothing is available for this time.")} />
      )}
      {rows && all.length > 0 && floors && (
        <div className="mb-3 flex flex-col gap-3">
          <PlaceSearch
            value={query}
            onChange={(q) => {
              setQuery(q);
              prune(q.trim().toLocaleLowerCase(), floorId);
            }}
          />
          {term ? (
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("Searching all buildings and floors.")}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <LocationPicker
                floors={floors}
                floorId={floorId}
                onChange={(id) => {
                  setFloorId(id);
                  prune(term, id);
                }}
              />
              {planFloor && (
                <div role="group" aria-label={t("View")} className="flex gap-2">
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
            </div>
          )}
        </div>
      )}
      {rows && all.length > 0 && !showPlan && ordered.length === 0 && (
        <Empty
          icon={term ? Search : LampDesk}
          label={term ? t("No place matches.") : t("Nothing is available on this floor for this time.")}
        />
      )}
      {rows && showPlan && planFloor && (
        <div className="mb-4">
          <div className="mb-2">
            <StateLegend t={t} />
          </div>
          <FloorPlanView
            key={planFloor.id}
            shapes={planFloor.plan.shapes}
            places={planPlaces}
            scalePxPerM={planFloor.scale_px_per_m}
            selectedIds={selected}
            onPlaceClick={(id) => {
              const p = byId.get(id);
              if (p && isFree(p)) toggle(id);
            }}
            describe={(pp) => {
              const p = byId.get(pp.id);
              if (p && isFree(p)) return t("Free");
              if (p && p.unavailableDays.length === 0 && totalDays > 1)
                return t("taken on {{taken}} of {{count}} days", { taken: p.takenDays.length, count: totalDays });
              return t("Not available for this time.");
            }}
          />
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
            {totalDays > 1
              ? t("Tap places that are free on all chosen days to select them.")
              : t("Tap free places on the plan to select them.")}
          </p>
        </div>
      )}
      {rows && !showPlan && ordered.length > 0 && (
        <ul className="space-y-2">
          {ordered.map((p) => {
            const on = selected.includes(p.id);
            const blocked = p.unavailableDays.length > 0;
            const taken = p.takenDays.length;
            const status = blocked ? (
              <span className="shrink-0 text-xs font-semibold text-slate-600 dark:text-slate-300">
                {t("Not available")}
              </span>
            ) : taken > 0 ? (
              <span className="shrink-0 text-right text-xs font-semibold text-amber-800 dark:text-amber-300">
                {t("taken on {{taken}} of {{count}} days", { taken, count: totalDays })}
              </span>
            ) : (
              <span className="shrink-0 text-xs font-semibold text-emerald-700 dark:text-emerald-400">{t("Free")}</span>
            );
            const body = (
              <span className="min-w-0 flex-1">
                <span
                  className={`block truncate font-medium ${
                    blocked ? "text-slate-700 dark:text-slate-200" : "text-slate-900 dark:text-slate-100"
                  }`}
                >
                  {p.name}
                  {p.kind === "meeting_room" && p.capacity
                    ? ` · ${t("{{count}} seats", { count: p.capacity })}`
                    : ""}
                </span>
                <span className="block truncate text-sm text-slate-600 dark:text-slate-300">
                  {(term ? [p.building, p.floor, p.room] : [p.room]).filter(Boolean).join(" · ")}
                </span>
                {p.features.length > 0 && (
                  <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                    {names(p.features).join(", ")}
                  </span>
                )}
                {blocked && (
                  <span className="block text-xs text-slate-600 dark:text-slate-300">
                    {totalDays > 1
                      ? t("Cannot be booked on {{count}} of the chosen days (closed, reserved for someone else or your own booking).", {
                          count: p.unavailableDays.length,
                        })
                      : t("Cannot be booked at this time (closed, reserved for someone else or your own booking).")}
                  </span>
                )}
              </span>
            );
            return (
              <li key={p.id}>
                {blocked ? (
                  <div className="flex min-h-[56px] items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
                    {body}
                    {status}
                  </div>
                ) : (
                  <label
                    className={`flex min-h-[56px] cursor-pointer items-center gap-3 rounded-xl border p-3 ${
                      on
                        ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20"
                        : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                    }`}
                  >
                    <input
                      type={multi ? "checkbox" : "radio"}
                      name="book-place"
                      checked={on}
                      onChange={() => toggle(p.id)}
                      className="h-5 w-5 shrink-0 accent-brand-600"
                    />
                    {body}
                    {status}
                    <FavoriteToggle
                      name={p.name}
                      active={favorites.ids.has(p.id)}
                      onToggle={() => favorites.toggle(p.id)}
                    />
                  </label>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
