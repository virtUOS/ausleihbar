// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Plus, X } from "lucide-react";

export interface AccessGroupOption {
  id: number;
  name: string;
  /** Already a group of the department itself: listed first. */
  in_pool?: boolean;
}

const hintCls = "text-xs text-slate-600 dark:text-slate-300";

/**
 * The assigned access groups as a list (each removable with ✕) plus an
 * "Add group" dropdown with a search field listing the groups not assigned
 * yet (the department's own first). `groups` null shows a loading line.
 * Used for the "Who may book" pickers of rooms, places and the bulk groups
 * dialog.
 */
export function AccessGroupPicker({
  groups,
  selected,
  onToggle,
  disabledIds = [],
  disabled = false,
  legend,
  hint,
  before,
  emptyText,
  note,
  alsoAddable = [],
  onAdd,
  lockedIds = [],
}: {
  groups: AccessGroupOption[] | null;
  selected: number[];
  /** Adds an unassigned group / removes an assigned one. */
  onToggle: (id: number) => void;
  /** Groups that can't be added here (e.g. chosen in the other list). */
  disabledIds?: number[];
  /** Read-only (e.g. it follows the room): no ✕, no dropdown. */
  disabled?: boolean;
  legend: ReactNode;
  hint?: ReactNode;
  /** Rendered between hint and list (e.g. a "Like the room" switch). */
  before?: ReactNode;
  /** Shown when no group is assigned; defaults to "No group". */
  emptyText?: string;
  /** Muted text beside an assigned group (e.g. "2 of 5" in bulk edits). */
  note?: (id: number) => string | undefined;
  /** Assigned groups that can still be added (e.g. "add to all" in bulk). */
  alsoAddable?: number[];
  /** Called for a pick from the dropdown; defaults to `onToggle`. */
  onAdd?: (id: number) => void;
  /** Assigned groups shown without ✕ (e.g. add-only: already in the pool). */
  lockedIds?: number[];
}) {
  const { t } = useTranslation();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLFieldSetElement>(null);
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const byId = new Map((groups ?? []).map((g) => [g.id, g]));
  const assigned = selected.filter((id) => byId.has(id));
  const needle = query.trim().toLowerCase();
  const candidates = (groups ?? [])
    .filter(
      (g) => (!selected.includes(g.id) || alsoAddable.includes(g.id)) && !disabledIds.includes(g.id),
    )
    .filter((g) => !needle || g.name.toLowerCase().includes(needle))
    .sort(
      (a, b) =>
        Number(b.in_pool ?? false) - Number(a.in_pool ?? false) || a.name.localeCompare(b.name),
    );

  function add(id: number) {
    (onAdd ?? onToggle)(id);
    setQuery("");
    setOpen(false);
  }

  return (
    <fieldset ref={root}>
      <legend className="mb-1 block text-xs font-semibold text-slate-600 dark:text-slate-300">
        {legend}
      </legend>
      {hint && <p className={`mb-1 ${hintCls}`}>{hint}</p>}
      {before}
      {groups === null ? (
        <p className={hintCls}>{t("Loading…")}</p>
      ) : (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700">
          {assigned.length === 0 ? (
            <p className={`px-3 py-2.5 ${hintCls}`}>{emptyText ?? t("No group")}</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {assigned.map((id) => {
                const name = byId.get(id)!.name;
                return (
                  <li
                    key={id}
                    className={`flex min-h-[44px] items-center gap-2 pl-3 pr-1 text-sm ${
                      disabled ? "text-slate-500 dark:text-slate-400" : "text-slate-900 dark:text-slate-100"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">{name}</span>
                    {note?.(id) && <span className={hintCls}>{note(id)}</span>}
                    {!disabled && !lockedIds.includes(id) && (
                      <button
                        type="button"
                        onClick={() => onToggle(id)}
                        aria-label={t("Remove {{name}}", { name })}
                        title={t("Remove {{name}}", { name })}
                        className="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-600 transition-colors duration-150 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                      >
                        <X aria-hidden className="h-4 w-4" />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {!disabled && (
            <div className="border-t border-slate-200 dark:border-slate-700">
              <button
                type="button"
                aria-expanded={open}
                aria-controls={listId}
                onClick={() => setOpen((o) => !o)}
                className="flex min-h-[44px] w-full items-center gap-2 px-3 text-left text-sm font-medium text-brand-700 transition-colors duration-150 hover:bg-slate-50 dark:text-brand-300 dark:hover:bg-slate-800/60"
              >
                <Plus aria-hidden className="h-4 w-4" />
                <span className="flex-1">{t("Add group…")}</span>
                <ChevronDown
                  aria-hidden
                  className={`h-4 w-4 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
                />
              </button>
              {open && (
                <div id={listId} className="border-t border-slate-200 p-2 dark:border-slate-700">
                  <input
                    ref={search}
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        e.preventDefault();
                        e.stopPropagation();
                        setOpen(false);
                      } else if (e.key === "Enter") {
                        e.preventDefault();
                        if (candidates.length > 0) add(candidates[0].id);
                      }
                    }}
                    placeholder={t("Search groups…")}
                    aria-label={t("Search groups…")}
                    className="mb-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                  />
                  {candidates.length === 0 ? (
                    <p className={`px-1 py-2 ${hintCls}`}>
                      {(groups ?? []).length === 0 ? t("No access groups defined yet.") : t("No matches.")}
                    </p>
                  ) : (
                    <ul className="max-h-56 overflow-y-auto">
                      {candidates.map((g) => (
                        <li key={g.id}>
                          <button
                            type="button"
                            onClick={() => add(g.id)}
                            className="flex min-h-[44px] w-full items-center rounded px-2 text-left text-sm text-slate-800 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                          >
                            {g.name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </fieldset>
  );
}
