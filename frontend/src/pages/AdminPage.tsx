// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { BlockDaysManager } from "../components/BlockDaysManager";
import type { HolidaySetting, Paginated, ResourcePool } from "../types";

const inputClass =
  "rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

export function AdminPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const pools = useFetch<Paginated<ResourcePool>>(() => api.listPools(), []);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      <HolidayRegion />

      <section className="mt-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Block days")}</h2>
        <p className="mb-4 mt-1 text-sm text-slate-600 dark:text-slate-300">
          {t(
            "Days on which no bookings are possible — system-wide (e.g. company holidays) or for a single pool. Public holidays loaded above appear here too and can be removed individually.",
          )}
        </p>
        <BlockDaysManager pools={pools.data?.results ?? []} />
      </section>
    </div>
  );
}

function HolidayRegion() {
  const { t } = useTranslation();
  const [country, setCountry] = useState("DE");
  const [subdivision, setSubdivision] = useState("");
  const [horizon, setHorizon] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const setting = useFetch<HolidaySetting>(() => api.getHolidaySetting(), []);
  useEffect(() => {
    if (setting.data) {
      setCountry(setting.data.country);
      setSubdivision(setting.data.subdivision);
      setHorizon(setting.data.horizon_months);
    }
  }, [setting.data]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.updateHolidaySetting({
        country: country.trim(),
        subdivision: subdivision.trim(),
      });
      setHorizon(res.horizon_months);
      setMessage({
        ok: true,
        text: t(
          "Loaded {{count}} new holiday block(s) for the next {{months}} months.",
          { count: res.loaded ?? 0, months: res.horizon_months },
        ),
      });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Failed.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Public holidays")}</h2>
      <p className="mb-4 mt-1 text-sm text-slate-600 dark:text-slate-300">
        {t("Set the region — public holidays are loaded automatically as system-wide block days for the whole booking horizon")}
        {horizon ? t(" (currently {{months}} months)", { months: horizon }) : ""}
        {t(". Re-save to refresh.")}
      </p>
      <form onSubmit={save} className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600 dark:text-slate-300">
          {t("Country")}
          <input
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            placeholder="DE"
            className={`mt-1 block w-20 ${inputClass}`}
          />
        </label>
        <label className="text-xs text-slate-600 dark:text-slate-300">
          {t("State / subdivision")}
          <input
            value={subdivision}
            onChange={(e) => setSubdivision(e.target.value)}
            placeholder="NI"
            className={`mt-1 block w-24 ${inputClass}`}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Loading…") : t("Save & load holidays")}
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
