// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import i18n from "../i18n";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { BookingRow } from "../components/BookingRow";
import { ManageTabs } from "../components/ManageTabs";
import { MonthCalendar } from "../components/MonthCalendar";
import { todayIso } from "../manage";
import { poolAccent } from "../poolAccent";
import type { DayOverview, ManageCalendarDay, ManagedBooking, ResourcePool } from "../types";

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

const POOL_KEY = "ausleihbar.manage.dayPool";

function readStoredPool(): number | null {
  try {
    const v = localStorage.getItem(POOL_KEY);
    return v ? Number(v) || null : null;
  } catch {
    return null;
  }
}

function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function shiftIso(iso: string, days: number): string {
  const d = parseIso(iso);
  d.setDate(d.getDate() + days);
  return isoOf(d.getFullYear(), d.getMonth(), d.getDate());
}

function Tile({
  label,
  value,
  detail,
  to,
  highlight,
}: {
  label: string;
  value: string | number;
  detail?: string;
  to: string;
  highlight?: boolean;
}) {
  const cls = highlight
    ? "border-red-300 bg-red-50 dark:border-red-500/40 dark:bg-red-950/30"
    : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900";
  const body = (
    <>
      <span className="block text-xs font-medium text-slate-600 dark:text-slate-300">{label}</span>
      <span className="block text-xl font-bold text-slate-900 dark:text-slate-100">{value}</span>
      {detail && <span className="block text-xs text-slate-600 dark:text-slate-300">{detail}</span>}
    </>
  );
  const common = `block rounded-xl border p-3 hover:border-brand-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 ${cls}`;
  return to.startsWith("#") ? (
    <a href={to} className={common}>{body}</a>
  ) : (
    <Link to={to} className={common}>{body}</Link>
  );
}

