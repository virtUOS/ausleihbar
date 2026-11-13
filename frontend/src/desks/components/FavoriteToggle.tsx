// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { Heart } from "lucide-react";

/** Compact heart toggle for a favourite place in list rows (44 px target).
 *  Same symbol and colours as the shop's product `FavoriteButton`. */
export function FavoriteToggle({
  name,
  active,
  onToggle,
}: {
  name: string;
  active: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const label = active
    ? t("Remove {{name}} from favorites", { name })
    : t("Add {{name}} to favorites", { name });
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={label}
      title={label}
      onClick={(e) => {
        // Inside clickable rows (labels): only toggle the favourite.
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors duration-150 ${
        active
          ? "text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/40"
          : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
      }`}
    >
      <Heart aria-hidden className={`h-5 w-5 ${active ? "fill-current" : ""}`} />
    </button>
  );
}
