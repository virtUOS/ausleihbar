// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MapPinCheck } from "lucide-react";
import { useFetch } from "../../useFetch";
import { formatTime } from "../../dates";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { canCheckIn, useMinuteNow } from "../checkIn";

/** The own reservations that can be checked in right now, as a highlighted
 *  strip above every desk page (except "Meine Buchungen", whose cards carry
 *  the same button). Reloads on navigation, every 5 minutes and when the tab
 *  becomes visible. */
export function CheckInBanner() {
  const { t } = useTranslation();
  const toast = useToast();
  const { pathname } = useLocation();
  const now = useMinuteNow();
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState<number | null>(null);
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

  async function checkIn(id: number) {
    setBusy(id);
    try {
      await desksApi.checkIn(id);
      toast.success(t("Checked in."));
      setRows((cur) => cur?.filter((r) => r.id !== id) ?? cur);
      setReload((n) => n + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      aria-label={t("Check in now")}
      className="mb-4 space-y-2 print:hidden"
    >
      {due.map((r) => (
        <div
          key={r.id}
          className="flex flex-wrap items-center gap-3 rounded-xl border border-brand-400 bg-brand-50 p-3 dark:border-brand-500/60 dark:bg-brand-900/30"
        >
          <MapPinCheck aria-hidden className="h-5 w-5 shrink-0 text-brand-700 dark:text-brand-300" />
          <p className="min-w-0 grow basis-48 text-sm text-slate-900 dark:text-slate-100">
            <span className="font-semibold">{t("Check in now")}:</span>{" "}
            {r.place.name} · {formatTime(r.start)}–{formatTime(r.end)}
          </p>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => checkIn(r.id)}
            aria-label={t("Check in at {{name}}", { name: r.place.name })}
            title={t("Check in")}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-500 text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50"
          >
            <MapPinCheck aria-hidden className="h-5 w-5" />
          </button>
        </div>
      ))}
    </section>
  );
}
