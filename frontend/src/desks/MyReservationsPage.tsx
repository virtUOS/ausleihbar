// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarCheck } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDayWithWeekday } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";
import { ReservationCard } from "./components/ReservationCard";
import type { DeskRequest, Reservation } from "./types";

const pad = (h: number) => String(h).padStart(2, "0");

const btn =
  "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

function groupByDay(rows: Reservation[]): [string, Reservation[]][] {
  const groups = new Map<string, Reservation[]>();
  for (const r of rows) groups.set(r.day, [...(groups.get(r.day) ?? []), r]);
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** Own upcoming reservations grouped by day (today first), with open swap and
 *  release requests on top. */
export function MyReservationsPage() {
  const { t } = useTranslation();
  const toast = useToast();
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const mine = useFetch(() => desksApi.myReservations(), [reload]);
  const requests = useFetch(() => desksApi.myRequests(), [reload]);
  const changed = () => setReload((n) => n + 1);

  async function answer(req: DeskRequest, accept: boolean) {
    setBusy(true);
    try {
      if (req.type === "swap") await desksApi.answerSwap(req.id, accept);
      else await desksApi.answerRelease(req.id, accept);
      toast.success(accept ? t("Request accepted.") : t("Request declined."));
      changed();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  const when = (b?: DeskRequest["own"]) =>
    b ? `${b.place.name}, ${formatDayWithWeekday(b.day)} ${pad(b.start_hour)}:00–${pad(b.end_hour)}:00` : "";

  function incomingText(req: DeskRequest) {
    if (req.type === "swap") {
      return t("Someone asks to swap: you give {{own}} and get {{other}}.", {
        own: when(req.own),
        other: when(req.other),
      });
    }
    return req.requester_name
      ? t("{{name}} asks you to release {{own}}.", { name: req.requester_name, own: when(req.own) })
      : t("Someone asks you to release {{own}}.", { own: when(req.own) });
  }

  function outgoingText(req: DeskRequest) {
    const who = req.other_holder_name ?? t("Person (hidden)");
    return req.type === "swap"
      ? t("Waiting for {{name}}: swap with {{other}}.", { name: who, other: when(req.other) })
      : t("Waiting for {{name}}: release of {{other}}.", { name: who, other: when(req.other) });
  }

  const incoming = requests.data?.incoming ?? [];
  const outgoing = requests.data?.outgoing ?? [];

  return (
    <section aria-labelledby="mine-title">
      <h2 id="mine-title" className="sr-only">
        {t("My reservations")}
      </h2>

      {(incoming.length > 0 || outgoing.length > 0) && (
        <div className="mb-6 space-y-2">
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">{t("Requests")}</h3>
          {incoming.map((req) => (
            <div
              key={`in-${req.type}-${req.id}`}
              className="rounded-xl border border-brand-300 bg-brand-50 p-3 dark:border-brand-700/60 dark:bg-brand-900/20"
            >
              <p className="text-sm text-slate-900 dark:text-slate-100">{incomingText(req)}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => answer(req, true)}
                  className="min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 hover:bg-brand-400 disabled:opacity-50"
                >
                  {t("Accept")}
                </button>
                <button type="button" disabled={busy} onClick={() => answer(req, false)} className={btn}>
                  {t("Decline")}
                </button>
              </div>
            </div>
          ))}
          {outgoing.map((req) => (
            <p
              key={`out-${req.type}-${req.id}`}
              className="rounded-xl border border-slate-200 p-3 text-sm text-slate-700 dark:border-slate-800 dark:text-slate-200"
            >
              {outgoingText(req)}
            </p>
          ))}
        </div>
      )}

      {mine.loading && <Loading />}
      {mine.error && <ErrorBox message={mine.error} />}
      {mine.data && mine.data.length === 0 && (
        <Empty icon={CalendarCheck} label={t("You have no upcoming desk reservations.")} />
      )}
      {mine.data &&
        groupByDay(mine.data).map(([day, rows]) => (
          <div key={day} className="mb-6">
            <h3 className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">
              {formatDayWithWeekday(day)}
            </h3>
            <ul className="space-y-2">
              {rows.map((r) => (
                <ReservationCard key={r.id} reservation={r} onChanged={changed} />
              ))}
            </ul>
          </div>
        ))}
    </section>
  );
}
