// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { useStartDate } from "../startDate";
import { Breadcrumbs, useParentCrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { LendingTypeSections } from "../components/LendingTypeSections";
import { ProductCard } from "../components/ProductCard";
import { SortToggle, sortAlpha, type SortMode } from "../components/SortToggle";

export function SectionPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { startDate } = useStartDate();
  const { data, loading, error } = useFetch(() => api.getSection(id!), [id]);
  const [sort, setSort] = useState<SortMode>("manual");
  const parents = useParentCrumbs();

  const productIds = useMemo(() => {
    const ids = new Set<number>();
    data?.categories.forEach((c) => c.products.forEach((p) => ids.add(p.id)));
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

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Empty label={t("Section not found.")} />;

  // One group per top-level category (#78), each listing its whole subtree.
  // Categories without a visible product are hidden (borrowers never get
  // them; lenders/admins do, but an empty group is no use in the shop).
  const shownCategories = data.categories.filter((c) => c.products.length > 0);
  const displayCategories =
    sort === "alpha" ? sortAlpha(shownCategories, (c) => c.name) : shownCategories;
  // Trail to carry to categories, products and sets opened from this section.
  const childCrumbs: Crumb[] = [
    ...parents,
    { label: data.title, to: `/sections/${data.id}` },
  ];

  return (
    <div>
      <Breadcrumbs items={[...parents, { label: data.title }]} />
      <div className="mb-1 flex items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">{data.title}</h1>
        {shownCategories.length > 0 && (
          <SortToggle value={sort} onChange={setSort} />
        )}
      </div>
      {data.description && <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{data.description}</p>}

      {shownCategories.length === 0 && data.sets.length === 0 && (
        <Empty label={t("No categories in this section.")} />
      )}

      {/* Quick-nav: jump to a category without scrolling the whole page. Sticks
          just under the app header so it stays reachable while browsing. */}
      {displayCategories.length > 1 && (
        <nav className="sticky top-16 z-10 -mx-4 mb-4 border-b border-slate-100 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 px-4 py-2 backdrop-blur">
          <div className="flex flex-wrap gap-1.5">
            {displayCategories.map((c) => (
              <a
                key={c.id}
                href={`#category-${c.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  document
                    .getElementById(`category-${c.id}`)
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  window.history.replaceState(null, "", `#category-${c.id}`);
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 dark:border-slate-800 px-3 py-1 text-sm text-slate-700 dark:text-slate-200 transition-colors duration-150 hover:border-brand-400 hover:bg-brand-50 dark:hover:bg-brand-900/30"
              >
                {c.name}
                <span className="text-xs font-semibold text-slate-400 dark:text-slate-300">{c.product_count}</span>
              </a>
            ))}
          </div>
        </nav>
      )}

      <div className="space-y-3">
        {displayCategories.map((category) => {
          const products =
            sort === "alpha"
              ? sortAlpha(category.products, (p) => p.title)
              : category.products;
          return (
          <details
            key={category.id}
            id={`category-${category.id}`}
            open
            className="scroll-mt-28 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
          >
            <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 font-semibold text-slate-900 dark:text-slate-100">
              {/* The header names the category and opens its own page (its
                  subcategories + every product of the subtree). */}
              <h2 className="min-w-0 text-base font-semibold">
                <Link
                  to={`/categories/${category.id}`}
                  state={{ crumbs: childCrumbs }}
                  className="group inline-flex items-center gap-1 rounded hover:text-brand-700 hover:underline dark:hover:text-brand-300"
                >
                  {category.name}
                  <ChevronRight
                    aria-hidden
                    className="h-4 w-4 shrink-0 text-slate-400 transition-transform duration-150 ease-out-quart group-hover:translate-x-0.5 dark:text-slate-300"
                  />
                </Link>
              </h2>
              <span className="shrink-0 text-xs font-normal text-slate-600 dark:text-slate-300">
                {category.product_count}
              </span>
            </summary>
            <div className="px-3 pb-3">
              <LendingTypeSections
                products={products}
                headingLevel={3}
                renderProducts={(list) => (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {list.map((product) => (
                      <ProductCard
                        key={product.id}
                        product={product}
                        availability={startDate ? availabilityMap[String(product.id)] : undefined}
                        crumbs={childCrumbs}
                      />
                    ))}
                  </div>
                )}
              />
            </div>
          </details>
          );
        })}
      </div>

      {data.sets.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("🎒 Sets")}</h2>
          <div className="grid grid-cols-2 gap-2">
            {data.sets.map((set) => (
              <Link
                key={set.id}
                to={`/sets/${set.id}`}
                state={{ crumbs: childCrumbs }}
                className="group flex items-center gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 transition-all duration-200 ease-out-quart hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md hover:shadow-slate-900/[0.04] active:bg-brand-50 dark:active:bg-brand-900/30"
              >
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-50 dark:bg-brand-900/30 text-xl">
                  🎒
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-medium text-slate-900 dark:text-slate-100">
                    {set.name}
                  </span>
                  <span className="text-xs text-slate-600 dark:text-slate-300">
                    {t("{{count}} product", { count: set.product_count })}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
