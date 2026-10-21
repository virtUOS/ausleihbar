// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import { api } from "../api";
import { formatPeriod } from "../manage";
import { bookingStatusClass, bookingStatusLabel, bookingUseKind } from "../bookingStatus";
import { formatDate, formatDateTime } from "../dates";
import type { Booking, Paginated } from "../types";

type GroupKey = "upcoming" | "handed_out" | "completed";
type BookingsFetcher = (
  id: number,
  group: GroupKey,
  page: number,
) => Promise<Paginated<Booking>>;

const GROUPS: { key: "upcoming" | "handed_out" | "completed"; title: string }[] = [
  { key: "upcoming", title: i18n.t("Upcoming") },
  { key: "handed_out", title: i18n.t("Handed out") },
  { key: "completed", title: i18n.t("Completed") },
];

function fmt(iso: string | null): string {
  if (!iso) return "–";
  const d = new Date(iso);
  const hasTime = d.getHours() !== 0 || d.getMinutes() !== 0;
  return hasTime ? formatDateTime(iso) : formatDate(iso);
}

function BookingCard({ booking }: { booking: Booking }) {
  useTranslation(); // re-render on language change (labels resolve via i18n.t)
  return (
    <li className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <div className="mb-1 flex items-center gap-2 text-sm">
        <span className="font-medium text-slate-900 dark:text-slate-100">
          {booking.code || `#${booking.id}`}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            bookingStatusClass(booking.status)
          }`}
        >
          {bookingStatusLabel(booking.status, bookingUseKind(booking))}
        </span>
        <span className="text-xs text-slate-400 dark:text-slate-300">{fmt(booking.created_at)}</span>
      </div>
      <ul className="space-y-0.5 text-sm text-slate-600 dark:text-slate-300">
        {booking.items.map((item) => (
          <li key={item.id} className="flex flex-wrap justify-between gap-x-3">
            <span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                {item.inventory_number}
              </span>{" "}
              · {item.product_title}
              <span className="text-slate-400 dark:text-slate-300"> · {item.pool}</span>
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-300">
              {formatPeriod(item.start, item.end, item.lending_type)}
            </span>
          </li>
        ))}
      </ul>
    </li>
  );
}

function HistoryGroup({
  userId,
  group,
  title,
  getBookings,
}: {
  userId: number;
  group: GroupKey;
  title: string;
  getBookings: BookingsFetcher;
}) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Booking[]>([]);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getBookings(userId, group, page)
      .then((res) => {
        if (!active) return;
        setItems((prev) => (page === 1 ? res.results : [...prev, ...res.results]));
        setCount(res.count);
        setHasNext(Boolean(res.next));
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [userId, group, page, getBookings]);

  return (
    <div>
      <h5 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-300">
        {title} ({count})
      </h5>
      {items.length === 0 && !loading ? (
        <p className="text-sm text-slate-400 dark:text-slate-300">{t("None.")}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((b) => (
            <BookingCard key={b.id} booking={b} />
          ))}
        </ul>
      )}
      {hasNext && (
        <button
          type="button"
          onClick={() => setPage((p) => p + 1)}
          disabled={loading}
          className="mt-2 text-sm font-medium text-slate-600 underline underline-offset-2 disabled:opacity-40 dark:text-slate-300"
        >
          {loading ? t("Loading…") : t("Show more")}
        </button>
      )}
    </div>
  );
}

/** A user's bookings grouped into upcoming, handed-out and completed.
 *  `getBookings` defaults to the admin endpoint; the lending-desk borrower
 *  profile passes the lender-accessible one. */
export function UserBookingHistory({
  userId,
  getBookings = api.getUserBookings,
}: {
  userId: number;
  getBookings?: BookingsFetcher;
}) {
  return (
    <div className="space-y-5">
      {GROUPS.map((g) => (
        <HistoryGroup
          key={g.key}
          userId={userId}
          group={g.key}
          title={g.title}
          getBookings={getBookings}
        />
      ))}
    </div>
  );
}
