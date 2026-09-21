// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Heart, X } from "lucide-react";
import { api } from "../api";
import { useCart } from "../cart";
import { useFetch } from "../useFetch";
import { useAuth } from "../auth";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { symbolFor } from "../emoji";
import { todayIso } from "../manage";
import type { ProductBrief } from "../types";

// Whole hours only — favorites don't need minute precision.
const HOURS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);

type Status =
  | { state: "available"; available: number; total: number }
  | { state: "partial"; daysFree: number; daysTotal: number }
  | { state: "unavailable" }
  | { state: "loading" }
  | { state: "error" };

export function FavoritesPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const favorites = useFetch<ProductBrief[]>(() => api.getFavorites(), [version]);

  if (user && !user.authenticated) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">
        {t("Please sign in to use favorites.")}
      </div>
    );
  }

  const items = favorites.data ?? [];
  const daily = items.filter((p) => p.lending_type === "days");
  const hourly = items.filter((p) => p.lending_type === "hours");

  function removeFavorite(id: number) {
    api.removeFavorite(id).then(() => setVersion((v) => v + 1));
  }

  return (
    <div className="pb-10">
      <h1 className="mb-1 flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-slate-100">
        <Heart aria-hidden className="h-5 w-5 fill-current text-rose-500" />
        {t("Favorites")}
      </h1>
      <p className="mb-5 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
        {t(
          "Mark the products you want, choose a period, and see whether they're available before reserving.",
        )}
      </p>

      {favorites.loading && <Loading />}
      {favorites.error && <ErrorBox message={favorites.error} />}

      {favorites.data && items.length === 0 && (
        <Empty
          label={t("No favorites yet. Add products with the ♥ button on a product page.")}
        />
      )}

      {daily.length > 0 && (
        <FavoriteSection mode="days" products={daily} onRemove={removeFavorite} />
      )}
      {hourly.length > 0 && (
        <FavoriteSection mode="hours" products={hourly} onRemove={removeFavorite} />
      )}
    </div>
  );
}

