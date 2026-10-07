// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { BookingRow } from "../components/BookingRow";
import { DateField } from "../components/DateField";
import { ManageTabs } from "../components/ManageTabs";
import { Pager } from "../components/Pager";
import { SortToggle } from "../components/SortToggle";
import { shiftDate, todayIso } from "../manage";
import type { ManagedBooking, Paginated } from "../types";

type Ordering = "start" | "created";
type Period = "all" | "today" | "week" | "month" | "custom";

const PERIODS: Period[] = ["all", "today", "week", "month", "custom"];

/** Inclusive local-date range for a preset period (week starts Monday). */
function presetRange(period: Period): { from?: string; to?: string } {
  const today = todayIso();
  if (period === "today") return { from: today, to: today };
  if (period === "week") {
    const [y, m, d] = today.split("-").map(Number);
    const dow = (new Date(y, m - 1, d).getDay() + 6) % 7; // Mon = 0
    const monday = shiftDate(today, -dow);
    return { from: monday, to: shiftDate(monday, 6) };
  }
  if (period === "month") {
    const [y, m] = today.split("-").map(Number);
    const pad = (n: number) => String(n).padStart(2, "0");
    const last = new Date(y, m, 0).getDate();
    return { from: `${y}-${pad(m)}-01`, to: `${y}-${pad(m)}-${pad(last)}` };
  }
  return {};
}

export function ManageListPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [params, setParams] = useSearchParams();

  const search = params.get("q") ?? "";
  const ordering: Ordering = params.get("sort") === "created" ? "created" : "start";
  const periodParam = params.get("period") as Period | null;
  const period: Period = periodParam && PERIODS.includes(periodParam) ? periodParam : "all";
  const customFrom = params.get("from") ?? "";
  const customTo = params.get("to") ?? "";
  const pageParam = parseInt(params.get("page") ?? "1", 10);
  const page = Number.isInteger(pageParam) && pageParam > 0 ? pageParam : 1;

  const range =
    period === "custom"
      ? { from: customFrom || undefined, to: customTo || undefined }
      : presetRange(period);
  const rangeInvalid = Boolean(range.from && range.to && range.from > range.to);

  // Local input state, debounced into the URL query.
  const [query, setQuery] = useState(search);
  useEffect(() => setQuery(search), [search]);
  useEffect(() => {
    const handle = setTimeout(() => {
      const next = query.trim();
      if (next !== search) update({ q: next }, true);
    }, 250);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  /** Patch the URL query; any change except paging resets to page 1. */
  function update(patch: Record<string, string | undefined>, resetPage = true) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        if (resetPage && !("page" in patch)) next.delete("page");
        return next;
      },
      { replace: true },
    );
  }

  const { data, loading, error } = useFetch<Paginated<ManagedBooking> | null>(
    () =>
      rangeInvalid
        ? Promise.resolve(null)
        : api.listManagedBookings({
            search: search || undefined,
            ordering,
            from: range.from,
            to: range.to,
            page,
          }),
    [version, search, ordering, range.from, range.to, page, rangeInvalid],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const count = data?.count ?? 0;
  const pager = {
    page,
    count,
    hasPrev: Boolean(data?.previous),
    hasNext: Boolean(data?.next),
    setPage: (p: number) => update({ page: p > 1 ? String(p) : undefined }, false),
  };
  const periodLabels: Record<Period, string> = {
    all: t("All"),
    today: t("Today"),
    week: t("This week"),
    month: t("This month"),
    custom: t("Custom"),
  };

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs showPoolScope />

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("Search by booking number, customer or product…")}
        aria-label={t("Search by booking number, customer or product…")}
        className="mb-3 w-full rounded-full border border-slate-300 px-4 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
      />

      <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <SortToggle<Ordering>
          value={ordering}
          onChange={(v) => update({ sort: v === "start" ? undefined : v })}
          options={[
            { value: "start", label: t("Lending start") },
            { value: "created", label: t("Booking received") },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="booking-period" className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            {t("Period")}
          </label>
          <select
            id="booking-period"
            value={period}
            onChange={(e) => {
              const v = e.target.value as Period;
              update({ period: v === "all" ? undefined : v, from: undefined, to: undefined });
            }}
            className="rounded-full border border-slate-300 bg-white px-3 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {periodLabels[p]}
              </option>
            ))}
          </select>
          {period === "custom" && (
            <>
              <DateField
                ariaLabel={t("From")}
                value={customFrom}
                onChange={(v) => update({ from: v || undefined })}
              />
              <span aria-hidden className="text-slate-400">–</span>
              <DateField
                ariaLabel={t("To")}
                value={customTo}
                onChange={(v) => update({ to: v || undefined })}
              />
            </>
          )}
        </div>
      </div>

      {rangeInvalid && <ErrorBox message={t("The start date must not be after the end date.")} />}
      {loading && !rangeInvalid && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && data.results.length === 0 && (
        <Empty label={period === "all" && !search ? t("No bookings found.") : t("No bookings in this period.")} />
      )}

      <div className="space-y-2">
        {data?.results.map((booking) => (
          <BookingRow key={booking.id} booking={booking} mode="browse" onActed={refetch} />
        ))}
      </div>
      {data && <Pager list={pager} />}
    </div>
  );
}
