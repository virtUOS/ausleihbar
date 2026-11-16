// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { BuildingSelect, type BuildingOption } from "./BuildingSelect";
import type { FloorLike } from "../location";

const byPosition = (a: FloorLike, b: FloorLike) =>
  (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name, undefined, { numeric: true });

/**
 * Building and floor in one compact row: the building as a searchable
 * dropdown (a plain label when there is only one), its floors as pills —
 * always shown, even a single one, so people see where they are.
 */
export function LocationPicker({
  floors,
  floorId,
  onChange,
  className = "",
}: {
  floors: FloorLike[];
  floorId: number | null;
  onChange: (floorId: number) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const current = floors.find((f) => f.id === floorId) ?? null;
  const buildings = useMemo(() => {
    const seen = new Map<number | null, BuildingOption>();
    for (const f of floors) {
      if (!seen.has(f.building_id)) {
        seen.set(f.building_id, { id: f.building_id, code: f.building, description: f.building_description });
      }
    }
    return [...seen.values()];
  }, [floors]);
  const buildingFloors = floors
    .filter((f) => f.building_id === (current?.building_id ?? null))
    .sort(byPosition);

  if (!current) return null;
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {(buildings.length > 1 || current.building_id != null) && (
        <BuildingSelect
          label={t("Building")}
          options={buildings}
          value={current?.building_id ?? null}
          onChange={(id) => {
            const first = floors.filter((f) => f.building_id === id).sort(byPosition)[0];
            if (first) onChange(first.id);
          }}
        />
      )}
      {buildingFloors.length > 0 && (
        <div role="group" aria-label={t("Floor")} className="-mx-1 flex min-w-0 gap-1.5 overflow-x-auto px-1 py-0.5">
          {buildingFloors.map((f) => {
            const on = f.id === floorId;
            return (
              <button
                key={f.id}
                type="button"
                aria-pressed={on}
                onClick={() => onChange(f.id)}
                className={`min-h-[44px] shrink-0 rounded-full border px-3.5 text-sm font-medium transition-colors duration-150 ${
                  on
                    ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                    : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                {f.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
