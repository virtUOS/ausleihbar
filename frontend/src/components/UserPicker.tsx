// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import { api } from "../api";
import type { ManageUser, PoolLender } from "../types";

/** Minimal user shape the picker hands back (matches `PoolLender`). */
export type PickedUser = PoolLender;

const MIN_CHARS = 2;
const DEBOUNCE_MS = 300;
const MAX_RESULTS = 10;

/** "First Last", falling back to the username. */
export function userDisplayName(u: Pick<PoolLender, "first_name" | "last_name" | "username">) {
  return `${u.first_name} ${u.last_name}`.trim() || u.username;
}

/** Map a user-management row onto the picker's result shape. `full_name` is
 *  Django's `get_full_name()` ("First Last"), so keeping it in `first_name`
 *  yields the same display name as a lender row from the backend. */
function toPicked(u: ManageUser): PickedUser {
  return { id: u.id, username: u.username, first_name: u.full_name ?? "", last_name: "", email: u.email };
}

/**
 * Searchable single-user picker (WAI-ARIA combobox with a listbox popup). Searches
 * the admin user list (debounced, from 2 characters), skips inactive users and
 * `excludeIds`, and calls `onPick` on click/Enter. Picking clears the input and
 * keeps focus in it so several users can be added in a row.
 */
export function UserPicker({
  onPick,
  excludeIds = [],
  label,
  placeholder,
}: {
  onPick: (user: PickedUser) => void;
  excludeIds?: number[];
  label: string;
  placeholder?: string;
}) {
  const { t } = useTranslation();
  const baseId = useId();
  const inputId = `${baseId}-input`;
  const listId = `${baseId}-list`;
  const optionId = (i: number) => `${baseId}-opt-${i}`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [users, setUsers] = useState<PickedUser[]>([]);
  const [active, setActive] = useState(-1);

  const term = query.trim();
  const searchable = term.length >= MIN_CHARS;

  useEffect(() => {
    if (!searchable) {
      setUsers([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      api
        .listUsers({ search: term })
        .then((page) => {
          if (cancelled) return;
          setUsers(page.results.filter((u) => u.is_active).map(toPicked));
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setUsers([]);
          setError(err instanceof Error ? err.message : t("Search failed."));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [term, searchable, t]);

  const results = users.filter((u) => !excludeIds.includes(u.id)).slice(0, MAX_RESULTS);
  const expanded = open && searchable && !loading && results.length > 0;

  // Keep the highlighted option within range when results change.
  useEffect(() => {
    setActive((a) => (a >= results.length ? results.length - 1 : a));
  }, [results.length]);

  function pick(user: PickedUser) {
    onPick(user);
    setQuery("");
    setUsers([]);
    setActive(-1);
    setOpen(false);
    inputRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      if (results.length) setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      if (results.length) setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Enter") {
      // Never submit the surrounding form from the search field.
      e.preventDefault();
      if (expanded && active >= 0 && results[active]) pick(results[active]);
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
        setActive(-1);
      }
    }
  }

  let status = "";
  if (searchable && open) {
    if (loading) status = t("Searching…");
    else if (error) status = error;
    else if (results.length === 0) status = t("No matches.");
    else status = t("Matching users: {{n}}", { n: results.length });
  }

  return (
    <div className="relative w-full sm:max-w-sm">
      <label htmlFor={inputId} className="mb-1 block text-xs text-slate-600 dark:text-slate-300">
        {label}
      </label>
      <div className="relative">
        <Search
          aria-hidden
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
        />
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          role="combobox"
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-activedescendant={expanded && active >= 0 ? optionId(active) : undefined}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(-1);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            setOpen(false);
            setActive(-1);
          }}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? t("Search by name, username or email…")}
          className="w-full rounded-full border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 outline-none focus:border-brand-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        />
      </div>
      <ul
        id={listId}
        role="listbox"
        aria-label={label}
        hidden={!expanded}
        className="absolute z-30 mt-1 max-h-[60vh] w-full overflow-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
      >
        {results.map((u, i) => (
          <li
            key={u.id}
            id={optionId(i)}
            role="option"
            aria-selected={i === active}
            onMouseDown={(e) => e.preventDefault()}
            onMouseEnter={() => setActive(i)}
            onClick={() => pick(u)}
            className={`flex cursor-pointer flex-col px-4 py-2.5 text-left ${
              i === active ? "bg-slate-100 dark:bg-slate-700" : ""
            }`}
          >
            <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
              {userDisplayName(u)}
              {userDisplayName(u) !== u.username && (
                <span className="ml-2 text-xs font-normal text-slate-600 dark:text-slate-300">
                  {u.username}
                </span>
              )}
            </span>
            {u.email && (
              <span className="text-xs text-slate-600 dark:text-slate-300">{u.email}</span>
            )}
          </li>
        ))}
      </ul>
      {open && searchable && !expanded && (
        <p
          aria-hidden
          className="absolute z-30 mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-center text-sm text-slate-600 shadow-lg dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
        >
          {status}
        </p>
      )}
      <span className="sr-only" role="status" aria-live="polite">
        {status}
      </span>
    </div>
  );
}
