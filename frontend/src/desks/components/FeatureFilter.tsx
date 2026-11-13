// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import type { Feature } from "../types";

interface Props {
  features: Feature[];
  value: number[];
  onChange: (ids: number[]) => void;
}

/** Equipment filter: toggle chips for the department's features (hidden when
 *  the department has none). A place must have every selected feature. */
export function FeatureFilter({ features, value, onChange }: Props) {
  const { t } = useTranslation();
  if (features.length === 0) return null;
  const toggle = (id: number) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  return (
    <div role="group" aria-label={t("Equipment")} className="flex flex-wrap gap-2">
      {features.map((f) => {
        const on = value.includes(f.id);
        return (
          <button
            key={f.id}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(f.id)}
            className={`min-h-[44px] rounded-full border px-4 text-sm font-medium transition-colors duration-150 ${
              on
                ? "border-brand-500 bg-brand-100 text-slate-900"
                : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            {f.name}
          </button>
        );
      })}
    </div>
  );
}

/** Names of the given feature ids (unknown ids dropped). */
export function featureNames(features: Feature[], ids: number[]): string[] {
  const names = new Map(features.map((f) => [f.id, f.name]));
  return ids.map((id) => names.get(id)).filter((n): n is string => !!n);
}
