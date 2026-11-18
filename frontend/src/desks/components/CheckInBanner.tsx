// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MapPinCheck, Trash2 } from "lucide-react";
import { useFetch } from "../../useFetch";
import { formatTime } from "../../dates";
import { desksApi } from "../api";
import { canCheckIn, useMinuteNow } from "../checkIn";
import type { Reservation } from "../types";
import { activeLateUntil, btnIcon, LateControls, useReservationActions, type ActionDone } from "./reservationActions";

/** The own reservations that can be checked in right now, as a highlighted
 *  strip above every desk page (except "Meine Buchungen", whose cards carry
 *  the same actions). The strip itself checks in; "I'll be late" and delete
 *  sit next to it. Reloads on navigation, every 5 minutes and when the tab
 *  becomes visible. */
export function CheckInBanner() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const now = useMinuteNow();
  const [reload, setReload] = useState(0);
  // `now` changes every minute; reload the list every fifth minute only.
  const slot = Math.floor(now / 300_000);
  const { data } = useFetch(() => desksApi.myReservations(), [pathname, slot, reload]);
  // Keep the last list while reloading, so the strip doesn't flicker.
  const [rows, setRows] = useState(data);
  useEffect(() => {
    if (data) setRows(data);
  }, [data]);

  if (pathname.startsWith("/desks/mine")) return null;
  const due = (rows ?? []).filter((r) => r.status === "active" && canCheckIn(r, now));
  if (due.length === 0) return null;

  // After an action the list reloads; a checked-in or deleted booking drops
  // out at once, a "late" one stays (still to check in).
  const changed = (id: number, done: ActionDone) => {
    if (done === "checked_in" || done === "deleted") setRows((cur) => cur?.filter((r) => r.id !== id) ?? cur);
    setReload((n) => n + 1);
  };

  return (
    <section aria-label={t("Check in now")} className="mb-4 space-y-2 print:hidden">
      {due.map((r) => (
        <BannerRow key={r.id} r={r} now={now} onChanged={changed} />
      ))}
    </section>
  );
}

function BannerRow({
  r,
  now,
  onChanged,
}: {
  r: Reservation;
  now: number;
  onChanged: (id: number, done: ActionDone) => void;
}) {
  const { t } = useTranslation();
  const actions = useReservationActions(r, now, (done) => onChanged(r.id, done));
  const lateUntil = activeLateUntil(r, now);

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-brand-400 bg-brand-50 p-1.5 dark:border-brand-500/60 dark:bg-brand-900/30">
      <button
        type="button"
        disabled={actions.busy}
        onClick={actions.checkIn}
        aria-label={t("Check in at {{name}}", { name: r.place.name })}
        title={t("Check in")}
        className="flex min-h-[44px] min-w-0 grow basis-56 items-center gap-3 rounded-lg px-1.5 text-left transition-colors duration-150 hover:bg-brand-100 disabled:opacity-50 dark:hover:bg-brand-900/50"
      >
        <span
          aria-hidden
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-500 text-slate-900"
        >
          <MapPinCheck className="h-5 w-5" />
        </span>
        <span className="min-w-0 text-sm text-slate-900 dark:text-slate-100">
          <span className="font-semibold">{t("Check in now")}:</span> {r.place.name} · {formatTime(r.start)}–
          {formatTime(r.end)}
          {lateUntil && (
            <span className="text-slate-600 dark:text-slate-300">
              {" "}
              · {t("Late until {{time}}", { time: formatTime(lateUntil) })}
            </span>
          )}
        </span>
      </button>
      <div className={`flex flex-wrap items-center gap-1.5 ${actions.late.open ? "basis-full justify-end" : ""}`}>
        <LateControls actions={actions} />
        <button
          type="button"
          disabled={actions.busy}
          aria-label={t("Delete")}
          title={t("Delete")}
          onClick={actions.remove}
          className={`${btnIcon} bg-white dark:bg-slate-900`}
        >
          <Trash2 aria-hidden className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
