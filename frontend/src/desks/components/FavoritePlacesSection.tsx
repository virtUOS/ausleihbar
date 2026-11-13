// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DoorOpen, LampDesk, X } from "lucide-react";
import { useFetch } from "../../useFetch";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";

/** Favourite desks and meeting rooms on the shop's favourites page (header
 *  heart): each links to booking it; the cross removes it. Rendered only for
 *  people who may book desks; returns whether it has rows via `onCount`. */
export function FavoritePlacesSection({ onCount }: { onCount?: (n: number) => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [version, setVersion] = useState(0);
  const { data, loading, error } = useFetch(async () => {
    const r = await desksApi.favorites();
    onCount?.(r.places.length);
    return r.places;
  }, [version]);

  async function remove(id: number) {
    try {
      await desksApi.setFavorite(id, false);
      setVersion((v) => v + 1);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data || data.length === 0) return null;
  const pools = new Set(data.map((p) => p.pool));

  return (
    <section className="mb-6 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Desks and meeting rooms")}
      </h2>
      <ul className="space-y-1">
        {data.map((p) => {
          const Icon = p.kind === "meeting_room" ? DoorOpen : LampDesk;
          const q = new URLSearchParams({ pool: String(p.pool), place: String(p.id), kind: p.kind });
          const where = [pools.size > 1 ? p.pool_name : "", p.building, p.floor, p.room].filter(Boolean);
          return (
            <li
              key={p.id}
              className="flex min-h-[44px] items-center gap-3 rounded-lg border border-slate-100 p-2 dark:border-slate-800"
            >
              <Icon aria-hidden className="h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                  {p.name}
                </span>
                <span className="block truncate text-xs text-slate-600 dark:text-slate-300">
                  {where.join(" · ")}
                </span>
              </span>
              <Link
                to={`/desks/book?${q}`}
                className="inline-flex min-h-[44px] shrink-0 items-center rounded-full bg-brand-400 px-4 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("Book")}
              </Link>
              <button
                type="button"
                onClick={() => remove(p.id)}
                aria-label={t("Remove {{name}} from favorites", { name: p.name })}
                title={t("Remove from favorites")}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800"
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