export function ManagePage() {
  const { t, i18n: i18nHook } = useTranslation();
  const { user } = useAuth();
  const today = todayIso();
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [date, setDate] = useState(today);
  const [version, setVersion] = useState(0);
  const [calOpen, setCalOpen] = useState(false);
  const [pool, setPool] = useState<number | null>(readStoredPool);

  const pools = useFetch<ResourcePool[]>(
    () => api.listPools({ pageSize: 200 }).then((r) => r.results.filter((p) => p.is_active)),
    [],
  );
  const poolList = pools.data ?? [];
  // A stored pool the user no longer manages must not silently filter to nothing.
  const activePool = pool !== null && poolList.some((p) => p.id === pool) ? pool : null;
  const waitingForPools = pool !== null && pools.loading;

  useEffect(() => {
    if (pools.data && pool !== null && activePool === null) setPool(null);
  }, [pools.data, pool, activePool]);

  const choosePool = (id: number | null) => {
    setPool(id);
    try {
      if (id === null) localStorage.removeItem(POOL_KEY);
      else localStorage.setItem(POOL_KEY, String(id));
    } catch {
      /* storage unavailable — filter just isn't remembered */
    }
  };

  const gotoDate = (iso: string) => {
    setDate(iso);
    const d = parseIso(iso);
    setView({ year: d.getFullYear(), month: d.getMonth() });
  };

  const from = isoOf(view.year, view.month, 1);
  const to = isoOf(view.month === 11 ? view.year + 1 : view.year, (view.month + 1) % 12, 1);

  const calendar = useFetch<{ days: ManageCalendarDay[]; closed_days: string[] }>(
    () => (waitingForPools ? new Promise(() => {}) : api.getManageCalendar(from, to, activePool)),
    [from, to, version, activePool, waitingForPools],
  );
  const overview = useFetch<DayOverview>(
    () => (waitingForPools ? new Promise(() => {}) : api.getDayOverview(date, activePool)),
    [date, version, activePool, waitingForPools],
  );

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
  const dateLabel = parseIso(date).toLocaleDateString(i18nHook.language, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const stats = overview.data?.stats;
  const doneOf = (x: { open: number; done: number }) =>
    t("{{done}} of {{total}} done", { done: x.done, total: x.done + x.open });
  const arrowCls =
    "rounded-full p-2 text-slate-700 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 dark:text-slate-200 dark:hover:bg-slate-800";

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      {poolList.length > 1 && (
        <div role="group" aria-label={t("Filter by pool")} className="mb-3 flex flex-wrap gap-2">
          <button
            type="button"
            aria-pressed={activePool === null}
            onClick={() => choosePool(null)}
            className={`rounded-full border px-3 py-1 text-sm ${
              activePool === null
                ? "border-brand-500 bg-brand-100 font-semibold text-slate-900"
                : "border-slate-200 text-slate-700 hover:border-brand-400 dark:border-slate-700 dark:text-slate-200"
            }`}
          >
            {t("All pools")}
          </button>
          {poolList.map((p) => {
            const accent = poolAccent(p.accent_color);
            const on = activePool === p.id;
            return (
              <button
                key={p.id}
                type="button"
                aria-pressed={on}
                onClick={() => choosePool(p.id)}
                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${
                  on
                    ? `${accent.border} ${accent.tint} font-semibold text-slate-900 dark:text-slate-100`
                    : "border-slate-200 text-slate-700 hover:border-brand-400 dark:border-slate-700 dark:text-slate-200"
                }`}
              >
                <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${accent.dot}`} />
                {p.name}
              </button>
            );
          })}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-1">
        <button type="button" onClick={() => gotoDate(shiftIso(date, -1))} aria-label={t("Previous day")} className={arrowCls}>
          <ChevronLeft aria-hidden className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => setCalOpen((o) => !o)}
          aria-expanded={calOpen}
          aria-controls="day-calendar"
          className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-base font-semibold text-slate-900 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 dark:text-slate-100 dark:hover:bg-slate-800"
        >
          <CalendarDays aria-hidden className="h-4 w-4" />
          <span aria-live="polite">{dateLabel}</span>
        </button>
        <button type="button" onClick={() => gotoDate(shiftIso(date, 1))} aria-label={t("Next day")} className={arrowCls}>
          <ChevronRight aria-hidden className="h-5 w-5" />
        </button>
        <button
          type="button"
          onClick={() => gotoDate(today)}
          disabled={date === today}
          className="ml-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:border-brand-400 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
        >
          {t("Today")}
        </button>
      </div>

      {calOpen && (
      <div id="day-calendar" className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <MonthCalendar
          year={view.year}
          month={view.month}
          onMonthChange={(year, month) => setView({ year, month })}
          onDayClick={(iso) => {
            gotoDate(iso);
            setCalOpen(false);
          }}
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
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-600 dark:text-slate-300">
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
        </div>
      </div>
      )}

      {stats && (
        <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <Tile label={t("Pickups")} value={doneOf(stats.pickups)} to="#pickups" />
          <Tile label={t("Returns")} value={doneOf(stats.returns)} to="#returns" />
          <Tile
            label={t("Overdue")}
            value={stats.overdue}
            to="#overdue"
            highlight={stats.overdue > 0}
            detail={stats.overdue > 0 ? t("needs attention") : undefined}
          />
          <Tile label={t("To confirm")} value={stats.to_confirm} to="/manage/confirm" />
          <Tile label={t("Currently lent out")} value={stats.lent_out} to="#returns" />
        </div>
      )}

      {overview.loading && <Loading />}
      {overview.error && <ErrorBox message={overview.error} />}

      {overview.data &&
        SECTIONS.map((section) => {
          const items = overview.data![section.key] as ManagedBooking[];
          if (!items || items.length === 0) return null;
          return (
            <section key={section.key} id={section.key} className="mb-6 scroll-mt-4">
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
        <p className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Nothing for this day.")}</p>
      )}
    </div>
  );
}
