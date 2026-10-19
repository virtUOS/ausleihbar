// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { BlockedNotice } from "../components/BlockedNotice";
import { TriangleAlert } from "lucide-react";
import { Empty, ErrorBox, Loading } from "../components/Status";
import { ProductCard } from "../components/ProductCard";
import { Tile } from "../components/Tile";
import { SortToggle, sortAlpha, type SortMode } from "../components/SortToggle";
import { symbolFor } from "../emoji";
import { contentCountLabel } from "../categories";
import type {
  FeaturedProducts,
  PoolCard,
  ProductBrief,
} from "../types";

export function StartPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const sections = useFetch(() => api.listSections(), []);
  const featured = useFetch<FeaturedProducts>(() => api.getFeatured(), []);
  const pools = useFetch<PoolCard[]>(() => api.getShopPools(), []);
  const [sort, setSort] = useState<SortMode>("manual");

  if (sections.loading) return <Loading />;
  if (sections.error) return <ErrorBox message={sections.error} />;

  const sectionList = sections.data?.results ?? [];
  const sortedSections =
    sort === "alpha" ? sortAlpha(sectionList, (s) => s.title) : sectionList;
  const popular = featured.data?.popular ?? [];
  const newest = featured.data?.newest ?? [];
  const poolList = pools.data ?? [];
  // Greet by first name (friendlier than the login username); fall back to the
  // full name, then the username if no real name is on file.
  const greetingName =
    user?.first_name?.trim() ||
    [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim() ||
    user?.username;

  if (
    sectionList.length === 0 &&
    popular.length === 0 &&
    newest.length === 0 &&
    poolList.length === 0
  ) {
    return <Empty label={t("Nothing here yet.")} />;
  }

  return (
    <div className="space-y-12">
      <BlockedNotice />
      {/* Greeting moment: one big friendly headline. The name just inherits the
          headline colour — the honey marker only covered the lower half of the
          glyphs (#3) and clashed with dark mode, so it was dropped. */}
      <header className="pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
          {t("Moin")}
          {greetingName && <>, {greetingName}</>}!
        </h1>
        <p className="mt-2 text-lg text-slate-600 dark:text-slate-300">
          {t("What would you like to borrow today?")}
        </p>
        <MyBookingsSummary />
      </header>

      {sectionList.length > 0 && (
        <section aria-labelledby="sections-heading">
          <div className="mb-4 flex items-baseline justify-between gap-3">
            <h2
              id="sections-heading"
              className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100"
            >
              {t("Browse by section")}
            </h2>
            {sectionList.length > 1 && <SortToggle value={sort} onChange={setSort} />}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {sortedSections.map((section) => (
              <Tile
                key={section.id}
                to={`/sections/${section.id}`}
                imageUrl={section.image}
                imageAspect="aspect-[4/3]"
                fallback={symbolFor(section.title)}
                fallbackBg="bg-slate-100 dark:bg-slate-800"
                title={section.title}
                subtitle={contentCountLabel(t, section.product_count, section.set_count)}
              />
            ))}
          </div>
        </section>
      )}

      {popular.length > 0 && (
        <FeaturedRow title={t("🔥 Popular right now")} products={popular} />
      )}
      {newest.length > 0 && (
        <FeaturedRow title={t("✨ New arrivals")} products={newest} />
      )}

      {poolList.length > 0 && (
        <section aria-labelledby="pools-heading">
          <h2
            id="pools-heading"
            className="mb-4 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100"
          >
            {t("📍 Your pools")}
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {poolList.map((pool) => (
              <Tile
                key={pool.id}
                to={`/pools/${pool.id}`}
                imageUrl={pool.image}
                imageAspect="aspect-video"
                fallback="📍"
                fallbackBg="bg-brand-50 dark:bg-brand-900/30"
                title={pool.name}
                subtitle={pool.room || undefined}
                accentColor={pool.accent_color}
              />
            ))}
          </div>
        </section>
      )}

    </div>
  );
}

/** A compact link to "My bookings" shown under the greeting, summarising how
 *  many bookings are currently active — with a clear empty state (issue #11).
 *  Overdue returns / missed pickups (lending desk rule) turn it red and are
 *  spelled out inside, linking straight to the overdue section (#133). */
function MyBookingsSummary() {
  const { t } = useTranslation();
  const { data, loading, error } = useFetch(
    () => api.myBookingsCurrentCount(),
    [],
  );
  const overdueFetch = useFetch(() => api.myOverdueBookings(), []);
  const current = data?.count ?? 0;
  const overdue = overdueFetch.data ?? [];
  const overdueReturns = overdue.reduce((n, b) => n + (b.overdue?.returns ?? 0), 0);
  const missedPickup = overdue.some((b) => (b.overdue?.pickups ?? 0) > 0);
  const isOverdue = overdueReturns > 0 || missedPickup;

  // On error the count is unknown, so we show the link without a summary line
  // rather than a misleading "no current bookings" (false negative).
  const summary = loading
    ? "…"
    : error
      ? null
      : current > 0
        ? t("{{count}} current booking", { count: current })
        : t("You have no current bookings.");

  return (
    <Link
      to={isOverdue ? "/bookings#overdue" : "/bookings"}
      className={`group mt-5 flex items-center justify-between gap-3 rounded-2xl px-4 py-3 transition-all duration-200 ease-out-quart hover:-translate-y-0.5 hover:shadow-md hover:shadow-slate-900/[0.04] ${
        isOverdue
          ? "border-2 border-red-500 bg-red-50 hover:border-red-600 dark:bg-red-950/40"
          : "border border-slate-200 bg-white hover:border-brand-400 dark:border-slate-800 dark:bg-slate-900"
      }`}
    >
      <div className="min-w-0">
        <p className="font-bold text-slate-900 dark:text-slate-100">
          {t("My bookings")}
        </p>
        {summary !== null && (
          <p className="text-sm text-slate-600 dark:text-slate-300">{summary}</p>
        )}
        {isOverdue && (
          <div className="mt-2 flex items-start gap-2 text-sm text-red-800 dark:text-red-200">
            <TriangleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              {overdueReturns > 0 && (
                <p className="font-semibold">
                  {t("You have {{count}} overdue item — please return it as soon as possible.", {
                    count: overdueReturns,
                  })}
                </p>
              )}
              {missedPickup && (
                <p className={overdueReturns > 0 ? "" : "font-semibold"}>
                  {t("You missed a pickup — please contact the lending team.")}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
      <span
        aria-hidden
        className="shrink-0 text-slate-300 transition-all duration-150 ease-out-quart group-hover:translate-x-0.5 group-hover:text-brand-600 dark:text-slate-300"
      >
        ›
      </span>
    </Link>
  );
}

function FeaturedRow({ title, products }: { title: string; products: ProductBrief[] }) {
  return (
    <section>
      <h2 className="mb-4 text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">{title}</h2>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {products.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}
