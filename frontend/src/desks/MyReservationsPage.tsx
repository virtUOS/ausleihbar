// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CalendarCheck } from "lucide-react";
import { useFetch } from "../useFetch";
import { formatDayWithWeekday } from "../dates";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { desksApi } from "./api";
import { MyAbsences } from "./components/MyAbsences";
import { MyRequests } from "./components/MyRequests";
import { ReservationCard } from "./components/ReservationCard";
import { SeriesGroup } from "./components/SeriesGroup";
import { pad2 } from "./weekdays";
import type { BookedState } from "./bookNow";
import type { Reservation, Series } from "./types";

function groupByDay(rows: Reservation[]): [string, Reservation[]][] {
  const groups = new Map<string, Reservation[]>();
  for (const r of rows) groups.set(r.day, [...(groups.get(r.day) ?? []), r]);
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** Own upcoming reservations grouped by day (today first), with open swap and
 *  release requests on top. */
export function MyReservationsPage() {
  const { t } = useTranslation();
  const [reload, setReload] = useState(0);
  const mine = useFetch(() => desksApi.myReservations(), [reload]);
  const series = useFetch(() => desksApi.mySeries(), [reload]);
  const requests = useFetch(() => desksApi.myRequests(), [reload]);
  const changed = () => setReload((n) => n + 1);

  // Coming from a booking: highlight the reservations just made (this visit
  // only — the state is dropped so a reload shows the plain list).
  const location = useLocation();
  const navigate = useNavigate();
  const [booked] = useState(() => new Set((location.state as BookedState | null)?.booked ?? []));
  useEffect(() => {
    if (location.state) navigate(".", { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // …and scroll the first of them into view once the list is there.
  // Groups holding a just-booked occurrence start expanded, so the target
  // exists once both lists are loaded.
  // Keep the last loaded lists while reloading, so groups don't flicker out.
  const [lastMine, setLastMine] = useState<Reservation[] | null>(null);
  const [lastSeries, setLastSeries] = useState<Series[] | null>(null);
  useEffect(() => {
    if (mine.data) setLastMine(mine.data);
  }, [mine.data]);
  useEffect(() => {
    if (series.data) setLastSeries(series.data);
  }, [series.data]);
  // Remembered lists bridge a reload only; after an error no stale rows show.
  const mineRows = mine.data ?? (mine.loading ? lastMine : null);
  const seriesRows = series.data ?? (series.loading ? lastSeries : null);
  // Series whose group is open; seeded with those holding a just-booked date.
  const [open, setOpen] = useState<Set<number> | null>(null);
  const [seeded, setSeeded] = useState(false);
  useEffect(() => {
    if (seeded || !mineRows) return;
    setSeeded(true);
    setOpen(new Set(mineRows.filter((r) => r.series_id != null && booked.has(r.id)).map((r) => r.series_id as number)));
  }, [mineRows, seeded, booked]);
  const toggle = (id: number) =>
    setOpen((cur) => {
      const next = new Set(cur ?? []);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const listReady = !!mineRows && (!!seriesRows || !!series.error) && open !== null;
  useEffect(() => {
    if (listReady && booked.size) document.querySelector("[data-just-booked]")?.scrollIntoView({ block: "nearest" });
  }, [listReady, booked]);

  const todayIso = (() => {
    const d = new Date();
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  })();
  const activeSeries = (seriesRows ?? []).filter((sr) => !sr.cancelled_at && sr.valid_until >= todayIso);
  const bySeries = new Map<number, Reservation[]>();
  for (const r of mineRows ?? []) {
    if (r.series_id != null) bySeries.set(r.series_id, [...(bySeries.get(r.series_id) ?? []), r]);
  }
  const seriesIds = new Set(activeSeries.map((sr) => sr.id));
  // Occurrences of a series we don't list (e.g. series fetch failed) stay visible by day.
  const standalone = (mineRows ?? []).filter((r) => r.series_id == null || !seriesIds.has(r.series_id));
  const incoming = requests.data?.incoming ?? [];
  const outgoing = requests.data?.outgoing ?? [];

  return (
    <section aria-labelledby="mine-title">
      <h2 id="mine-title" className="sr-only">
        {t("My reservations")}
      </h2>

      {(incoming.length > 0 || outgoing.length > 0) && (
        <MyRequests incoming={incoming} outgoing={outgoing} onChanged={changed} />
      )}

      <MyAbsences onChanged={changed} />

      {series.error && <ErrorBox message={series.error} />}
      {listReady && activeSeries.length > 0 && (
        <h3 className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">{t("Series bookings")}</h3>
      )}
      {listReady && activeSeries.length > 0 && (
        <ul className="mb-6 space-y-2">
          {activeSeries.map((sr) => (
            <SeriesGroup
              key={sr.id}
              series={sr}
              occurrences={bySeries.get(sr.id) ?? []}
              justBooked={booked}
              expanded={open?.has(sr.id) ?? false}
              onToggle={() => toggle(sr.id)}
              onChanged={changed}
            />
          ))}
        </ul>
      )}

      {requests.error && <ErrorBox message={requests.error} />}
      {!listReady && !mine.error && <Loading />}
      {mine.error && <ErrorBox message={mine.error} />}
      {listReady && mineRows?.length === 0 && activeSeries.length === 0 && (
        <Empty icon={CalendarCheck} label={t("You have no upcoming desk reservations.")} />
      )}
      {listReady && standalone.length > 0 && (
        <h3 className="mb-2 text-sm font-bold text-slate-900 dark:text-slate-100">{t("Single bookings")}</h3>
      )}
      {listReady &&
        groupByDay(standalone).map(([day, rows]) => (
          <div key={day} className="mb-4">
            <h4 className="mb-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
              {formatDayWithWeekday(day)}
            </h4>
            <ul className="space-y-2">
              {rows.map((r) => (
                <ReservationCard key={r.id} reservation={r} onChanged={changed} justBooked={booked.has(r.id)} />
              ))}
            </ul>
          </div>
        ))}
    </section>
  );
}
