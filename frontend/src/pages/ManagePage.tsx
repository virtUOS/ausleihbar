// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import i18n from "../i18n";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { BookingRow } from "../components/BookingRow";
import { ManageTabs } from "../components/ManageTabs";
import { MonthCalendar } from "../components/MonthCalendar";
import { todayIso } from "../manage";
import type { DayOverview, ManageCalendarDay, ManagedBooking } from "../types";

const pad = (n: number) => String(n).padStart(2, "0");
const isoOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

// Reservations awaiting confirmation now live on their own page (/manage/confirm),
// surfaced via the badge in the lending-desk navigation.
type SectionKey = "overdue" | "pickups" | "returns";

const SECTIONS: { key: SectionKey; title: () => string }[] = [
  { key: "overdue", title: () => i18n.t("⚠ Overdue") },
  { key: "pickups", title: () => i18n.t("Pickups") },
  { key: "returns", title: () => i18n.t("Returns due") },
];

export function ManagePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const today = todayIso();
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [date, setDate] = useState(today);
  const [version, setVersion] = useState(0);

  const from = isoOf(view.year, view.month, 1);
  const to = isoOf(view.month === 11 ? view.year + 1 : view.year, (view.month + 1) % 12, 1);

  const calendar = useFetch<{ days: ManageCalendarDay[]; closed_days: string[] }>(
    () => api.getManageCalendar(from, to),
    [from, to, version],
  );
  const overview = useFetch<DayOverview>(() => api.getDayOverview(date), [date, version]);

  const byDate = useMemo(() => {
    const map: Record<string, ManageCalendarDay> = {};
    calendar.data?.days.forEach((d) => (map[d.date] = d));
    return map;
  }, [calendar.data]);

  const closedDays = useMemo(
    () => new Set(calendar.data?.closed_days ?? []),
    [calendar.data],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const isEmpty =
    overview.data &&
    SECTIONS.every((s) => (overview.data![s.key] as ManagedBooking[]).length === 0);

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <div className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <MonthCalendar
          year={view.year}
          month={view.month}
          onMonthChange={(year, month) => setView({ year, month })}
          onDayClick={setDate}
          isSelected={(iso) => iso === date}
          isClosed={(iso) => closedDays.has(iso)}
          dayLabel={(iso, label) => {
            const c = byDate[iso];
            const parts: string[] = [];
            if (c?.pickups) parts.push(`${c.pickups} ${t("pickups")}`);
            if (c?.returns) parts.push(`${c.returns} ${t("returns")}`);
            if (closedDays.has(iso)) parts.push(t("closed"));
            return parts.length ? `${label}, ${parts.join(", ")}` : label;
          }}
          renderDay={(iso) => {
            const c = byDate[iso];
            if (!c || (c.pickups === 0 && c.returns === 0)) return null;
            return (
              <span className="mt-1 flex flex-wrap items-center justify-center gap-1 leading-none">
                {c.pickups > 0 && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full bg-brand-200 px-1.5 py-0.5 text-[11px] font-bold text-brand-900"
                    title={t("pickups")}
                  >
                    <ArrowUpRight aria-hidden className="h-3 w-3" />
                    {c.pickups}
                  </span>
                )}
                {c.returns > 0 && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full bg-slate-800 px-1.5 py-0.5 text-[11px] font-bold text-white"
                    title={t("returns")}
                  >
                    <ArrowDownLeft aria-hidden className="h-3 w-3" />
                    {c.returns}
                  </span>
                )}
              </span>
            );
          }}
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-4 items-center gap-0.5 rounded-full bg-brand-200 px-1.5 text-[10px] font-bold text-brand-900">
                <ArrowUpRight aria-hidden className="h-2.5 w-2.5" />
              </span>
              {t("Pickups")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-flex h-4 items-center gap-0.5 rounded-full bg-slate-800 px-1.5 text-[10px] font-bold text-white">
                <ArrowDownLeft aria-hidden className="h-2.5 w-2.5" />
              </span>
              {t("Returns")}
            </span>
            <span>{t("greyed = closed")}</span>
          </span>
          <button
            type="button"
            onClick={() => {
              setDate(today);
              setView({ year: now.getFullYear(), month: now.getMonth() });
            }}
            className="hover:underline"
          >
            {t("Today")}
          </button>
        </div>
      </div>

      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">{date}</h2>

      {overview.loading && <Loading />}
      {overview.error && <ErrorBox message={overview.error} />}

      {overview.data &&
        SECTIONS.map((section) => {
          const items = overview.data![section.key] as ManagedBooking[];
          if (!items || items.length === 0) return null;
          return (
            <section key={section.key} className="mb-6">
              <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                {section.title()} ({items.length})
              </h3>
              <div className="space-y-2">
                {items.map((booking) => (
                  <BookingRow
                    key={booking.id}
                    booking={booking}
                    mode={section.key}
                    date={date}
                    onActed={refetch}
                  />
                ))}
              </div>
            </section>
          );
        })}

      {isEmpty && !overview.loading && (
        <p className="py-10 text-center text-slate-500 dark:text-slate-400">{t("Nothing for this day.")}</p>
      )}
    </div>
  );
}
