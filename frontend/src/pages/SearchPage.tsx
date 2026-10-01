// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { useStartDate } from "../startDate";
import { Breadcrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { ProductCard } from "../components/ProductCard";
import type { ProductTypeWithProducts } from "../types";

type AvailabilityMap = Record<string, { available: number; total: number }>;

/** A product type shown with its products — used for matched product types and inside
 *  matched sections, so a name search surfaces the grouping and its content. */
function ProductTypeBlock({
  productType,
  availabilityMap,
  startDate,
  crumbs,
}: {
  productType: ProductTypeWithProducts;
  availabilityMap: AvailabilityMap;
  startDate: string | null;
  crumbs: Crumb[];
}) {
  const { t } = useTranslation();
  return (
    <details open className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <summary className="flex cursor-pointer items-center justify-between px-4 py-3 font-semibold text-slate-900 dark:text-slate-100">
        <span>{productType.name}</span>
        <span className="text-xs font-normal text-slate-600 dark:text-slate-300">
          {productType.product_count}
        </span>
      </summary>
      <div className="space-y-2 px-3 pb-3">
        {productType.products.length === 0 && (
          <p className="px-1 py-2 text-sm text-slate-400 dark:text-slate-300">{t("No products found.")}</p>
        )}
        {productType.products.map((product) => (
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

  // All product ids across loose products, matched product types and matched
  // sections — so the start-date availability overlay works everywhere.
  const productIds = useMemo(() => {
    const ids = new Set<number>();
    data?.products.forEach((p) => ids.add(p.id));
    data?.product_types.forEach((c) => c.products.forEach((p) => ids.add(p.id)));
    data?.sections.forEach((s) =>
      s.product_types.forEach((c) => c.products.forEach((p) => ids.add(p.id))),
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
    data.product_types.length === 0 &&
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
                <Link
                  to={`/sections/${section.id}`}
                  className="mb-2 inline-block font-semibold text-slate-900 hover:underline dark:text-slate-100"
                >
                  {section.title} ›
                </Link>
                <div className="space-y-3">
                  {section.product_types.map((productType) => (
                    <ProductTypeBlock
                      key={productType.id}
                      productType={productType}
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

      {data && data.product_types.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{t("Product types")}</h2>
          <div className="space-y-3">
            {data.product_types.map((productType) => (
              <ProductTypeBlock
                key={productType.id}
                productType={productType}
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
