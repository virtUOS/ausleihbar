// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { ReorderControls } from "./ReorderControls";

interface OrderedPickerProps {
  options: { id: number; label: string }[];
  value: number[];
  onChange: (ids: number[]) => void;
  excludeIds?: number[];
  placeholder?: string;
  emptyText?: string;
}

/** Pick items from a list and arrange them in order (↑/↓). Used for a product's
 *  complementary devices (#23); generic so other ordered picks can reuse it. */
export function OrderedPicker({
  options,
  value,
  onChange,
  excludeIds = [],
  placeholder,
  emptyText,
}: OrderedPickerProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const byId = new Map(options.map((o) => [o.id, o]));
  const selected = value.filter((id) => byId.has(id));
  const needle = query.trim().toLowerCase();
  const candidates = needle
    ? options
        .filter(
          (o) =>
            !value.includes(o.id) &&
            !excludeIds.includes(o.id) &&
            o.label.toLowerCase().includes(needle),
        )
        .slice(0, 8)
    : [];

  function move(index: number, delta: number) {
    const next = [...selected];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <div className="rounded-md border border-slate-200 dark:border-slate-800">
      {selected.length === 0 ? (
        <p className="px-3 py-2 text-sm text-slate-600 dark:text-slate-300">{emptyText}</p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {selected.map((id, i) => (
            <li key={id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              <span className="min-w-0 flex-1 truncate text-slate-900 dark:text-slate-100">
                {byId.get(id)!.label}
              </span>
              <ReorderControls
                label={byId.get(id)!.label}
                isFirst={i === 0}
                isLast={i === selected.length - 1}
                onUp={() => move(i, -1)}
                onDown={() => move(i, 1)}
              />
              <button
                type="button"
                onClick={() => onChange(selected.filter((x) => x !== id))}
                aria-label={t("Remove {{name}}", { name: byId.get(id)!.label })}
                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t border-slate-200 p-2 dark:border-slate-800">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
        {candidates.length > 0 && (
          <ul className="mt-1">
            {candidates.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange([...selected, o.id]);
                    setQuery("");
                  }}
                  className="w-full rounded px-2 py-1 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  + {o.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
