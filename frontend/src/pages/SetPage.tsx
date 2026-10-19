// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MapPin } from "lucide-react";
import { RichText, isEmptyHtml } from "@basicbar/ui";
import { poolAccent } from "../poolAccent";
import { api } from "../api";
import { useCart } from "../cart";
import { useFetch } from "../useFetch";
import { BlockedNotice } from "../components/BlockedNotice";
import { BookingCalendar } from "../components/BookingCalendar";
import { HourlyBookingCalendar } from "../components/HourlyBookingCalendar";
import { ProductGallery } from "../components/ProductGallery";
import { Breadcrumbs, useParentCrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { symbolFor } from "../emoji";
import type { SetDetail } from "../types";
import { durationRange, limitValue } from "../durations";

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
      <BlockedNotice className="mb-4" />
      <Breadcrumbs items={[...parents, { label: set.name }]} />

      <ProductGallery images={set.images} fallback="🎒" />

      <h1 className="mt-4 text-xl font-bold text-slate-900 dark:text-slate-100">{set.name} 🎒</h1>
      {!isEmptyHtml(set.description) && (
        <div className="mt-1 text-slate-700 dark:text-slate-200">
          <RichText html={set.description} />
        </div>
      )}
      {set.pool && (
        // The set's pool in its accent colour, like the pool cards in the
        // cart and bookings (#37), so the pickup location stands out.
        <div
          className={`mt-3 inline-flex overflow-hidden rounded-xl border text-sm ${poolAccent(set.pool.accent_color).border}`}
        >
          <span aria-hidden className={`w-1.5 shrink-0 ${poolAccent(set.pool.accent_color).bar}`} />
          <p
            className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 py-2 ${poolAccent(set.pool.accent_color).tint}`}
          >
            <MapPin aria-hidden className={`h-4 w-4 shrink-0 ${poolAccent(set.pool.accent_color).text}`} />
            <span className="text-slate-700 dark:text-slate-200">{t("Available in")}</span>
            <Link
              to={`/pools/${set.pool.id}`}
              className="font-semibold text-slate-900 hover:underline dark:text-slate-100"
            >
              {set.pool.name}
            </Link>
            {set.pool.room && <span className="text-slate-600 dark:text-slate-300">· {set.pool.room}</span>}
          </p>
        </div>
      )}

      <h2 className="mb-2 mt-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Products in this set")}
      </h2>
      <ul className="space-y-2">
        {set.items.map(({ product: p, quantity }) => (
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
              <span className="font-medium text-slate-900 dark:text-slate-100">
                <span className="tabular-nums text-slate-600 dark:text-slate-300">
                  {t("{{quantity}} ×", { quantity })}
                </span>{" "}
                {p.title}
              </span>
              <span className="ml-auto text-slate-300 dark:text-slate-300">›</span>
            </Link>
          </li>
        ))}
      </ul>

      {(limitValue(set.min_duration) || limitValue(set.max_duration)) && (
        <p className="mt-3 text-xs text-slate-600 dark:text-slate-300">
          {t(
            "Lending duration: {{range}} (set by the most limited product). Availability follows the scarcest product.",
            { range: durationRange(set.min_duration, set.max_duration, set.lending_type) },
          )}
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
          minDuration={set.min_duration}
          maxDuration={set.max_duration}
          addedText={t("Added to cart: {{title}}", { title: set.name })}
        />
      )}
    </div>
  );
}
