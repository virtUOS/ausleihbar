// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarCheck } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDayWithWeekday } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import type { Reservation } from "./types";

const pad = (h: number) => String(h).padStart(2, "0");

/** Own upcoming reservations with check-in and cancel (F3 adds "Ich komme
 *  später", "Freigeben", moving and requests). */
export function MyReservationsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const [reload, setReload] = useState(0);
  const { data, loading, error } = useFetch(() => desksApi.myReservations(), [reload]);

  async function checkIn(r: Reservation) {
    try {
      await desksApi.checkIn(r.id);
      toast.success(t("Checked in."));
      setReload((n) => n + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  async function cancel(r: Reservation) {
    const ok = await confirm({
      message: t("Cancel the reservation of {{place}}?", { place: r.place.name }),
      confirmLabel: t("Cancel reservation"),
      cancelLabel: t("Keep"),
      danger: true,
    });
    if (!ok) return;
    try {
      await desksApi.cancelReservation(r.id);
      toast.success(t("Reservation cancelled."));
      setReload((n) => n + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  const btn =
    "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

  return (
    <section aria-labelledby="mine-title">
      <h2 id="mine-title" className="sr-only">
        {t("My reservations")}
      </h2>
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && data.length === 0 && (
        <Empty icon={CalendarCheck} label={t("You have no upcoming desk reservations.")} />
      )}
      {data && data.length > 0 && (
        <ul className="space-y-2">
          {data.map((r) => (
            <li
              key={r.id}
              className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"
            >
              <p className="font-medium text-slate-900 dark:text-slate-100">{r.place.name}</p>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {formatDayWithWeekday(r.day)}, {pad(r.start_hour)}:00–{pad(r.end_hour)}:00
              </p>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {[r.place.building, r.place.floor, r.place.room].filter(Boolean).join(" · ")}
              </p>
              {r.checked_in_at && (
                <p className="mt-1 text-sm font-medium text-emerald-700 dark:text-emerald-400">
                  {t("Checked in")}
                </p>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                {!r.checked_in_at && (
                  <button type="button" onClick={() => checkIn(r)} className={btn}>
                    {t("Check in")}
                  </button>
                )}
                <button type="button" onClick={() => cancel(r)} className={btn}>
                  {t("Cancel reservation")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