function FavoriteSection({
  mode,
  products,
  onRemove,
}: {
  mode: "days" | "hours";
  products: ProductBrief[];
  onRemove: (id: number) => void;
}) {
  const { t } = useTranslation();
  const { add } = useCart();
  const today = todayIso();

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [time, setTime] = useState({ from: "09:00", to: "12:00" });
  const [statuses, setStatuses] = useState<Record<number, Status>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const reqRef = useRef(0);

  // A valid, bookable period for this section.
  const period: { start: string; end: string } | null = (() => {
    if (mode === "days") {
      if (!startDate || !endDate || endDate < startDate) return null;
      return { start: startDate, end: endDate };
    }
    if (!startDate || !time.from || !time.to || time.to <= time.from) return null;
    return { start: `${startDate}T${time.from}`, end: `${startDate}T${time.to}` };
  })();

  const selectedIds = [...selected];

  // Re-check availability whenever the selection or period changes.
  useEffect(() => {
    if (!period || selectedIds.length === 0) {
      setStatuses({});
      return;
    }
    const token = ++reqRef.current;
    setStatuses(Object.fromEntries(selectedIds.map((id) => [id, { state: "loading" }])));
    Promise.all(
      selectedIds.map(async (id): Promise<[number, Status]> => {
        try {
          const whole = await api.getAvailability(id, period.start, period.end);
          if (whole.available >= 1)
            return [id, { state: "available", available: whole.available, total: whole.total }];
          if (mode === "days" && endDate > startDate) {
            // The calendar's `to` is exclusive — add a day so the last day counts.
            const toExclusive = new Date(`${endDate}T00:00:00`);
            toExclusive.setDate(toExclusive.getDate() + 1);
            const cal = await api.getAvailabilityCalendar(
              id,
              startDate,
              toExclusive.toISOString().slice(0, 10),
            );
            const free = cal.days.filter((d) => !d.closed && d.available > 0).length;
            if (free > 0)
              return [id, { state: "partial", daysFree: free, daysTotal: cal.days.length }];
          }
          return [id, { state: "unavailable" }];
        } catch {
          return [id, { state: "error" }];
        }
      }),
    ).then((entries) => {
      if (token === reqRef.current) setStatuses(Object.fromEntries(entries));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period?.start, period?.end, selectedIds.join(",")]);

  function toggle(id: number) {
    setMessage(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allAvailable =
    selectedIds.length > 0 &&
    selectedIds.every((id) => statuses[id]?.state === "available");

  async function addToCart() {
    if (!period) return;
    setBusy(true);
    setMessage(null);
    try {
      for (const id of selectedIds) await add(id, period.start, period.end);
      setMessage(t("Added {{count}} product(s) to the cart.", { count: selectedIds.length }));
      setSelected(new Set());
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t("Could not add to the cart."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mb-6 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {mode === "days" ? t("Daily rental") : t("Hourly rental")}
      </h2>

      {/* Period picker */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        {mode === "days" ? (
          <>
            <label className="text-xs text-slate-500 dark:text-slate-400">
              {t("From")}
              <input
                type="date"
                min={today}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
            <label className="text-xs text-slate-500 dark:text-slate-400">
              {t("Until")}
              <input
                type="date"
                min={startDate || today}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
          </>
        ) : (
          <>
            <label className="text-xs text-slate-500 dark:text-slate-400">
              {t("Day")}
              <input
                type="date"
                min={today}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
            <label className="text-xs text-slate-500 dark:text-slate-400">
              {t("From")}
              <select
                value={time.from}
                onChange={(e) => setTime((s) => ({ ...s, from: e.target.value }))}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                {HOURS.map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-slate-500 dark:text-slate-400">
              {t("Until")}
              <select
                value={time.to}
                onChange={(e) => setTime((s) => ({ ...s, to: e.target.value }))}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                {HOURS.map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>

      {/* Product list */}
      <ul className="space-y-1">
        {products.map((p) => {
          const checked = selected.has(p.id);
          const status = checked ? statuses[p.id] : undefined;
          return (
            <li
              key={p.id}
              className="flex items-center gap-3 rounded-lg border border-slate-100 p-2 dark:border-slate-800"
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(p.id)}
                aria-label={t("Select {{title}}", { title: p.title })}
                className="h-4 w-4 shrink-0"
              />
              <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-slate-100 text-lg dark:bg-slate-800">
                {p.image ? (
                  <img src={p.image} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span aria-hidden>{symbolFor(p.title)}</span>
                )}
              </div>
              <Link
                to={`/products/${p.id}`}
                className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900 hover:underline dark:text-slate-100"
              >
                {p.title}
              </Link>
              {status && <StatusBadge status={status} />}
              <button
                type="button"
                onClick={() => onRemove(p.id)}
                aria-label={t("Remove from favorites")}
                title={t("Remove from favorites")}
                className="shrink-0 rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800"
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={addToCart}
          disabled={busy || !period || !allAvailable}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {t("Reserve — add to cart")}
        </button>
        {selectedIds.length > 0 && !period && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {t("Choose a period to check availability.")}
          </span>
        )}
        {message && (
          <span className="text-sm text-slate-600 dark:text-slate-300">{message}</span>
        )}
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: Status }) {
  const { t } = useTranslation();
  const base = "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium";
  switch (status.state) {
    case "loading":
      return <span className={`${base} text-slate-400 dark:text-slate-400`}>{t("checking…")}</span>;
    case "available":
      return (
        <span className={`${base} bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300`}>
          {t("available")}
        </span>
      );
    case "partial":
      return (
        <span
          className={`${base} bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300`}
          title={t("Free on {{free}} of {{total}} days", {
            free: status.daysFree,
            total: status.daysTotal,
          })}
        >
          {t("only partly ({{free}}/{{total}} days)", {
            free: status.daysFree,
            total: status.daysTotal,
          })}
        </span>
      );
    case "unavailable":
      return (
        <span className={`${base} bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300`}>
          {t("unavailable")}
        </span>
      );
    default:
      return <span className={`${base} text-slate-400`}>{t("error")}</span>;
  }
}
