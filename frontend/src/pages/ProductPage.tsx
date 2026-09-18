// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, mediaUrl } from "../api";
import { useFetch } from "../useFetch";
import { Breadcrumbs, useParentCrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { BookingCalendar } from "../components/BookingCalendar";
import { HourlyBookingCalendar } from "../components/HourlyBookingCalendar";
import { ProductGallery } from "../components/ProductGallery";
import { FavoriteButton } from "../components/FavoriteButton";
import { symbolFor } from "../emoji";

export function ProductPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const parents = useParentCrumbs();
  const { data, loading, error } = useFetch(() => api.getProduct(id!), [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Empty label={t("Product not found.")} />;

  // Trail to carry to sets opened from this product.
  const childCrumbs: Crumb[] = [
    ...parents,
    { label: data.title, to: `/products/${data.id}` },
  ];

  // Human-readable max lending duration, reused in the meta grid and next to
  // the booking calendar (issue #21).
  const maxDurationLabel =
    data.effective_max_duration == null
      ? t("Not limited")
      : data.lending_type === "hours"
        ? t("{{count}} hour", { count: data.effective_max_duration })
        : t("{{count}} day", { count: data.effective_max_duration });

  return (
    <div className="pb-10">
      <Breadcrumbs items={[...parents, { label: data.title }]} />

      <ProductGallery
        images={data.images}
        fallback={symbolFor(data.product_type_name, data.title)}
      />

      <div className="mt-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">{data.title}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{data.product_type_name}</p>
        </div>
        <FavoriteButton productId={data.id} initial={data.is_favorite} />
      </div>

      {data.description && <p className="mt-3 text-slate-700 dark:text-slate-200">{data.description}</p>}

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50">
          <dt className="text-slate-500 dark:text-slate-400">{t("Lending type")}</dt>
          <dd className="font-medium text-slate-900 dark:text-slate-100">
            {data.lending_type === "hours" ? t("Hourly") : t("Daily")}
          </dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50">
          <dt className="text-slate-500 dark:text-slate-400">{t("Maximum lending duration")}</dt>
          <dd className="font-medium text-slate-900 dark:text-slate-100">
            {maxDurationLabel}
          </dd>
        </div>
      </dl>

      {data.visible_attributes.length > 0 && (
        <section className="mt-5">
          <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Details")}</h2>
          <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {data.visible_attributes.map((attr) => (
              <div key={attr.key} className="flex justify-between gap-4 px-3 py-2 text-sm">
                <dt className="text-slate-500 dark:text-slate-400">{attr.label}</dt>
                <dd className="text-right font-medium text-slate-900 dark:text-slate-100">
                  {attr.type === "pdf" ? (
                    attr.value ? (
                      <a
                        href={mediaUrl(String(attr.value))}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-900 underline underline-offset-2 dark:text-slate-100"
                      >
                        📄 {t("Open PDF")}
                      </a>
                    ) : (
                      "–"
                    )
                  ) : (
                    String(attr.value ?? "–")
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="mt-5">
        <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Available at")}</h2>
        {data.pools.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">{t("No pools yet.")}</p>
        ) : (
          <ul className="space-y-2">
            {data.pools.map((pool) => (
              <li key={pool.id} className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
                <p className="font-medium text-slate-900 dark:text-slate-100">
                  {pool.name}
                  {pool.room && <span className="text-slate-500 dark:text-slate-400"> · {pool.room}</span>}
                  {pool.lead_time_hours > 0 && (
                    <span className="text-slate-500 dark:text-slate-400">
                      {" "}
                      · {t("book ≥{{n}}h in advance", { n: pool.lead_time_hours })}
                    </span>
                  )}
                </p>
                {pool.address && (
                  <p className="whitespace-pre-line text-slate-500 dark:text-slate-400">{pool.address}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.sets.length > 0 && (
        <section className="mt-5">
          <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Part of sets")}</h2>
          <ul className="flex flex-wrap gap-2">
            {data.sets.map((set) => (
              <li key={set.id}>
                <Link
                  to={`/sets/${set.id}`}
                  state={{ crumbs: childCrumbs }}
                  className="rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  🎒 {set.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-5">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {t("Availability")}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t("Maximum lending duration")}:{" "}
            <span className="font-medium text-slate-700 dark:text-slate-200">
              {maxDurationLabel}
            </span>
          </p>
        </div>
        {data.lending_type === "hours" ? (
          <HourlyBookingCalendar
            productId={data.id}
            addedText={t("Added to cart: {{title}}", { title: data.title })}
          />
        ) : (
          <BookingCalendar
            productId={data.id}
            maxDuration={data.effective_max_duration}
            addedText={t("Added to cart: {{title}}", { title: data.title })}
          />
        )}
      </section>
    </div>
  );
}
