// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Armchair, DoorOpen } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatTime } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { desksApi } from "./api";
import { useDesks } from "./DesksLayout";
import type { PlaceKind } from "./types";

/** Start page of the area: what is free right now (F2 adds booking from here). */
export function FreeNowPage() {
  const { t } = useTranslation();
  const { pool } = useDesks();
  const [kind, setKind] = useState<PlaceKind | "">("");
  const { data, loading, error } = useFetch(
    () => desksApi.freeNow(pool, kind || undefined),
    [pool, kind],
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
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && data.length === 0 && <Empty icon={Armchair} label={t("Nothing is free right now.")} />}
      {data && data.length > 0 && (
        <ul className="space-y-2">
          {data.map((place) => {
            const Icon = place.kind === "meeting_room" ? DoorOpen : Armchair;
            return (
              <li
                key={place.id}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
              >
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
                </div>
                <p className="shrink-0 text-sm tabular-nums text-slate-600 dark:text-slate-300">
                  {place.free_until
                    ? t("free until {{time}}", { time: formatTime(place.free_until) })
                    : t("free all day")}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
