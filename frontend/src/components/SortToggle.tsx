// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

export type SortMode = "manual" | "alpha";

export interface SortOption<V extends string = string> {
  value: V;
  label: string;
}

interface SortToggleProps<V extends string> {
  value: V;
  onChange: (mode: V) => void;
  options?: SortOption<V>[];
}

/** Small pill toggle to switch a list between sort orders. Defaults to the
 *  shop's grouped (curated) order vs. A–Z; pass `options` for other orders. */
export function SortToggle(props: SortToggleProps<SortMode>): JSX.Element;
export function SortToggle<V extends string>(
  props: SortToggleProps<V> & { options: SortOption<V>[] },
): JSX.Element;
export function SortToggle({
  value,
  onChange,
  options,
}: {
  value: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange: (mode: any) => void;
  options?: SortOption[];
}) {
  const { t } = useTranslation();
  const base =
    "rounded-full px-2.5 py-1 text-xs font-semibold transition-colors duration-150";
  const opts: SortOption[] = options ?? [
    { value: "manual", label: t("Grouped") },
    { value: "alpha", label: t("A–Z") },
  ];
  return (
    <div
      role="group"
      aria-label={t("Sort order")}
      className="inline-flex gap-0.5 rounded-full bg-slate-100 p-0.5 dark:bg-slate-800"
    >
      {opts.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`${base} ${
            value === o.value
              ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-slate-100"
              : "text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Stable alphabetical sort by a string field (does not mutate the input). */
export function sortAlpha<T>(items: T[], key: (item: T) => string): T[] {
  return [...items].sort((a, b) =>
    key(a).localeCompare(key(b), undefined, { sensitivity: "base" }),
  );
}
