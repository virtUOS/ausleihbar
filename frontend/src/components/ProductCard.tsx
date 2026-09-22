// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";
import { symbolFor } from "../emoji";
import type { Crumb } from "./Breadcrumbs";
import type { ProductBrief } from "../types";

interface ProductCardProps {
  product: ProductBrief;
  /** Availability for the chosen start date (shown only when a date is set). */
  availability?: { available: number; total: number };
  /** Breadcrumb trail to carry to the product page (parent crumbs). */
  crumbs?: Crumb[];
}

export function ProductCard({ product, availability, crumbs }: ProductCardProps) {
  const { t } = useTranslation();
  return (
    <Link
      to={`/products/${product.id}`}
      state={crumbs ? { crumbs } : undefined}
      className="group flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 transition-all duration-200 ease-out-quart hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md hover:shadow-slate-900/[0.04] active:bg-brand-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-500 dark:active:bg-slate-800"
    >
      <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100 text-2xl dark:bg-slate-800">
        {product.image ? (
          <img src={product.image} alt="" className="h-full w-full object-cover" />
        ) : (
          <span aria-hidden>{symbolFor(product.title)}</span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate font-bold text-slate-900 dark:text-slate-100">{product.title}</p>
          {product.is_new && (
            <span className="shrink-0 rounded-full bg-brand-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand-800 dark:bg-brand-900/40 dark:text-brand-200">
              {t("New")}
            </span>
          )}
        </div>
        {product.short_description && (
          <p className="truncate text-xs text-slate-600 dark:text-slate-300">
            {product.short_description}
          </p>
        )}
        <p className="text-xs text-slate-600 dark:text-slate-300">
          {product.lending_type === "hours" ? t("Hourly lending") : t("Daily lending")}
        </p>
      </div>
      {availability && (
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
            availability.available > 0
              ? "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300"
              : "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300"
          }`}
          title={t("{{available}} of {{total}} available", {
            available: availability.available,
            total: availability.total,
          })}
        >
          {t("{{available}} free", { available: availability.available })}
        </span>
      )}
      <ChevronRight
        aria-hidden
        className="h-4 w-4 shrink-0 text-slate-300 transition-all duration-150 ease-out-quart group-hover:translate-x-0.5 group-hover:text-brand-600 dark:text-slate-300 dark:group-hover:text-brand-400"
      />
    </Link>
  );
}
