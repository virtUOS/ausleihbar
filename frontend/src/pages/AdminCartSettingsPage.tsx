// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import type { CartSetting } from "../types";

export function AdminCartSettingsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }
  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Cart")}</h2>
      <p className="mb-4 text-xs text-slate-600 dark:text-slate-300">
        {t(
          "When a product is put in the cart its resource is reserved for everyone else. The hold lasts this long and is renewed on every cart action; once it lapses the resource is free again.",
        )}
      </p>
      <CartHoldEditor />
    </div>
  );
}

function CartHoldEditor() {
  const { t } = useTranslation();
  const [minutes, setMinutes] = useState(30);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const setting = useFetch<CartSetting>(() => api.getCartSetting(), []);
  useEffect(() => {
    if (setting.data) setMinutes(setting.data.hold_minutes);
  }, [setting.data]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.updateCartSetting({ hold_minutes: minutes });
      setMinutes(res.hold_minutes);
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Failed.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900">
      <form onSubmit={save} className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600 dark:text-slate-300">
          {t("Cart hold (minutes)")}
          <input
            type="number"
            min={1}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value || 0))}
            className="mt-1 block w-28 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Loading…") : t("Save")}
        </button>
      </form>
      {message && (
        <p className={`mt-3 text-sm ${message.ok ? "text-green-700 dark:text-green-300" : "text-red-600 dark:text-red-300"}`}>
          {message.text}
        </p>
      )}
    </section>
  );
}
