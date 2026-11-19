// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Layers } from "lucide-react";
import { api } from "../../api";
import { Empty, ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { useDesks } from "../DesksLayout";
import type { BuildingOption } from "../components/BuildingSelect";
import { departmentFloors, type PlacesAdminData } from "../components/adminTypes";
import type { Floor } from "../types";
import { AssignDialog } from "./AssignDialog";
import { FloorContent } from "./FloorContent";
import { LocationBar, byFloorOrder } from "./LocationBar";
import { SelectionBar } from "./SelectionBar";
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
  const toast = useToast();
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

  // Department names for the badges: app admins may meet every department
  // (the manage pools API), department admins only their own.
  const { pools } = useDesks();
  const allPools = useFetch(() => (appAdmin ? api.listPools({ pageSize: 2000 }) : Promise.resolve(null)), [appAdmin]);
  const poolNames = useMemo(() => {
    const names = new Map(pools.map((p) => [p.id, p.name]));
    for (const p of allPools.data?.results ?? []) names.set(p.id, p.name);
    return names;
  }, [pools, allPools.data]);

  // Rooms and places selected for the department assignment (app admins).
  const [selectedRoomIds, setSelectedRoomIds] = useState<Set<number>>(() => new Set());
  const [selectedPlaceIds, setSelectedPlaceIds] = useState<Set<number>>(() => new Set());
  const [assigning, setAssigning] = useState(false);

  const [chosen, setChosen] = useState<Location>(readLocation);
  function choose(loc: Location) {
    setChosen(loc);
    writeLocation(loc);
    // A selection never reaches across floors.
    setSelectedRoomIds(new Set());
    setSelectedPlaceIds(new Set());
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

  // The selection as it stands on this floor: rows moved elsewhere (edited)
  // or removed since are never sent, and are dropped after each reload.
  const floorId = floor?.id ?? null;
  const floorRoomIds = useMemo(
    () => new Set(data && floorId !== null ? data.rooms.filter((r) => r.floor === floorId).map((r) => r.id) : []),
    [data, floorId],
  );
  const floorPlaceIds = useMemo(
    () => new Set(data ? data.places.filter((p) => floorRoomIds.has(p.room)).map((p) => p.id) : []),
    [data, floorRoomIds],
  );
  useEffect(() => {
    const prune = (allowed: Set<number>) => (ids: Set<number>) =>
      [...ids].every((id) => allowed.has(id)) ? ids : new Set([...ids].filter((id) => allowed.has(id)));
    setSelectedRoomIds(prune(floorRoomIds));
    setSelectedPlaceIds(prune(floorPlaceIds));
  }, [floorRoomIds, floorPlaceIds]);
  const roomIds = [...selectedRoomIds].filter((id) => floorRoomIds.has(id));
  const placeIds = [...selectedPlaceIds].filter((id) => floorPlaceIds.has(id));
  const clearSelection = () => {
    setSelectedRoomIds(new Set());
    setSelectedPlaceIds(new Set());
  };

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
          building={data.buildings.find((b) => b.id === buildingId)}
          floorBuildings={floorBuildingOptions}
          floors={buildingFloors}
          floorId={floor?.id ?? null}
          onBuilding={(id) => choose({ building: id, floor: null })}
          onFloor={(id) => choose({ building: buildingId ?? null, floor: id })}
          onChanged={reload}
          onFloorDeleted={() => {
            choose({ building: buildingId ?? null, floor: null });
            reload();
          }}
          onFloorSaved={(f) => {
            // A floor moved to another building stays the current one.
            choose({ building: f.building, floor: f.id });
            reload();
          }}
          onBuildingDeleted={() => {
            choose({});
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
        <FloorContent
          floor={floor}
          data={data}
          pool={pool}
          appAdmin={appAdmin}
          names={poolNames}
          selection={{
            roomIds: selectedRoomIds,
            placeIds: selectedPlaceIds,
            setRoomIds: setSelectedRoomIds,
            setPlaceIds: setSelectedPlaceIds,
          }}
          onChanged={reload}
        />
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
      {appAdmin && floor && roomIds.length + placeIds.length > 0 && (
        <SelectionBar
          rooms={roomIds.length}
          places={placeIds.length}
          onAssign={() => setAssigning(true)}
          onClear={clearSelection}
        />
      )}
      {appAdmin && (
        <AssignDialog
          open={assigning}
          roomIds={roomIds}
          placeIds={placeIds}
          onClose={() => setAssigning(false)}
          onAssigned={(count) => {
            setAssigning(false);
            toast.success(t("{{count}} places changed", { count }));
            clearSelection();
            reload();
          }}
        />
      )}
    </div>
  );
}
