// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useFetch } from "../../useFetch";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { FreeNowCard, useNowHour } from "./FreeNowCard";
import { meetingRoomEntry, placeEntry, type TimelineEntry } from "./PlaceTimeline";
import type { DepartmentDay, FreeNowPlace } from "../types";

/** Favourite desks and meeting rooms on the shop's favourites page (header
 *  heart), each like on "Jetzt frei": today's occupancy, quick bookings
 *  from now, "Book later" (Book page) and a cross to remove it. Rendered
 *  only for people who may book desks; reports its row count via `onCount`. */
export function FavoritePlacesSection({ onCount }: { onCount?: (n: number) => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [version, setVersion] = useState(0);
  const { data, loading, error } = useFetch(async () => {
    const r = await desksApi.favorites();
    onCount?.(r.places.length);
    return r.places;
  }, [version]);

  // Today of every department with a favourite: its day (timeline) and
  // which places are free now (quick bookings).
  const [reload, setReload] = useState(0);
  const refresh = () => setReload((n) => n + 1);
  const nowHour = useNowHour(refresh);
  const favPools = [...new Set((data ?? []).map((p) => p.pool))].sort((a, b) => a - b);
  const today = useFetch(
    () =>
      Promise.all(
        favPools.map(async (pool) => {
          const [day, free] = await Promise.all([desksApi.overview(pool), desksApi.freeNow(pool)]);
          return { pool, day, free };
        }),
      ),
    [favPools.join(","), reload],
  );
  const byPool = useMemo(() => {
    const map = new Map<
      number,
      { day: DepartmentDay; entries: Map<number, TimelineEntry>; free: Map<number, FreeNowPlace> }
    >();
    for (const r of today.data ?? []) {
      const entries = new Map<number, TimelineEntry>();
      for (const f of r.day.floors) for (const p of f.places) entries.set(p.id, placeEntry(p));
      for (const m of r.day.meeting_rooms) entries.set(m.id, meetingRoomEntry(m, ""));
      map.set(r.pool, { day: r.day, entries, free: new Map(r.free.map((f) => [f.id, f])) });
    }
    return map;
  }, [today.data]);

  async function remove(id: number) {
    try {
      await desksApi.setFavorite(id, false);
      setVersion((v) => v + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data || data.length === 0) return null;
  const pools = new Set(data.map((p) => p.pool));

  return (
    <section className="mb-6 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Desks and meeting rooms")}
      </h2>
      <ul className="space-y-2">
        {data.map((p) => {
          const where = [pools.size > 1 ? p.pool_name : "", p.building, p.floor, p.room].filter(Boolean);
          const d = byPool.get(p.pool);
          return (
            <li key={p.id}>
              <FreeNowCard
                pool={p.pool}
                place={p}
                free={d?.free.get(p.id) ?? null}
                entry={d?.entries.get(p.id)}
                day={d?.day}
                nowHour={nowHour}
                onFailed={refresh}
                later
                details={
                  <>
                    <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                      {p.name}
                    </span>
                    <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                      {where.join(" · ")}
                    </span>
                  </>
                }
                action={
                  <button
                    type="button"
                    onClick={() => remove(p.id)}
                    aria-label={t("Remove {{name}} from favorites", { name: p.name })}
                    title={t("Remove from favorites")}
                    className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800"
                  >
                    <X aria-hidden className="h-4 w-4" />
                  </button>
                }
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}
