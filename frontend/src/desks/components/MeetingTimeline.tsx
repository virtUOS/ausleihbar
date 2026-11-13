// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { stateMeta } from "./placeStates";
import type { MeetingRoomDay } from "../types";

const pad = (h: number) => `${String(h).padStart(2, "0")}:00`;

export function MeetingTimeline({ room, open }: { room: MeetingRoomDay; open: [number, number] | null }) {
  const { t } = useTranslation();
  let from = open ? open[0] : 6;
  let to = open ? open[1] : 20;
  for (const r of room.reservations) {
    from = Math.min(from, r.start_hour);
    to = Math.max(to, r.end_hour);
  }
  const span = Math.max(to - from, 1);
  const cols = Array.from({ length: span }, (_, i) => from + i);
  const pct = (h: number) => `${((h - from) / span) * 100}%`;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2">
        <p className="font-medium text-slate-900 dark:text-slate-100">{room.name}</p>
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {[room.floor, room.room].filter(Boolean).join(" · ")}
          {room.capacity ? ` · ${t("{{count}} seats", { count: room.capacity })}` : ""}
        </p>
      </div>
      <div className="overflow-x-auto" aria-hidden>
        <div className="min-w-[560px]">
          <div className="relative h-5 text-[11px] text-slate-600 dark:text-slate-300" aria-hidden>
            {cols.map((h) => (
              <span key={h} className="absolute" style={{ left: pct(h) }}>
                {h}
              </span>
            ))}
          </div>
          <div className="relative h-16 rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
            {cols.slice(1).map((h) => (
              <span
                key={h}
                aria-hidden
                className="absolute inset-y-0 border-l border-slate-200 dark:border-slate-700"
                style={{ left: pct(h) }}
              />
            ))}
            {room.reservations.map((r) => (
              <div
                key={r.id}
                className={`absolute inset-y-1 overflow-hidden rounded-md border px-1.5 py-0.5 text-[11px] leading-tight ${stateMeta(r.state).pill} ${r.mine ? "ring-2 ring-brand-500" : ""}`}
                style={{ left: pct(r.start_hour), width: `calc(${((r.end_hour - r.start_hour) / span) * 100}% - 2px)` }}
                title={[`${pad(r.start_hour)}–${pad(r.end_hour)}`, r.holder ?? t("Person (hidden)"), r.comment].filter(Boolean).join(" · ")}
              >
                <span className="block truncate font-semibold">
                  {r.mine ? t("Your reservation") : (r.holder ?? t("Person (hidden)"))}
                </span>
                {r.comment && <span className="block truncate">{r.comment}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
      {room.reservations.length === 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">{t("No reservations this day.")}</p>
      )}
      <ul className="sr-only">
        {room.reservations.map((r) => (
          <li key={r.id}>
            {[`${pad(r.start_hour)}–${pad(r.end_hour)}: ${r.holder ?? t("Person (hidden)")}`, r.comment].filter(Boolean).join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}
