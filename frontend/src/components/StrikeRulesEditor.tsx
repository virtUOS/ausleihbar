// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { Loading } from "./Status";
import { DeleteButton } from "./RowActions";
import type { StrikeSetting, StrikeThreshold } from "../types";

/** Editor for the strike policy: how long a strike counts and the escalation. */
export function StrikeRulesEditor() {
  const { t } = useTranslation();
  const [expiry, setExpiry] = useState(365);
  const [thresholds, setThresholds] = useState<StrikeThreshold[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.getStrikeSetting().then((s) => {
      setExpiry(s.strike_expiry_days);
      setThresholds(s.thresholds);
      setLoading(false);
    });
  }, []);

  function setRow(i: number, patch: Partial<StrikeThreshold>) {
    setThresholds((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const payload: StrikeSetting = {
        strike_expiry_days: expiry,
        thresholds: thresholds.filter((t) => t.count > 0),
      };
      const saved = await api.updateStrikeSetting(payload);
      setThresholds(saved.thresholds);
      setExpiry(saved.strike_expiry_days);
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Failed.") });
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading />;

  return (
    <form onSubmit={save} className="space-y-5 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <label className="block text-xs text-slate-500 dark:text-slate-400">
        {t("A strike counts for (days)")}
        <input
          type="number"
          min={1}
          value={expiry}
          onChange={(e) => setExpiry(Number(e.target.value || 0))}
          className="mt-1 block w-28 rounded-md border border-slate-300 dark:border-slate-600 dark:bg-slate-800 px-2 py-1 text-sm text-slate-900 dark:text-slate-100"
        />
        <span className="mt-1 block text-slate-400 dark:text-slate-500">
          {t("After this time a strike no longer counts towards a block.")}
        </span>
      </label>

      <div>
        <p className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          {t("Escalation — what happens once a borrower reaches a strike count")}
        </p>
        <div className="space-y-2">
          {thresholds.map((th, i) => {
            const permanent = th.block_days === 0;
            return (
              <div
                key={i}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-sm text-slate-700 dark:text-slate-200"
              >
                <span>{t("From")}</span>
                <input
                  type="number"
                  min={1}
                  value={th.count}
                  onChange={(e) => setRow(i, { count: Number(e.target.value || 0) })}
                  className="w-16 rounded-md border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 px-2 py-1"
                />
                <span>{t("strikes:")}</span>
                <label className="ml-1 flex items-center gap-1">
                  <input
                    type="radio"
                    name={`mode-${i}`}
                    checked={!permanent}
                    onChange={() => setRow(i, { block_days: 30 })}
                  />
                  {t("block for")}
                </label>
                <input
                  type="number"
                  min={1}
                  value={permanent ? "" : th.block_days}
                  disabled={permanent}
                  onChange={(e) => setRow(i, { block_days: Number(e.target.value || 0) })}
                  className="w-20 rounded-md border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 px-2 py-1 disabled:bg-slate-100 dark:disabled:bg-slate-800"
                />
                <span>{t("days")}</span>
                <label className="ml-2 flex items-center gap-1">
                  <input
                    type="radio"
                    name={`mode-${i}`}
                    checked={permanent}
                    onChange={() => setRow(i, { block_days: 0 })}
                  />
                  {t("permanent")}
                </label>
                <DeleteButton
                  className="ml-auto"
                  label={t("Remove step")}
                  onClick={() => setThresholds((rows) => rows.filter((_, j) => j !== i))}
                />
              </div>
            );
          })}
          {thresholds.length === 0 && (
            <p className="text-sm text-slate-400 dark:text-slate-500">
              {t("No escalation steps — strikes never block automatically.")}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setThresholds((rows) => [...rows, { count: 1, block_days: 30 }])}
          className="mt-2 text-xs text-slate-600 dark:text-slate-300 hover:underline"
        >
          {t("+ Add step")}
        </button>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Saving…") : t("Save rules")}
        </button>
        {message && (
          <span className={message.ok ? "text-sm text-green-700 dark:text-green-300" : "text-sm text-red-600 dark:text-red-400"}>
            {message.text}
          </span>
        )}
      </div>
    </form>
  );
}
