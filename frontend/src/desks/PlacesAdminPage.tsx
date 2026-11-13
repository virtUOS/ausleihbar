// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useRef, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Map as MapIcon, PencilRuler } from "lucide-react";
import { useFetch } from "../useFetch";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import { FeaturesAdmin } from "./components/FeaturesAdmin";
import { FloorsRoomsAdmin } from "./components/FloorsRoomsAdmin";
import { PlacesAdminList } from "./components/PlacesAdminList";
import type { PlacesAdminData } from "./components/adminTypes";
import type { Floor, Place, Room } from "./types";

/** Department administration of places: floor plans, then the lists of floors
 *  and rooms, places and equipment features. */
export function PlacesAdminPage() {
  const { pool, isAdmin } = useDesks();
  if (!isAdmin) return <Navigate to="/desks" replace />;
  return <PlacesAdmin pool={pool} />;
}

function PlacesAdmin({ pool }: { pool: number }) {
  const { t } = useTranslation();
  const [version, setVersion] = useState(0);
  const fetched = useFetch<PlacesAdminData>(
    async () => {
      // Deactivated rows included: they stay editable and can be reactivated.
      const [floors, rooms, places, features] = await Promise.all([
        desksApi.floors(true),
        desksApi.rooms(true),
        desksApi.places(true),
        desksApi.features(),
      ]);
      return { floors, rooms, places, features };
    },
    [version],
  );
  // Keep the previous lists on screen while a change reloads them.
  const last = useRef<PlacesAdminData | null>(null);
  if (fetched.data) last.current = fetched.data;
  const data = fetched.data ?? last.current;
  const { error } = fetched;
  const section = { pool, onChanged: () => setVersion((n) => n + 1) };

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;

  const floors = data.floors
    .filter((f) => f.pool === pool && f.is_active)
    .sort((a, b) => a.building.localeCompare(b.building) || a.position - b.position);

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="plans-title">
        <h2 id="plans-title" className="mb-1 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">
          {t("Floor plans")}
        </h2>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Redraw each floor on top of its existing plan. Users see the redrawn plan in the overview.")}
        </p>
        {floors.length === 0 ? (
          <Empty icon={MapIcon} label={t("This department has no floors yet.")} />
        ) : (
          <ul className="flex flex-col gap-2">
            {floors.map((f) => (
              <FloorRow key={f.id} floor={f} rooms={data.rooms} places={data.places} />
            ))}
          </ul>
        )}
      </section>
      <FloorsRoomsAdmin {...section} data={data} />
      <PlacesAdminList {...section} data={data} />
      <FeaturesAdmin {...section} data={data} />
    </div>
  );
}

function FloorRow({ floor, rooms, places }: { floor: Floor; rooms: Room[]; places: Place[] }) {
  const { t } = useTranslation();
  const roomIds = new Set(rooms.filter((r) => r.floor === floor.id).map((r) => r.id));
  const floorPlaces = places.filter((p) => roomIds.has(p.room));
  const placed = floorPlaces.filter((p) => p.plan_symbol).length;
  const shapes = floor.plan?.shapes?.length ?? 0;
  const facts = [
    shapes ? t("Plan drawn") : t("No plan yet"),
    t("{{placed}} of {{total}} places on the plan", { placed, total: floorPlaces.length }),
    floor.has_template ? t("Template uploaded") : null,
    floor.scale_px_per_m ? t("Scale set") : null,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center dark:border-slate-700">
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-slate-900 dark:text-slate-100">
          {floor.building ? `${floor.building} · ` : ""}
          {floor.name}
        </p>
        <p className="text-xs text-slate-600 dark:text-slate-300">{facts.join(" · ")}</p>
      </div>
      <Link
        to={`/desks/manage/plans/${floor.id}`}
        className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
      >
        <PencilRuler aria-hidden className="h-4 w-4" />
        {t("Edit plan")}
      </Link>
    </li>
  );
}
