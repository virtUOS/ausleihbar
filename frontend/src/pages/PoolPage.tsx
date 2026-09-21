// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Clock, Mail, MapPin, Phone } from "lucide-react";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { useStartDate } from "../startDate";
import { poolHours, hasHours } from "../pools";
import { Breadcrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { ProductCard } from "../components/ProductCard";
import { SortToggle, sortAlpha, type SortMode } from "../components/SortToggle";
import type { Paginated, PoolDetail, ProductBrief } from "../types";

/** A resource pool: where & when to pick things up (concept §1.5) plus its
 *  bookable stock — reached from the start page, the cart and bookings. */
export function PoolPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { startDate } = useStartDate();
  const [sort, setSort] = useState<SortMode>("manual");
  const [query, setQuery] = useState("");
  const poolFetch = useFetch<PoolDetail>(() => api.getPool(id!), [id]);
  const products = useFetch<Paginated<ProductBrief>>(
    () => api.getPoolProducts(id!),
    [id],
  );

  const pool = poolFetch.data ?? null;
  const items = products.data?.results ?? [];

  const productIds = useMemo(() => items.map((p) => p.id), [items]);
  const availabilityFetch = useFetch(
    () =>
      startDate && productIds.length
        ? api.getBulkAvailability(startDate, productIds)
        : Promise.resolve(null),
    [startDate, productIds.join(",")],
  );
  const availabilityMap = availabilityFetch.data?.availability ?? {};

  if (poolFetch.loading || products.loading) return <Loading />;
  if (poolFetch.error) return <ErrorBox message={poolFetch.error} />;
  if (!pool) return <Empty label={t("Pool not found.")} />;

  // "Available here" is the only place that lists every product in the pool,
  // so let shoppers filter (issue #27) and re-sort it; the full list is loaded
  // up front, so both happen client-side. Default keeps the curated order.
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? items.filter((p) => p.title.toLowerCase().includes(needle))
    : items;
  const displayItems =
    sort === "alpha" ? sortAlpha(filtered, (p) => p.title) : filtered;
  const childCrumbs: Crumb[] = [{ label: pool.name, to: `/pools/${pool.id}` }];
  // Only list the days the pool is actually open — closed days add noise.
  const hours = poolHours(pool.opening_hours, pool.closed_weekdays).filter(
    (d) => !d.closed,
  );
  const showHours = hasHours(pool.opening_hours);

  return (
    <div>
      <Breadcrumbs items={[{ label: pool.name }]} />
      <div className="mb-4 flex items-center gap-4">
        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100 text-3xl dark:bg-slate-800">
          {pool.image ? (
            <img src={pool.image} alt="" className="h-full w-full object-cover" />
          ) : (
            <span aria-hidden>📍</span>
          )}
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{pool.name}</h1>
          {pool.room && <p className="text-sm text-slate-500 dark:text-slate-400">{pool.room}</p>}
        </div>
      </div>
      {pool.description && (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{pool.description}</p>
      )}

      {/* Pickup info: opening hours + how to find and reach the pool. */}
      <div className="mb-6 grid gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/50 sm:grid-cols-2">
        {showHours && (
          <div>
            <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-900 dark:text-slate-100">
              <Clock aria-hidden className="h-4 w-4 text-brand-600" />
              {t("Service times")}
            </h2>
            <dl className="space-y-0.5 text-sm">
              {hours.map((d) => (
                <div key={d.label} className="flex justify-between gap-4">
                  <dt className="text-slate-500 dark:text-slate-400">{d.label}</dt>
                  <dd className="font-medium text-slate-800 dark:text-slate-200">
                    {d.ranges.join(", ")}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="space-y-3 text-sm">
          {pool.address && (
            <div>
              <h2 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-slate-900 dark:text-slate-100">
                <MapPin aria-hidden className="h-4 w-4 text-brand-600" />
                {t("Address")}
              </h2>
              <p className="whitespace-pre-line text-slate-700 dark:text-slate-200">{pool.address}</p>
              {pool.directions && (
                <p className="mt-1 whitespace-pre-line text-slate-500 dark:text-slate-400">{pool.directions}</p>
              )}
            </div>
          )}
          {(pool.phone || pool.email) && (
            <div className="space-y-1">
              {pool.phone && (
                <p className="flex items-center gap-1.5 text-slate-700 dark:text-slate-200">
                  <Phone aria-hidden className="h-4 w-4 text-slate-400 dark:text-slate-400" />
                  <a href={`tel:${pool.phone}`} className="hover:underline">{pool.phone}</a>
                </p>
              )}
              {pool.email && (
                <p className="flex items-center gap-1.5 text-slate-700 dark:text-slate-200">
                  <Mail aria-hidden className="h-4 w-4 text-slate-400 dark:text-slate-400" />
                  <a href={`mailto:${pool.email}`} className="hover:underline">{pool.email}</a>
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Available here")}</h2>
        {items.length > 1 && (
          <div className="flex items-center gap-2">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("Search…")}
              aria-label={t("Search products in this pool")}
              className="min-w-0 flex-1 rounded-full border border-slate-300 bg-slate-50 px-4 py-1.5 text-sm placeholder:text-slate-400 focus:border-slate-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-200 dark:placeholder:text-slate-500 dark:focus:border-slate-500 sm:w-52 sm:flex-none"
            />
            <div className="shrink-0">
              <SortToggle value={sort} onChange={setSort} />
            </div>
          </div>
        )}
      </div>
      {items.length === 0 ? (
        <Empty label={t("No products in this pool.")} />
      ) : displayItems.length === 0 ? (
        <Empty label={t("No products found.")} />
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {displayItems.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              availability={startDate ? availabilityMap[String(product.id)] : undefined}
              crumbs={childCrumbs}
            />
          ))}
        </div>
      )}
    </div>
  );
}
