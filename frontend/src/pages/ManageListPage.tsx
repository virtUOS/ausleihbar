// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { BookingRow } from "../components/BookingRow";
import { ManageTabs } from "../components/ManageTabs";
import type { ManagedBooking, Paginated } from "../types";

export function ManageListPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");

  // Debounce the query into the server-side search term.
  useEffect(() => {
    const handle = setTimeout(() => setSearch(query.trim()), 250);
    return () => clearTimeout(handle);
  }, [query]);

  const { data, loading, error } = useFetch<Paginated<ManagedBooking>>(
    () => api.listManagedBookings({ search: search || undefined }),
    [version, search],
  );

  const byCustomer = useMemo(() => {
    const map = new Map<
      number,
      { name: string; bookings: ManagedBooking[] }
    >();
    for (const booking of data?.results ?? []) {
      const entry = map.get(booking.borrower_id);
      if (entry) {
        entry.bookings.push(booking);
      } else {
        map.set(booking.borrower_id, {
          name: booking.borrower_name || booking.borrower,
          bookings: [booking],
        });
      }
    }
    return [...map.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name));
  }, [data]);

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("Search by booking number, customer or product…")}
        className="mb-5 w-full rounded-full border border-slate-300 px-4 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
      />

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && byCustomer.length === 0 && <Empty label={t("No bookings found.")} />}

      {byCustomer.map(([borrowerId, { name, bookings }]) => (
        <section key={borrowerId} className="mb-6">
          <h2 className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
            <Link
              to={`/manage/users/${borrowerId}`}
              className="hover:underline"
              title={t("Open borrower profile")}
            >
              {name}
            </Link>
            <span className="text-xs font-normal text-slate-400 dark:text-slate-400">
              {t("{{count}} booking", { count: bookings.length })}
            </span>
          </h2>
          <div className="space-y-2">
            {bookings.map((booking) => (
              <BookingRow
                key={booking.id}
                booking={booking}
                mode="browse"
                onActed={refetch}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
