// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
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

export function BookingDetailPage() {
  const { t } = useTranslation();
  const { code } = useParams();
  const navigate = useNavigate();
  const { user, login } = useAuth();
  const [version, setVersion] = useState(0);
  const { data, loading, error } = useFetch<Booking | null>(
    () => (user?.authenticated ? api.getMyBookingByCode(code!) : Promise.resolve(null)),
    [code, version, user?.authenticated],
  );

  if (!user?.authenticated) {
    return (
      <div className="py-10 text-center">
        <p className="mb-3 text-slate-600 dark:text-slate-300">
          {t("Please sign in to view booking {{code}}.", { code })}
        </p>
        <button
          onClick={login}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
        >
          {t("Sign in")}
        </button>
      </div>
    );
  }

  async function cancel() {
    if (!data) return;
    await api.cancelBooking(data.id);
    setVersion((v) => v + 1);
  }

  return (
    <div className="pb-10">
      <Breadcrumbs
        items={[{ label: t("My bookings"), to: "/bookings" }, { label: code ?? "" }]}
      />

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data === null && !loading && <Empty label={t("Booking not found.")} />}

      {data && (
        <>
          <div className="mb-1 flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">{data.code}</h1>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                STATUS_STYLE[data.status] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
              }`}
            >
              {bookingStatusLabel(data.status)}
            </span>
          </div>
          {/* Plain-language explanation of the current state (#12). */}
          <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
            {bookingStatusHint(data.status)}
          </p>

          <div className="space-y-3">
            {data.groups.map((group) => (
              <div
                key={group.pool_id}
                className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
              >
                <p className="font-semibold text-slate-900 dark:text-slate-100">
                  {t("Pickup at {{pool}}", { pool: group.pool })}
                  {group.room && <span className="text-slate-500 dark:text-slate-400"> · {group.room}</span>}
                </p>
                {group.periods.map((period, i) => (
                  <div key={i} className="mt-2 text-sm">
                    <p className="text-slate-500 dark:text-slate-400">
                      {formatPeriod(period.start, period.end, period.lending_type)}
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {period.items.map((item) => (
                        <li key={item.id} className="text-slate-700 dark:text-slate-200">
                          <span className="font-medium text-slate-900 dark:text-slate-100">
                            {item.product_title}
                          </span>{" "}
                          · {item.inventory_number}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ))}
          </div>

          {data.note && (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
              {t("Message: {{note}}", { note: data.note })}
            </p>
          )}

          {(data.status === "pending" || data.status === "confirmed") && (
            <button
              type="button"
              onClick={cancel}
              className="mt-4 text-sm text-red-600 hover:underline dark:text-red-400"
            >
              {t("Cancel booking")}
            </button>
          )}

          <div className="mt-4">
            <button
              type="button"
              onClick={() => navigate("/bookings")}
              className="text-sm text-slate-600 hover:underline dark:text-slate-300"
            >
              {t("‹ All my bookings")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
