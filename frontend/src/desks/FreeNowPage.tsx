// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { LampDesk, DoorOpen, Heart } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatTime } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useBookNow } from "./bookNow";
import { FavoriteToggle } from "./components/FavoriteToggle";
import { FeatureFilter, featureNames } from "./components/FeatureFilter";
import { favoritesFirst, useFavorites } from "./favorites";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import type { PlaceKind } from "./types";

/** Start page of the area: what is free right now, filterable by kind and equipment. */
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

  const rows = favoritesFirst(
    (data ?? []).filter((p) => !onlyFavorites || favorites.ids.has(p.id)),
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
      <div role="group" aria-label={t("Show")} className="mb-4 flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={kind === f.value}
            onClick={() => setKind(f.value)}
            className={`min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
              kind === f.value
                ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
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
      {data && data.length > 0 && rows.length === 0 && (
        <Empty icon={Heart} label={t("None of your favorites is free right now.")} />
      )}
      {rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((place) => {
            const Icon = place.kind === "meeting_room" ? DoorOpen : LampDesk;
            return (
              <li
                key={place.id}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
              >
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
                    {[place.building, place.floor, place.room].filter(Boolean).join(" · ")}
                  </p>
                  {place.features.length > 0 && (
                    <p className="truncate text-xs text-slate-600 dark:text-slate-300">
                      {featureNames(featureList.data ?? [], place.features).join(", ")}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <p className="text-sm tabular-nums text-slate-600 dark:text-slate-300">
                    {place.free_until
                      ? t("free until {{time}}", { time: formatTime(place.free_until) })
                      : t("free all day")}
                  </p>
                  <button
                    type="button"
                    disabled={booking !== null}
                    onClick={() => bookNow(place)}
                    className="min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50"
                  >
                    {t("Book now")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
