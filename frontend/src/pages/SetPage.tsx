// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useCart } from "../cart";
import { useFetch } from "../useFetch";
import { BookingCalendar } from "../components/BookingCalendar";
import { HourlyBookingCalendar } from "../components/HourlyBookingCalendar";
import { Breadcrumbs, useParentCrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { symbolFor } from "../emoji";
import type { SetDetail } from "../types";

export function SetPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const parents = useParentCrumbs();
  const { addSet } = useCart();

  const setFetch = useFetch<SetDetail>(() => api.getSet(id!), [id]);
  const set = setFetch.data;

  if (setFetch.loading) return <Loading />;
  if (setFetch.error) return <ErrorBox message={setFetch.error} />;
  if (!set) return <Empty label={t("Set not found.")} />;

  const hourly = set.lending_type === "hours";
  // Trail to carry to products opened from this set.
  const childCrumbs: Crumb[] = [
    ...parents,
    { label: set.name, to: `/sets/${set.id}` },
  ];

  // The set books all its products together; the calendar drives the booking.
  async function onAddSet(start: string, end: string) {
    await addSet(set!.id, start, end);
  }

  return (
    <div className="pb-10">
      <Breadcrumbs items={[...parents, { label: set.name }]} />

      <h1 className="mt-2 text-xl font-bold text-slate-900 dark:text-slate-100">{set.name} 🎒</h1>
      {set.description && <p className="mt-1 text-slate-700 dark:text-slate-200">{set.description}</p>}
      {set.pool && (
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          {t("Available from")} <span className="font-medium text-slate-700 dark:text-slate-200">{set.pool.name}</span>
          {set.pool.room ? ` · ${set.pool.room}` : ""}
        </p>
      )}

      <h2 className="mb-2 mt-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Products in this set")}
      </h2>
      <ul className="space-y-2">
        {set.products.map((p) => (
          <li key={p.id}>
            <Link
              to={`/products/${p.id}`}
              state={{ crumbs: childCrumbs }}
              className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 active:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:active:bg-slate-800"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-slate-100 text-lg dark:bg-slate-800">
                {p.image ? (
                  <img src={p.image} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span aria-hidden>{symbolFor(p.title)}</span>
                )}
              </div>
              <span className="font-medium text-slate-900 dark:text-slate-100">{p.title}</span>
              <span className="ml-auto text-slate-300 dark:text-slate-300">›</span>
            </Link>
          </li>
        ))}
      </ul>

      {set.max_duration && (
        <p className="mt-3 text-xs text-slate-400 dark:text-slate-300">
          {hourly
            ? t("Max booking duration: {{count}} hours (set by the most limited product). Availability follows the scarcest product.", { count: set.max_duration })
            : t("Max booking duration: {{count}} days (set by the most limited product). Availability follows the scarcest product.", { count: set.max_duration })}
        </p>
      )}

      {!set.pool ? (
        <p className="mt-5 rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          {t("This set can’t be booked right now — it isn’t assigned to a pool you can access.")}
        </p>
      ) : hourly ? (
        <HourlyBookingCalendar
          fetchCalendar={(from, to) => api.getSetHourlyCalendar(set.id, from, to)}
          fetchDay={(date) => api.getSetHourlyAvailability(set.id, date)}
          onAdd={onAddSet}
          reloadKey={`set${set.id}`}
          addedText={t("Added to cart: {{title}}", { title: set.name })}
        />
      ) : (
        <BookingCalendar
          fetchCalendar={(from, to) => api.getSetCalendar(set.id, from, to)}
          onAdd={onAddSet}
          reloadKey={`set${set.id}`}
          maxDuration={set.max_duration}
          addedText={t("Added to cart: {{title}}", { title: set.name })}
        />
      )}
    </div>
  );
}
