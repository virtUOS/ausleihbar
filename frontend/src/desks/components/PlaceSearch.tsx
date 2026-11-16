// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

/** The place text filter of Free now and Book (searches every building and floor). */
export function PlaceSearch({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation();
  return (
    <div className="relative sm:max-w-sm">
      <Search
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
      />
      <input
        type="search"
        aria-label={t("Filter places")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("Place, room, building or equipment")}
        className="min-h-[44px] w-full rounded-full border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
      />
    </div>
  );
}
