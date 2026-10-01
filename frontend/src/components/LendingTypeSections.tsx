// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { CalendarDays, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ProductBrief } from "../types";

/** Daily products first, then hourly (#19). Stable, so any incoming order
 *  (curated or alphabetical) is kept inside each half. */
export function splitByLendingType(products: ProductBrief[]) {
  return {
    daily: products.filter((p) => p.lending_type !== "hours"),
    hourly: products.filter((p) => p.lending_type === "hours"),
  };
}

/** Renders a product list as a daily section followed by an hourly section.
 *  Sub-headings appear only when both kinds are present. */
export function LendingTypeSections({
  products,
  renderProducts,
}: {
  products: ProductBrief[];
  renderProducts: (products: ProductBrief[]) => ReactNode;
}) {
  const { t } = useTranslation();
  const { daily, hourly } = splitByLendingType(products);
  const both = daily.length > 0 && hourly.length > 0;
  const part = (items: ProductBrief[], type: "days" | "hours") =>
    items.length > 0 && (
      <div>
        {both && (
          <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
            {type === "hours" ? (
              <Clock aria-hidden className="h-3.5 w-3.5" />
            ) : (
              <CalendarDays aria-hidden className="h-3.5 w-3.5" />
            )}
            {type === "hours" ? t("Hourly lending") : t("Daily lending")}
          </h4>
        )}
        {renderProducts(items)}
      </div>
    );
  return (
    <div className="space-y-3">
      {part(daily, "days")}
      {part(hourly, "hours")}
    </div>
  );
}
