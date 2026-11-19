// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DoorOpen, Layers, PencilRuler } from "lucide-react";
import { Empty, ErrorBox, Loading } from "../../components/Status";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import type { BuildingOption } from "../components/BuildingSelect";
import { departmentFloors, type PlacesAdminData } from "../components/adminTypes";
import { secondaryBtn } from "../components/formStyles";
import type { Floor } from "../types";
import { LocationBar, byFloorOrder } from "./LocationBar";
import { SettingsMenu } from "./SettingsMenu";

const STORAGE_KEY = "desks.admin.location";

/** The building/floor last chosen here. `building` absent: none chosen yet
 *  (null is a real choice: "without building"). */
interface Location {
  building?: number | null;
  floor?: number | null;
}

function readLocation(): Location {
  try {
    const raw: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    if (!raw || typeof raw !== "object") return {};
    const { building, floor } = raw as Record<string, unknown>;
    const id = (v: unknown) => (typeof v === "number" && Number.isInteger(v) ? v : null);
    return {
      ...(building !== undefined ? { building: id(building) } : {}),
      floor: id(floor),
    };
  } catch {
    return {};
  }
}

function writeLocation(loc: Location) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
  } catch {
    // Private mode / blocked storage: the choice just isn't kept.
  }
}

/**
 * The places workspace: choose building and floor, then work on that floor.
 * App admins see every floor; department admins the floors holding rooms or
 * places of the current department.
 */
export function PlacesWorkspace({ pool, appAdmin }: { pool: number; appAdmin: boolean }) {
  const { t } = useTranslation();
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((n) => n + 1);
  const fetched = useFetch<PlacesAdminData>(
    async () => {
      // Deactivated rows included: they stay editable and can be reactivated.
      const [floors, rooms, places, features, buildings] = await Promise.all([
        desksApi.floors(true),
        desksApi.rooms(true),
        desksApi.places(true),
        desksApi.features(),
        desksApi.buildings(),
      ]);
      return { floors, rooms, places, features, buildings };
    },
    [version],
  );
  // Keep the previous data on screen while a change reloads it.
  const last = useRef<PlacesAdminData | null>(null);
  if (fetched.data) last.current = fetched.data;
  const data = fetched.data ?? last.current;

  const [chosen, setChosen] = useState<Location>(readLocation);
  function choose(loc: Location) {
    setChosen(loc);
    writeLocation(loc);
  }

  // Department admins only work on active floors of their department.
  const floors = useMemo(
    () => (data ? departmentFloors(data, pool, appAdmin).filter((f) => appAdmin || f.is_active) : []),
    [data, pool, appAdmin],
  );

  const buildingOptions = useMemo<BuildingOption[]>(() => {
    if (!data) return [];
    const byId = new Map(data.buildings.map((b) => [b.id, b]));
    const option = (id: number | null): BuildingOption => {
      const b = id == null ? undefined : byId.get(id);
      return { id, code: b?.code ?? "", description: b?.description ?? "", address: b?.address };
    };
    // App admins choose among all buildings (a new one is still empty);
    // department admins among those of their floors.
    const ids = new Set<number | null>(appAdmin ? data.buildings.map((b) => b.id) : []);
    for (const f of floors) ids.add(f.building);
    return [...ids].map(option);
  }, [data, floors, appAdmin]);

  // The effective location: the stored choice where it still exists, else the
  // first building and floor (never written back — a just-created floor may
  // not be loaded yet).
  const floorOf = (id: number | null | undefined) => floors.find((f) => f.id === id);
  const hasBuilding = (id: number | null | undefined) =>
    id !== undefined && buildingOptions.some((o) => o.id === id);
  const firstWithFloors = buildingOptions.find((o) => floors.some((f) => f.building === o.id));
  // Fall back on the option/floor itself: its building id may be null ("without building").
  const storedFloor = floorOf(chosen.floor);
  const buildingId: number | null | undefined = hasBuilding(chosen.building)
    ? chosen.building
    : storedFloor
      ? storedFloor.building
      : (firstWithFloors ?? buildingOptions[0])?.id;
  const buildingFloors = floors.filter((f) => f.building === buildingId).sort(byFloorOrder);
  const floor: Floor | null =
    buildingFloors.find((f) => f.id === chosen.floor) ??
    buildingFloors.find((f) => f.is_active) ??
    buildingFloors[0] ??
    null;

  if (fetched.error) return <ErrorBox message={fetched.error} />;
  if (!data) return <Loading />;

  // New-floor building choices: every building plus "without building".
  const floorBuildingOptions: BuildingOption[] = [
    { id: null, code: "", description: "" },
    ...data.buildings.map((b) => ({ id: b.id, code: b.code, description: b.description, address: b.address })),
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <LocationBar
          appAdmin={appAdmin}
          buildings={buildingOptions}
          buildingId={buildingId}
          floors={buildingFloors}
          floorId={floor?.id ?? null}
          onBuilding={(id) => choose({ building: id, floor: null })}
          onFloor={(id) => choose({ building: buildingId ?? null, floor: id })}
          onChanged={reload}
          onFloorDeleted={() => {
            choose({ building: buildingId ?? null, floor: null });
            reload();
          }}
        />
        <SettingsMenu
          appAdmin={appAdmin}
          buildings={floorBuildingOptions}
          buildingId={buildingId}
          floors={data.floors}
          onBuildingCreated={(b) => {
            // Department admins only see buildings holding their floors.
            if (appAdmin) choose({ building: b.id, floor: null });
            reload();
          }}
          onFloorCreated={(f) => {
            choose({ building: f.building, floor: f.id });
            reload();
          }}
          onFeatureCreated={reload}
        />
      </div>
      {floor ? (
        <FloorRooms floor={floor} data={data} pool={pool} appAdmin={appAdmin} />
      ) : (
        <Empty
          icon={Layers}
          label={
            !appAdmin && floors.length === 0
              ? t("This department has no floors yet.")
              : buildingId === undefined
                ? t("No buildings yet.")
                : t("This building has no floors yet.")
          }
        />
      )}
    </div>
  );
}

/** The rooms of the chosen floor and a link to its plan. */
function FloorRooms({
  floor,
  data,
  pool,
  appAdmin,
}: {
  floor: Floor;
  data: PlacesAdminData;
  pool: number;
  appAdmin: boolean;
}) {
  const { t } = useTranslation();
  // Department admins: rooms of their department or holding its places.
  const ownRooms = new Set(data.places.filter((p) => p.pool === pool).map((p) => p.room));
  const rooms = data.rooms
    .filter((r) => r.floor === floor.id && (appAdmin || r.pool === pool || ownRooms.has(r.id)))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  return (
    <section aria-labelledby="floor-rooms-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="floor-rooms-title" className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("Rooms")}
        </h2>
        <Link to={`/desks/manage/plans/${floor.id}`} className={secondaryBtn}>
          <PencilRuler aria-hidden className="h-4 w-4" />
          {t("Edit plan")}
        </Link>
      </div>
      {rooms.length === 0 ? (
        <Empty icon={DoorOpen} label={t("This floor has no rooms yet.")} />
      ) : (
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
          {rooms.map((r) => (
            <li key={r.id} className="px-3 py-2 text-sm text-slate-900 dark:text-slate-100">
              {r.name}
              {!r.is_active && (
                <span className="ml-2 text-xs text-slate-600 dark:text-slate-300">({t("deactivated")})</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
