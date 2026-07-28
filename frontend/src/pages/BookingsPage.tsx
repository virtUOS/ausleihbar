// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { TriangleAlert } from "lucide-react";
import i18n from "../i18n";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { DeleteButton } from "../components/RowActions";
import { formatPeriod } from "../manage";
import { bookingStatusHint, bookingStatusLabel } from "../bookingStatus";
import type { Booking } from "../types";

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  confirmed: "bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300",
  handed_out: "bg-purple-100 text-purple-800 dark:bg-purple-950/50 dark:text-purple-300",
  returned: "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300",
  cancelled: "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
};

// Three borrower-facing buckets (concept §4): things still ahead, things in
// hand right now, and everything that's finished one way or another. Each
// carries a one-line description so the categories are self-explanatory (#12).
const GROUPS: {
  key: string;
  title: string;
  description: string;
  statuses: string[];
  empty: string;
  cancellable?: boolean;
}[] = [
  {
    key: "upcoming",
    title: i18n.t("Upcoming"),
    description: i18n.t("Booked for you but not picked up yet."),
    statuses: ["pending", "confirmed"],
    empty: i18n.t("No upcoming bookings."),
    cancellable: true,
  },
  {
    key: "active",
    title: i18n.t("Currently out"),
    description: i18n.t("Items you have right now and still need to return."),
    statuses: ["handed_out"],
    empty: i18n.t("Nothing is currently out."),
  },
  {
    key: "past",
    title: i18n.t("Returned & cancelled"),
    description: i18n.t("Finished bookings — nothing left to do."),
    statuses: ["returned", "cancelled"],
    empty: i18n.t("No past bookings yet."),
  },
];

function BookingCard({
  booking,
  onCancel,
}: {
  booking: Booking;
  onCancel?: (id: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={`rounded-xl border p-4 ${
        booking.has_strike ? "border-red-300 bg-red-50 dark:border-red-900/50 dark:bg-red-950/40" : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/bookings/${booking.code}`}
            className="text-sm font-semibold text-slate-900 dark:text-slate-100 hover:underline"
          >
            {booking.code}
          </Link>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              STATUS_STYLE[booking.status] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
            }`}
          >
            {bookingStatusLabel(booking.status)}
          </span>
          {booking.has_strike && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-950/50 dark:text-red-300"
              title={booking.strike_reason || undefined}
            >
              <TriangleAlert aria-hidden className="h-3.5 w-3.5" />
              {t("Strike received")}
            </span>
          )}
        </div>
        {onCancel && (
          <DeleteButton
            onClick={() => onCancel(booking.id)}
            label={t("Cancel booking")}
            className="shrink-0"
          />
        )}
      </div>
      {/* Plain-language explanation of the current state (#12). */}
      <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
        {bookingStatusHint(booking.status)}
      </p>
      <ul className="mt-3 space-y-1 text-sm">
        {booking.items.map((item) => (
          <li key={item.id} className="text-slate-700 dark:text-slate-200">
            <span className="font-medium text-slate-900 dark:text-slate-100">{item.product_title}</span>
            {" · "}
            {item.pool_id ? (
              <Link
                to={`/pools/${item.pool_id}`}
                className="text-slate-700 dark:text-slate-200 hover:text-brand-700 dark:hover:text-brand-400 hover:underline"
              >
                {item.pool}
              </Link>
            ) : (
              item.pool
            )}
            {" · "}
            <span className="text-slate-500 dark:text-slate-400">
              {formatPeriod(item.start, item.end, item.lending_type)}
            </span>
          </li>
        ))}
      </ul>
      {booking.strike_reason && (
        <p className="mt-2 text-sm text-red-700 dark:text-red-300">
          {t("Strike reason: {{reason}}", { reason: booking.strike_reason })}
        </p>
      )}
      {booking.note && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{t("Message: {{note}}", { note: booking.note })}</p>
      )}
    </div>
  );
}

export function BookingsPage() {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const [version, setVersion] = useState(0);
  const { data, loading, error } = useFetch(() => api.listMyBookings(), [version]);

  if (!user?.authenticated) {
    return (
      <div className="py-10 text-center">
        <p className="mb-3 text-slate-600 dark:text-slate-300">{t("Please sign in to see your bookings.")}</p>
        <button
          onClick={login}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
        >
          {t("Sign in")}
        </button>
      </div>
    );
  }

  async function cancel(id: number) {
    await api.cancelBooking(id);
    setVersion((v) => v + 1);
  }

  const bookings = data?.results ?? [];

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold text-slate-900 dark:text-slate-100">{t("My bookings")}</h1>
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && bookings.length === 0 && <Empty label={t("No bookings yet.")} />}

      {data && bookings.length > 0 && (
        <div className="space-y-8">
          {GROUPS.map((group) => {
            const items = bookings.filter((b) => group.statuses.includes(b.status));
            return (
              <section key={group.key}>
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {group.title}
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {items.length}
                  </span>
                </h2>
                <p className="mb-3 mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  {group.description}
                </p>
                {items.length === 0 ? (
                  <p className="text-sm text-slate-400 dark:text-slate-500">{group.empty}</p>
                ) : (
                  <div className="space-y-3">
                    {items.map((booking) => (
                      <BookingCard
                        key={booking.id}
                        booking={booking}
                        onCancel={group.cancellable ? cancel : undefined}
                      />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
