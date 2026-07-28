// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { Heart } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";

/** Toggle a product in the borrower's favorites (issue: favorites). Hidden for
 *  signed-out visitors. Optimistic; reverts on error. */
export function FavoriteButton({
  productId,
  initial,
}: {
  productId: number;
  initial: boolean;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [fav, setFav] = useState(initial);
  const [busy, setBusy] = useState(false);

  useEffect(() => setFav(initial), [initial, productId]);

  if (!user?.authenticated) return null;

  async function toggle() {
    const next = !fav;
    setBusy(true);
    setFav(next);
    try {
      if (next) await api.addFavorite(productId);
      else await api.removeFavorite(productId);
    } catch {
      setFav(!next);
    } finally {
      setBusy(false);
    }
  }

  const label = fav ? t("In favorites") : t("Add to favorites");
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={fav}
      aria-label={label}
      title={label}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-150 ${
        fav
          ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-300"
          : "border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
      }`}
    >
      <Heart aria-hidden className={`h-4 w-4 ${fav ? "fill-current" : ""}`} />
      {label}
    </button>
  );
}
