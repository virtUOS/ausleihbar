// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Search } from "lucide-react";

// QR images by key, shared by the on-screen and the print copy of a label so
// each code is fetched once per page visit. Object URLs are small and live
// until the tab is closed.
const qrCache = new Map<string, Promise<string>>();

/** Object URL of a label's QR image, loaded once per `key`. */
export function useLabelQr(key: string, load: () => Promise<string>): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let pending = qrCache.get(key);
    if (!pending) {
      pending = load();
      qrCache.set(key, pending);
      pending.catch(() => qrCache.delete(key));
    }
    pending.then((url) => alive && setSrc(url)).catch(() => {});
    return () => {
      alive = false;
    };
    // `load` is recreated on every render; the key identifies the image.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return src;
}

export interface PickableLabel {
  id: number;
  /** Text the search matches (name, location, product …). */
  search: string;
}

/** Search + clickable labels for the QR label pages (lending items and desk
 *  places). Clicking a label selects it for printing; "Select all/none" act
 *  on the labels matching the search. The print sheet holds every selected
 *  label, also those the current search hides, so a selection can be
 *  collected over several searches. */
export function QrLabelPicker<T extends PickableLabel>({
  items,
  selected,
  onSelectedChange,
  render,
  emptyText,
}: {
  items: T[];
  selected: Set<number>;
  onSelectedChange: (next: Set<number>) => void;
  render: (item: T) => ReactNode;
  emptyText: string;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((i) => {
      const text = i.search.toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [items, query]);
  const printed = items.filter((i) => selected.has(i.id));

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  };
  const setShown = (on: boolean) => {
    const next = new Set(selected);
    for (const i of shown) {
      if (on) next.add(i.id);
      else next.delete(i.id);
    }
    onSelectedChange(next);
  };

  return (
    <>
      <div className="print:hidden">
        {items.length === 0 ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">{emptyText}</p>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="relative min-w-0 flex-1 basis-56">
                <Search
                  aria-hidden
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-300"
                />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("Search labels")}
                  aria-label={t("Search labels")}
                  className="min-h-[44px] w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                />
              </div>
              <button
                type="button"
                onClick={() => setShown(true)}
                disabled={shown.length === 0}
                className="min-h-[44px] rounded-full border border-slate-300 px-4 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {query ? t("Select all found") : t("Select all")}
              </button>
              <button
                type="button"
                onClick={() => setShown(false)}
                disabled={shown.length === 0}
                className="min-h-[44px] rounded-full border border-slate-300 px-4 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {query ? t("Deselect all found") : t("Select none")}
              </button>
            </div>
            <p className="mb-3 text-sm text-slate-600 dark:text-slate-300" aria-live="polite">
              {t("Click the labels you want to print.")}{" "}
              {t("{{selected}} of {{total}} selected", { selected: printed.length, total: items.length })}
              {query && ` · ${t("{{count}} found", { count: shown.length })}`}
            </p>
            {shown.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">{t("No labels match the search.")}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {shown.map((item) => {
                  const on = selected.has(item.id);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle(item.id)}
                      className={
                        "relative rounded-md text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 dark:focus-visible:ring-slate-100 " +
                        (on
                          ? "ring-2 ring-brand-400 ring-offset-2 dark:ring-offset-slate-900"
                          : "opacity-50 hover:opacity-100")
                      }
                    >
                      {render(item)}
                      {on && (
                        <span className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-brand-400 text-slate-900">
                          <Check aria-hidden className="h-3.5 w-3.5" />
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
      {/* The printable sheet: every selected label, whatever the search. */}
      <div className="label-sheet hidden flex-wrap gap-2 print:flex">
        {printed.map((item) => (
          // No wrapper element: the roll formats break pages after each
          // `.qr-label` except the `:last-child`.
          <Fragment key={item.id}>{render(item)}</Fragment>
        ))}
      </div>
    </>
  );
}
