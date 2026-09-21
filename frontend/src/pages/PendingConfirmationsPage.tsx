// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { BookingRow } from "../components/BookingRow";
import { ManageTabs } from "../components/ManageTabs";
import type { ManagedBooking, Paginated } from "../types";

/** Dedicated page listing reservations awaiting the lender's confirmation. */
export function PendingConfirmationsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);

  const { data, loading, error } = useFetch<Paginated<ManagedBooking>>(
    () => api.listManagedBookings({ status: "pending" }),
    [version],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  // Bump the version: refetches the list and (via ManageTabs) the badge count.
  const refetch = () => setVersion((v) => v + 1);
  const bookings = data?.results ?? [];

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs pendingVersion={version} />

      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Bookings to confirm")}
        {bookings.length > 0 && (
          <span className="ml-2 font-normal text-slate-400 dark:text-slate-400">({bookings.length})</span>
        )}
      </h2>

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && bookings.length === 0 && (
        <Empty label={t("Nothing to confirm right now.")} />
      )}

      <div className="space-y-2">
        {bookings.map((booking) => (
          <BookingRow
            key={booking.id}
            booking={booking}
            mode="to_confirm"
            onActed={refetch}
          />
        ))}
      </div>
    </div>
  );
}
