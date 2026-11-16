// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Building2, Check, ChevronDown, Search } from "lucide-react";

export interface BuildingOption {
  /** Building id; null stands for "without building". */
  id: number | null;
  code: string;
  description: string;
  address?: string;
}

/** Natural order of building codes: "2" before "15", "AX" after "15". */
export function compareBuildingCodes(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

/** From this many buildings on the list gets a search field. */
const SEARCH_FROM = 7;

/**
 * Compact building picker: a pill button with the short code (description
 * beside it from `sm` up) that opens a searchable list — code in bold, the
 * description muted below, the current one ticked. Built for long lists
 * (a campus may have a hundred buildings).
 */
export function BuildingSelect({
  options,
  value,
  onChange,
  label,
}: {
  options: BuildingOption[];
  value: number | null;
  onChange: (id: number | null) => void;
  label: string;
}) {
  const { t } = useTranslation();
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (i: number) => `${baseId}-opt-${i}`;
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);

  const sorted = useMemo(
    () => [...options].sort((a, b) => compareBuildingCodes(a.code, b.code)),
    [options],
  );
  const searchable = sorted.length >= SEARCH_FROM;
  const term = query.trim().toLocaleLowerCase();
  const results = term
    ? sorted.filter((o) =>
        [o.code, o.description, o.address ?? ""].some((s) => s.toLocaleLowerCase().includes(term)),
      )
    : sorted;
  const current = sorted.find((o) => o.id === value);
  const noneLabel = t("Without building");

  useEffect(() => {
    if (!open) return;
    const start = results.findIndex((o) => o.id === value);
    setActive(start >= 0 ? start : 0);
    (searchable ? searchRef.current : listRef.current)?.focus();
    function onDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
    // Only when opening: the highlight then follows the keyboard.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (active >= 0) document.getElementById(optionId(active))?.scrollIntoView({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  function close(focusButton = true) {
    setOpen(false);
    setQuery("");
    if (focusButton) buttonRef.current?.focus();
  }

  function pick(o: BuildingOption) {
    onChange(o.id);
    close();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (results.length) setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (results.length) setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Home" && !searchable) {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End" && !searchable) {
      e.preventDefault();
      setActive(results.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results[active]) pick(results[active]);
    } else if (e.key === "Escape") {
      // Close only the list, not a surrounding sheet or dialog.
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      close(false);
    }
  }

  if (sorted.length === 1 && current) {
    // Nothing to choose: show the building as a plain label.
    return (
      <span
        aria-label={`${label}: ${current.code || noneLabel}`}
        className="inline-flex min-h-[44px] max-w-full items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <Building2 aria-hidden className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
        <span className="font-semibold">{current.code || noneLabel}</span>
        {current.description && (
          <span className="hidden max-w-[12rem] truncate text-slate-600 sm:inline dark:text-slate-300">
            {current.description}
          </span>
        )}
      </span>
    );
  }

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${current ? current.code || noneLabel : ""}`}
        onClick={() => (open ? close() : setOpen(true))}
        className="inline-flex min-h-[44px] max-w-full items-center gap-2 rounded-full border border-slate-300 bg-white pl-3 pr-2.5 text-sm text-slate-900 transition-colors duration-150 hover:border-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-slate-500"
      >
        <Building2 aria-hidden className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
        <span className="font-semibold">{current ? current.code || noneLabel : label}</span>
        {current?.description && (
          <span className="hidden max-w-[12rem] truncate text-slate-600 sm:inline dark:text-slate-300">
            {current.description}
          </span>
        )}
        <ChevronDown
          aria-hidden
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="absolute left-0 z-30 mt-1 w-72 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800">
          {searchable && (
            <div className="relative border-b border-slate-200 p-2 dark:border-slate-700">
              <Search
                aria-hidden
                className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
              />
              <input
                ref={searchRef}
                type="text"
                role="combobox"
                autoComplete="off"
                aria-label={t("Search buildings")}
                aria-autocomplete="list"
                aria-expanded
                aria-controls={listId}
                aria-activedescendant={active >= 0 && results[active] ? optionId(active) : undefined}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActive(0);
                }}
                onKeyDown={onKeyDown}
                placeholder={t("Code, name or address")}
                className="w-full rounded-full border border-slate-300 bg-white py-2 pl-8 pr-3 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              />
            </div>
          )}
          <ul
            ref={listRef}
            id={listId}
            role="listbox"
            aria-label={label}
            tabIndex={searchable ? -1 : 0}
            aria-activedescendant={!searchable && active >= 0 ? optionId(active) : undefined}
            onKeyDown={searchable ? undefined : onKeyDown}
            className="max-h-[50vh] overflow-auto py-1 focus:outline-none"
          >
            {results.map((o, i) => {
              const selected = o.id === value;
              return (
                <li
                  key={o.id ?? "none"}
                  id={optionId(i)}
                  role="option"
                  aria-selected={selected}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(o)}
                  className={`flex cursor-pointer items-start gap-3 px-3 py-2 ${
                    i === active ? "bg-slate-100 dark:bg-slate-700" : ""
                  }`}
                >
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
                    {selected && <Check aria-hidden className="h-4 w-4 text-brand-600 dark:text-brand-400" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {o.code || noneLabel}
                    </span>
                    {o.description && (
                      <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                        {o.description}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
            {results.length === 0 && (
              <li className="px-3 py-2 text-sm text-slate-600 dark:text-slate-300">{t("No matches.")}</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
