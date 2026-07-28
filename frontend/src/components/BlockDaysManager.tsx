// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "./Status";
import { DeleteButton } from "./RowActions";
import { DateField } from "./DateField";
import type { BlockDay, Paginated, ResourcePool } from "../types";

const inputClass =
  "rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-sm text-slate-900 dark:text-slate-100";

/**
 * Lists and manages block days (Sperrtage). When ``poolId`` is given the list
 * and new blocks are scoped to that pool; otherwise (admin overview) it shows
 * all blocks and lets the user pick a pool or block all pools system-wide.
 */
export function BlockDaysManager({
  poolId,
  pools,
}: {
  poolId?: number;
  pools?: ResourcePool[];
}) {
  const { t } = useTranslation();
  const [version, setVersion] = useState(0);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [scopePool, setScopePool] = useState<string>(""); // "" = system-wide
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const blocks = useFetch<Paginated<BlockDay>>(
    () => api.listBlocks(poolId),
    [poolId, version],
  );

  const refetch = () => setVersion((v) => v + 1);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!start) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createBlock({
        start_date: start,
        end_date: end || undefined,
        reason: reason || undefined,
        resource_pool: poolId ?? (scopePool ? Number(scopePool) : null),
      });
      setStart("");
      setEnd("");
      setReason("");
      refetch();
      const adj = created.adjusted;
      if (adj && (adj.rescheduled || adj.cancelled)) {
        window.alert(
          t(
            "Closure saved. {{rescheduled}} booking(s) rescheduled, {{cancelled}} cancelled — affected borrowers were emailed.",
            { rescheduled: adj.rescheduled, cancelled: adj.cancelled },
          ),
        );
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("Could not add block."),
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(block: BlockDay) {
    if (!window.confirm(t("Remove this block day?"))) return;
    try {
      await api.deleteBlock(block.id);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  return (
    <div>
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-slate-500 dark:text-slate-400">
          {t("From")}
          <DateField className="mt-1 block" ariaLabel={t("From")} required value={start} onChange={setStart} />
        </label>
        <label className="text-xs text-slate-500 dark:text-slate-400">
          {t("To (optional)")}
          <DateField className="mt-1 block" ariaLabel={t("To (optional)")} value={end} onChange={setEnd} />
        </label>
        {poolId === undefined && pools && (
          <label className="text-xs text-slate-500 dark:text-slate-400">
            {t("Scope")}
            <select
              value={scopePool}
              onChange={(e) => setScopePool(e.target.value)}
              className={`mt-1 block ${inputClass}`}
            >
              <option value="">{t("All pools (system-wide)")}</option>
              {pools.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex-1 text-xs text-slate-500 dark:text-slate-400">
          {t("Reason (optional)")}
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("e.g. Betriebsferien")}
            className={`mt-1 block w-full ${inputClass}`}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Adding…") : t("Add block")}
        </button>
      </form>

      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-300">{error}</p>}

      <div className="mt-4">
        {blocks.loading && <Loading />}
        {blocks.error && <ErrorBox message={blocks.error} />}
        {blocks.data && (
          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">{t("Days")}</th>
                  {poolId === undefined && (
                    <th className="px-3 py-2">{t("Scope")}</th>
                  )}
                  <th className="px-3 py-2">{t("Reason")}</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {blocks.data.results.map((b) => (
                  <tr key={b.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2 text-slate-700 dark:text-slate-200">
                      {b.start_date}
                      {b.end_date !== b.start_date && ` – ${b.end_date}`}
                    </td>
                    {poolId === undefined && (
                      <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                        {b.pool_name ?? t("All pools")}
                      </td>
                    )}
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                      {b.is_holiday && (
                        <span className="mr-1 rounded-full bg-amber-100 dark:bg-amber-950/50 px-2 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-300">
                          {t("Holiday")}
                        </span>
                      )}
                      {b.reason || "–"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <DeleteButton onClick={() => remove(b)} />
                    </td>
                  </tr>
                ))}
                {blocks.data.results.length === 0 && (
                  <tr>
                    <td
                      colSpan={poolId === undefined ? 4 : 3}
                      className="px-3 py-6 text-center text-slate-500 dark:text-slate-400"
                    >
                      {t("No block days.")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
