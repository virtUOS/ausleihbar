// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";

export interface Option {
  id: number;
  label: string;
  sublabel?: string;
}

/**
 * Checkbox multi-select with a client-side search box, for assigning related
 * items (e.g. a category's products). The full option list is passed in;
 * filtering happens locally so it stays instant even with hundreds of options.
 */
export function MultiSelectList({
  options,
  selected,
  onToggle,
  placeholder,
  emptyText,
}: {
  options: Option[];
  selected: number[];
  onToggle: (id: number) => void;
  placeholder?: string;
  emptyText?: string;
}) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? options.filter((o) =>
        `${o.label} ${o.sublabel ?? ""}`.toLowerCase().includes(needle),
      )
    : options;

  return (
    <div className="rounded-md border border-slate-200 dark:border-slate-800">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-2 py-1 dark:border-slate-800">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder ?? t("Search…")}
          className="w-full rounded-md border border-slate-300 px-2 py-0.5 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
        <span className="shrink-0 text-xs text-slate-400 dark:text-slate-300">
          {t("{{count}} selected", { count: selected.length })}
        </span>
      </div>
      <div className="max-h-56 space-y-1 overflow-y-auto p-2">
        {options.length === 0 && (
          <p className="text-xs text-slate-400 dark:text-slate-300">
            {emptyText ?? t("Nothing available.")}
          </p>
        )}
        {filtered.map((o) => (
          <label
            key={o.id}
            className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"
          >
            <input
              type="checkbox"
              checked={selected.includes(o.id)}
              onChange={() => onToggle(o.id)}
            />
            {o.label}
            {o.sublabel && (
              <span className="text-xs text-slate-400 dark:text-slate-300">{o.sublabel}</span>
            )}
          </label>
        ))}
        {options.length > 0 && filtered.length === 0 && (
          <p className="text-xs text-slate-400 dark:text-slate-300">{t("No matches.")}</p>
        )}
      </div>
    </div>
  );
}
