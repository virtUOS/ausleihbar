// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { useCart } from "../cart";
import { poolAccent } from "../poolAccent";
import type { PoolAvailability } from "../types";

interface PoolChoiceProps {
  productId: number;
  start: string | null;
  end: string | null;
  value: number | undefined;
  onChange: (poolId: number) => void;
  onAvailabilityChange?: (hasAvailable: boolean) => void;
}

/** Pick-up pool selection shown AFTER a date/hour range is chosen (#10): the
 *  borrower sees which pools have the product free for that exact selection and
 *  picks one. Available pools are selectable; pools the product lives in but has
 *  no free unit for this selection are shown disabled. Preselects a pool the
 *  cart already uses, else the most-available, else the first in pool order. */
export function PoolChoice({
  productId,
  start,
  end,
  value,
  onChange,
  onAvailabilityChange,
}: PoolChoiceProps) {
  const { t } = useTranslation();
  const { cart } = useCart();

  const { data, loading } = useFetch<{ pools: PoolAvailability[] }>(
    () =>
      start
        ? api.getPoolAvailability(productId, start, end ?? start)
        : Promise.resolve({ pools: [] }),
    [productId, start, end],
  );

  const pools = useMemo(() => data?.pools ?? [], [data]);
  const available = useMemo(() => pools.filter((p) => p.available > 0), [pools]);
  const cartPoolIds = useMemo(
    () => new Set((cart?.groups ?? []).map((g) => g.pool_id)),
    [cart],
  );

  // Preselect when the available set changes. Keep the current pick if it is
  // still available; otherwise apply the rules. Track the last selection key so
  // we recompute per selection, not on every render.
  const lastKey = useRef<string>("");
  useEffect(() => {
    onAvailabilityChange?.(available.length > 0);
    const key = `${productId}|${start}|${end}`;
    const stillValid = value != null && available.some((p) => p.pool_id === value);
    if (key === lastKey.current && stillValid) return;
    lastKey.current = key;
    if (available.length === 0) return;
    if (stillValid) return;
    const fromCart = available.find((p) => cartPoolIds.has(p.pool_id));
    const mostFree = [...available].sort((a, b) => b.available - a.available)[0];
    // available is position-ordered from the endpoint, so ties fall to the
    // earliest; sort() is stable in modern engines, preserving that order.
    onChange((fromCart ?? mostFree).pool_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [available, productId, start, end]);

  if (!start) return null;
  if (loading && pools.length === 0) {
    return <p className="mt-3 text-xs text-slate-600 dark:text-slate-300">{t("Checking pools…")}</p>;
  }
  if (pools.length === 0) return null;

  return (
    <div className="mt-4">
      <p className="mb-1.5 text-sm font-medium text-slate-900 dark:text-slate-100">
        {t("Pick-up location")}
      </p>
      {available.length === 0 && (
        <p className="mb-2 text-sm text-red-600 dark:text-red-400">
          {t("Not available in any single pool for this selection.")}
        </p>
      )}
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("Pick-up location")}>
        {pools.map((pool) => {
          const free = pool.available > 0;
          const active = value === pool.pool_id;
          const accent = poolAccent(pool.accent_color);
          return (
            <button
              key={pool.pool_id}
              type="button"
              disabled={!free}
              aria-pressed={active}
              onClick={() => onChange(pool.pool_id)}
              title={free ? undefined : t("Not available for this selection")}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                !free
                  ? "cursor-not-allowed border-slate-100 text-slate-300 dark:border-slate-800 dark:text-slate-600"
                  : active
                    ? "border-brand-400 bg-brand-50 text-slate-900 dark:border-brand-500/60 dark:bg-brand-500/10 dark:text-slate-100"
                    : "border-slate-200 text-slate-700 hover:border-slate-300 dark:border-slate-700 dark:text-slate-200"
              }`}
            >
              <span aria-hidden className={`h-2 w-2 rounded-full ${accent.dot}`} />
              {pool.name}
              <span className={`text-xs font-bold ${free ? "text-green-700 dark:text-green-300" : ""}`}>
                {free
                  ? t("{{count}} free", { count: pool.available })
                  : t("none")}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
