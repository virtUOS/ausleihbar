// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { useStartDate } from "../startDate";
import { Breadcrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { ProductCard } from "../components/ProductCard";
import type { CategoryGroup } from "../types";

type AvailabilityMap = Record<string, { available: number; total: number }>;

/** A category shown with its products — used for matched categories and inside
 *  matched sections, so a name search surfaces the grouping and its content.
 *  The header links to the category page; a matched subcategory shows its
 *  path ("Kameras › Video") so same-named categories stay distinguishable. */
function CategoryBlock({
  category,
  path = [],
  headingLevel,
  availabilityMap,
  startDate,
  crumbs,
}: {
  category: CategoryGroup;
  path?: { id: number; name: string }[];
  headingLevel: 3 | 4;
  availabilityMap: AvailabilityMap;
  startDate: string | null;
  crumbs: Crumb[];
}) {
  const { t } = useTranslation();
  const Heading = `h${headingLevel}` as const;
  return (
    <details open className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 text-slate-900 dark:text-slate-100">
        <Heading className="min-w-0 text-base font-semibold">
          {path.length > 0 && (
            <span className="block truncate text-xs font-normal text-slate-600 dark:text-slate-300">
              {path.map((a) => a.name).join(" › ")} ›
            </span>
          )}
          <Link
            to={`/categories/${category.id}`}
            className="group inline-flex items-center gap-1 rounded hover:text-brand-700 hover:underline dark:hover:text-brand-300"
          >
            {category.name}
            <ChevronRight
              aria-hidden
              className="h-4 w-4 shrink-0 text-slate-400 transition-transform duration-150 ease-out-quart group-hover:translate-x-0.5 dark:text-slate-300"
            />
          </Link>
        </Heading>
        <span className="shrink-0 text-xs font-normal text-slate-600 dark:text-slate-300">
          {category.product_count}
        </span>
      </summary>
      <div className="space-y-2 px-3 pb-3">
        {category.products.length === 0 && (
          <p className="px-1 py-2 text-sm text-slate-400 dark:text-slate-300">{t("No products found.")}</p>
        )}
        {category.products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            availability={startDate ? availabilityMap[String(product.id)] : undefined}
            crumbs={crumbs}
          />
        ))}
      </div>
    </details>
  );
}

export function SearchPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const query = params.get("q") ?? "";
  const childCrumbs: Crumb[] = [
    { label: t("Search"), to: `/search?q=${encodeURIComponent(query)}` },
  ];
  const { startDate } = useStartDate();
  const { data, loading, error } = useFetch(() => api.search(query), [query]);

  // All product ids across loose products, matched categories and matched
  // sections — so the start-date availability overlay works everywhere.
  const productIds = useMemo(() => {
    const ids = new Set<number>();
    data?.products.forEach((p) => ids.add(p.id));
    data?.categories.forEach((c) => c.products.forEach((p) => ids.add(p.id)));
    data?.sections.forEach((s) =>
      s.categories.forEach((c) => c.products.forEach((p) => ids.add(p.id))),
    );
    return [...ids];
  }, [data]);

  const availabilityFetch = useFetch(
    () =>
      startDate && productIds.length
        ? api.getBulkAvailability(startDate, productIds)
        : Promise.resolve(null),
    [startDate, productIds.join(",")],
  );
  const availabilityMap = availabilityFetch.data?.availability ?? {};

  const isEmpty =
    data &&
    data.sections.length === 0 &&
    data.categories.length === 0 &&
    data.products.length === 0;

  return (
    <div>
      <Breadcrumbs items={[{ label: t("Search: “{{query}}”", { query }) }]} />
      <h1 className="mb-4 text-xl font-bold text-slate-900 dark:text-slate-100">
        {t("Results for “{{query}}”", { query })}
      </h1>
      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {isEmpty && <Empty label={t("No results found.")} />}

      {data && data.sections.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{t("Sections")}</h2>
          <div className="space-y-4">
            {data.sections.map((section) => (
              <div key={section.id}>
                <h3 className="mb-2">
                  <Link
                    to={`/sections/${section.id}`}
                    className="inline-block font-semibold text-slate-900 hover:underline dark:text-slate-100"
                  >
                    {section.title} ›
                  </Link>
                </h3>
                <div className="space-y-3">
                  {section.categories.map((category) => (
                    <CategoryBlock
                      key={category.id}
                      category={category}
                      headingLevel={4}
                      availabilityMap={availabilityMap}
                      startDate={startDate}
                      crumbs={childCrumbs}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data && data.categories.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{t("Categories")}</h2>
          <div className="space-y-3">
            {data.categories.map((category) => (
              <CategoryBlock
                key={category.id}
                category={category}
                path={category.path}
                headingLevel={3}
                availabilityMap={availabilityMap}
                startDate={startDate}
                crumbs={childCrumbs}
              />
            ))}
          </div>
        </section>
      )}

      {data && data.products.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{t("Products")}</h2>
          <div className="space-y-2">
            {data.products.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                availability={startDate ? availabilityMap[String(product.id)] : undefined}
                crumbs={childCrumbs}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
