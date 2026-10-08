// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useFetch } from "../useFetch";
import { useStartDate } from "../startDate";
import { Breadcrumbs, useParentCrumbs, type Crumb } from "../components/Breadcrumbs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { LendingTypeSections } from "../components/LendingTypeSections";
import { ProductCard } from "../components/ProductCard";
import { SortToggle, sortAlpha, type SortMode } from "../components/SortToggle";
import { SubcategoryChips } from "../components/SubcategoryChips";
import { Tile } from "../components/Tile";
import { symbolFor } from "../emoji";
import type { CategoryDetail } from "../types";

const SECTION_PATH = /^\/sections\/(\d+)$/;

/**
 * The trail above a category: Section › ancestors. The section is the one the
 * user came from (the last section crumb in router state, kept with whatever
 * preceded it) when it is one of the root category's sections; otherwise the
 * root category's first section. Ancestors always come from the API, so a deep
 * link, a search hit and a click-through all show the same category path.
 */
function categoryParentCrumbs(parents: Crumb[], data: CategoryDetail): Crumb[] {
  const sectionIds = new Set(data.sections.map((s) => s.id));
  let sectionTrail: Crumb[] = [];
  for (let i = parents.length - 1; i >= 0; i--) {
    const match = parents[i].to?.match(SECTION_PATH);
    if (match && sectionIds.has(Number(match[1]))) {
      sectionTrail = parents.slice(0, i + 1);
      break;
    }
  }
  if (sectionTrail.length === 0 && data.sections.length > 0) {
    const first = data.sections[0];
    sectionTrail = [{ label: first.title, to: `/sections/${first.id}` }];
  }
  return [
    ...sectionTrail,
    ...data.ancestors.map((a) => ({ label: a.name, to: `/categories/${a.id}` })),
  ];
}

/** A shop category (#78): its subcategories as tiles, then every product of
 *  the whole subtree (deduplicated, shop order) split by lending type. */
export function CategoryPage() {
  const { id } = useParams();
  // Keyed by id: local state (sort) starts fresh when navigating to another
  // category, e.g. via a subcategory tile or the breadcrumb.
  return <CategoryView key={id} id={id!} />;
}

function CategoryView({ id }: { id: string }) {
  const { t } = useTranslation();
  const { startDate } = useStartDate();
  const parents = useParentCrumbs();
  const [sort, setSort] = useState<SortMode>("manual");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  // Unknown, trashed or (for borrowers) empty categories answer 404 → show a
  // "not found" state rather than a raw request error.
  const { data, loading, error } = useFetch<CategoryDetail | null>(
    () =>
      api.getCategory(id).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }),
    [id],
  );

  const productIds = useMemo(() => data?.products.map((p) => p.id) ?? [], [data]);
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
  if (!data) {
    return (
      <div>
        <Breadcrumbs items={[{ label: t("Category not found.") }]} />
        <Empty label={t("Category not found.")} />
      </div>
    );
  }

  const trail = categoryParentCrumbs(parents, data);
  // Trail carried to subcategories and products opened from here.
  const childCrumbs: Crumb[] = [...trail, { label: data.name, to: `/categories/${data.id}` }];
  const sorted =
    sort === "alpha" ? sortAlpha(data.products, (p) => p.title) : data.products;
  // Subcategory filter from `?f=<childId>`; an unknown child (e.g. after a
  // visibility change) falls back to "All".
  const filterParam = params.get("f");
  const activeChild = filterParam
    ? data.children.find((c) => String(c.id) === filterParam)
    : undefined;
  const activeIds = activeChild ? new Set(activeChild.product_ids) : null;
  const products = activeIds ? sorted.filter((p) => activeIds.has(p.id)) : sorted;
  const selectChild = (childId: number | null) => {
    const out = new URLSearchParams(params);
    if (childId === null) out.delete("f");
    else out.set("f", String(childId));
    // Replace (filtering is no navigation step) and keep the breadcrumb state.
    navigate(
      { search: out.toString(), hash: window.location.hash },
      { replace: true, preventScrollReset: true, state: location.state },
    );
  };

  return (
    <div>
      <Breadcrumbs items={[...trail, { label: data.name }]} />
      <div className="mb-1 flex items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">{data.name}</h1>
        {data.products.length > 1 && <SortToggle value={sort} onChange={setSort} />}
      </div>
      {data.description && (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{data.description}</p>
      )}

      {data.children.length > 0 && (
        <section aria-labelledby="subcategories-heading" className="mb-6 mt-4">
          <h2
            id="subcategories-heading"
            className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100"
          >
            {t("Subcategories")}
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {data.children.map((child) => (
              <Tile
                key={child.id}
                to={`/categories/${child.id}`}
                crumbs={childCrumbs}
                imageUrl={child.image}
                imageAspect="aspect-[4/3]"
                fallback={symbolFor(child.name)}
                fallbackBg="bg-slate-100 dark:bg-slate-800"
                title={child.name}
                subtitle={t("{{count}} product", { count: child.product_count })}
              />
            ))}
          </div>
        </section>
      )}

      {data.products.length === 0 ? (
        <Empty label={t("No products in this category.")} />
      ) : (
        <section aria-labelledby="category-products-heading" className="mt-4">
          <h2
            id="category-products-heading"
            className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100"
          >
            {t("Products")}
            <span className="text-xs font-normal text-slate-600 dark:text-slate-300">
              {activeChild ? activeChild.product_count : data.product_count}
            </span>
          </h2>
          {data.children.length > 0 && (
            <SubcategoryChips
              items={data.children}
              total={data.product_count}
              selected={activeChild?.id ?? null}
              onSelect={selectChild}
              label={t("Filter {{name}} by subcategory", { name: data.name })}
              shownCount={products.length}
              linkState={{ crumbs: childCrumbs }}
            />
          )}
          {products.length === 0 ? (
            <Empty label={t("No products in this category.")} />
          ) : (
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
          )}
        </section>
      )}
    </div>
  );
}
