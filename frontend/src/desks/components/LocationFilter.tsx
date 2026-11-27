// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Building2, Layers } from "lucide-react";
import { compareBuildingCodes } from "./BuildingSelect";
import type { FloorLike } from "../location";
import type { LocationScope } from "../overviewFilter";

const byPosition = (a: FloorLike, b: FloorLike) =>
  (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name, undefined, { numeric: true });

const selectCls =
  "min-h-[44px] w-full min-w-0 max-w-full rounded-full sm:w-auto border border-slate-300 bg-white py-0 pl-9 pr-8 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-slate-500";
// Phones: building and floor share one row (each half), wider: natural width.
const selectWrap = "relative inline-flex min-w-0 flex-1 sm:flex-none";
const labelCls =
  "inline-flex min-h-[44px] max-w-full items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

const buildingKey = (id: number | null | "all") => (id === "all" ? "all" : id === null ? "none" : String(id));

/** Building and floor of the overview as two compact selects, each with an
 *  "all" choice. The floor select is disabled (showing "Alle") while the
 *  building is "all". With exactly one floor there is nothing to choose and
 *  neither "all" nor a dropdown is shown. */
export function LocationFilter({
  floors,
  scope,
  onChange,
}: {
  floors: FloorLike[];
  scope: LocationScope;
  onChange: (scope: LocationScope) => void;
}) {
  const { t } = useTranslation();
  const buildings = useMemo(() => {
    const seen = new Map<number | null, { id: number | null; code: string }>();
    for (const f of floors) if (!seen.has(f.building_id)) seen.set(f.building_id, { id: f.building_id, code: f.building });
    return [...seen.values()].sort((a, b) => compareBuildingCodes(a.code, b.code));
  }, [floors]);

  // With a single building there is no building choice: "all" means that one.
  const buildingId = scope.buildingId === "all" && buildings.length === 1 ? buildings[0].id : scope.buildingId;
  const buildingFloors = useMemo(
    () => (buildingId === "all" ? [] : floors.filter((f) => f.building_id === buildingId).sort(byPosition)),
    [floors, buildingId],
  );

  const noneLabel = t("Without building");

  if (floors.length === 0) return null;

  if (floors.length === 1) {
    const only = floors[0];
    return (
      <div className="flex flex-wrap items-center gap-2">
        {only.building_id != null && (
          <span className={labelCls}>
            <Building2 aria-hidden className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
            <span className="sr-only">{t("Building")}: </span>
            {only.building}
          </span>
        )}
        <span className={labelCls}>
          <Layers aria-hidden className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
          <span className="sr-only">{t("Floor")}: </span>
          {only.name}
        </span>
      </div>
    );
  }

  function pickBuilding(value: string) {
    if (value === "all") return onChange({ buildingId: "all", floorId: "all" });
    const id = value === "none" ? null : Number(value);
    const inBuilding = floors.filter((f) => f.building_id === id);
    // A building with a single floor selects it directly, else all its floors.
    onChange({ buildingId: id, floorId: inBuilding.length === 1 ? inBuilding[0].id : "all" });
  }

  return (
    <div className="flex basis-full items-center gap-2 sm:basis-auto">
      {buildings.length > 1 ? (
        <span className={selectWrap}>
          <Building2
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400"
          />
          <select
            aria-label={t("Building")}
            value={buildingKey(scope.buildingId)}
            onChange={(e) => pickBuilding(e.target.value)}
            className={selectCls}
          >
            <option value="all">{t("All buildings")}</option>
            {buildings.map((b) => (
              <option key={buildingKey(b.id)} value={buildingKey(b.id)}>
                {b.code || noneLabel}
              </option>
            ))}
          </select>
        </span>
      ) : (
        buildings[0]?.id != null && (
          <span className={labelCls}>
            <Building2 aria-hidden className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
            <span className="sr-only">{t("Building")}: </span>
            {buildings[0].code}
          </span>
        )
      )}
      <span className={selectWrap}>
        <Layers
          aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400"
        />
        <select
          aria-label={t("Floor")}
          disabled={buildingId === "all"}
          value={buildingId === "all" ? "all" : String(scope.floorId)}
          onChange={(e) => onChange({ buildingId, floorId: e.target.value === "all" ? "all" : Number(e.target.value) })}
          className={selectCls}
        >
          <option value="all">{t("All floors")}</option>
          {buildingFloors.map((f) => (
            <option key={f.id} value={String(f.id)}>
              {f.name}
            </option>
          ))}
        </select>
      </span>
    </div>
  );
}
