// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { desksApi } from "./api";

/** The viewer's favourite places (personal; the server drops ones they may
 *  no longer book). `toggle` updates optimistically and rolls back on error. */
export function useFavorites() {
  const { t } = useTranslation();
  const toast = useToast();
  const [ids, setIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let alive = true;
    desksApi
      .favorites()
      .then((r) => alive && setIds(new Set(r.place_ids)))
      .catch(() => {
        /* Favourites are a convenience; lists work without them. */
      });
    return () => {
      alive = false;
    };
  }, []);

  const toggle = useCallback(
    async (placeId: number) => {
      const on = !ids.has(placeId);
      const apply = (value: boolean) =>
        setIds((prev) => {
          const next = new Set(prev);
          if (value) next.add(placeId);
          else next.delete(placeId);
          return next;
        });
      apply(on);
      try {
        await desksApi.setFavorite(placeId, on);
      } catch (e) {
        apply(!on);
        toast.error(e instanceof Error ? e.message : t("The request failed."));
      }
    },
    [ids, t, toast],
  );

  return { ids, toggle };
}

/** Favourites first, otherwise the server's order (stable sort). */
export function favoritesFirst<T extends { id: number }>(rows: T[], ids: Set<number>): T[] {
  return [...rows].sort((a, b) => Number(ids.has(b.id)) - Number(ids.has(a.id)));
}
