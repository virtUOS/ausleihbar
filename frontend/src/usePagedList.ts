// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useRef, useState } from "react";
import type { Paginated } from "./types";

// Must match the backend default page size (config.pagination.StandardPagination).
export const PAGE_SIZE = 25;

/**
 * Server-side paginated + searchable list. Pass a fetcher that takes
 * {page, search} and returns a DRF `Paginated<T>`.
 *
 * `filtersKey` is the set of active filters: when it changes, the list resets
 * to page 1 (a different filter rarely has the same pages). Search is debounced
 * and likewise resets to page 1. To refresh after editing a row, call the
 * returned `reload()` — it refetches the *current* page so the user stays put.
 * If a delete empties the current (last) page, it steps back one page.
 */
export function usePagedList<T>(
  fetcher: (params: { page: number; search: string }) => Promise<Paginated<T>>,
  filtersKey: unknown = 0,
) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [reloadCount, setReloadCount] = useState(0);
  const [data, setData] = useState<Paginated<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const id = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [search]);

  // A filter change resets to page 1 so we never request a now-out-of-range
  // page. A plain reload() (after an edit) does NOT — it keeps the page.
  useEffect(() => {
    setPage(1);
  }, [filtersKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetcherRef
      .current({ page, search: debounced })
      .then((d) => {
        if (cancelled) return;
        // A delete may have emptied the current (last) page → step back.
        if (d.results.length === 0 && page > 1) {
          setPage((p) => p - 1);
          return;
        }
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        // Out-of-range page (DRF 404s after the last row on a page is deleted)
        // → step back one page instead of surfacing an error.
        const msg = e instanceof Error ? e.message : "Failed";
        if (page > 1 && msg.includes("(404)")) {
          setPage((p) => p - 1);
          return;
        }
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, debounced, filtersKey, reloadCount]);

  const reload = useCallback(() => setReloadCount((n) => n + 1), []);

  const count = data?.count ?? 0;
  return {
    items: data?.results ?? [],
    count,
    page,
    setPage,
    search,
    setSearch,
    loading,
    error,
    reload,
    hasPrev: Boolean(data?.previous),
    hasNext: Boolean(data?.next),
    from: count === 0 ? 0 : (page - 1) * PAGE_SIZE + 1,
    to: Math.min(page * PAGE_SIZE, count),
  };
}
