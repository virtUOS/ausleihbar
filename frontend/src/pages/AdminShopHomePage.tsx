// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import type { ShopSetting } from "../types";

/**
 * Admin settings for the signed-in shop start page (StartPage): which
 * suggestion rows appear and how long products are flagged "new". The guest
 * landing page is configured separately under "Startseite" (AdminWelcomePage).
 */
export function AdminShopHomePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (user && !user.is_staff) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">
        {t("Not authorized.")}
      </div>
    );
  }
  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Administration")}
      </h1>
      <AdminTabs />
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Shop start page")}
      </h2>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t(
          "Shown to signed-in users. Choose which suggestion rows appear and how long new products are flagged.",
        )}
      </p>
      <StartPageSectionsEditor />
    </div>
  );
}

/** Toggles for the logged-in start page's featured rows + how long products
 *  are flagged "new" (system-wide). */
function StartPageSectionsEditor() {
  const { t } = useTranslation();
  const setting = useFetch<ShopSetting>(() => api.getShopSetting(), []);
  const [showPopular, setShowPopular] = useState(true);
  const [showNew, setShowNew] = useState(true);
  const [newDays, setNewDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (setting.data) {
      setShowPopular(setting.data.show_popular);
      setShowNew(setting.data.show_new_arrivals);
      setNewDays(setting.data.new_product_days);
    }
  }, [setting.data]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await api.updateShopSetting({
        show_popular: showPopular,
        show_new_arrivals: showNew,
        new_product_days: newDays,
      });
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Failed.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-3 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={showPopular}
          onChange={(e) => setShowPopular(e.target.checked)}
        />
        {t("Show “Popular right now”")}
      </label>
      <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={showNew}
          onChange={(e) => setShowNew(e.target.checked)}
        />
        {t("Show “New arrivals”")}
      </label>
      <label className="block text-xs text-slate-500 dark:text-slate-400">
        {t("Show “New” label for (days)")}
        <input
          type="number"
          min={0}
          value={newDays}
          onChange={(e) => setNewDays(Number(e.target.value || 0))}
          className="mt-1 block w-28 rounded-md border border-slate-300 dark:border-slate-600 dark:bg-slate-800 px-2 py-1 text-sm text-slate-900 dark:text-slate-100"
        />
      </label>
      <div className="flex items-center gap-3 pt-1">
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Loading…") : t("Save")}
        </button>
        {message && (
          <span className={`text-sm ${message.ok ? "text-green-700 dark:text-green-300" : "text-red-600 dark:text-red-300"}`}>
            {message.text}
          </span>
        )}
      </div>
    </form>
  );
}
