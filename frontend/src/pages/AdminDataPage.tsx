// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Upload } from "lucide-react";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ErrorBox } from "../components/Status";
import type { ImportSummary, Paginated, ResourcePool } from "../types";

/** Admin data transfer: export the whole system or a single pool as a ZIP
 *  (structure + inventory + images), and import such an archive back (merge by
 *  natural key). System-wide, admin only. */
export function AdminDataPage() {
  const { t } = useTranslation();
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000 }),
    [],
  );
  const poolList = pools.data?.results ?? [];

  const [poolId, setPoolId] = useState<string>("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  async function runExport(withPool: boolean) {
    setExporting(true);
    setExportError(null);
    try {
      await api.exportData(withPool && poolId ? Number(poolId) : undefined);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : t("Export failed."));
    } finally {
      setExporting(false);
    }
  }

  async function runImport(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setImportError(null);
    setSummary(null);
    try {
      setSummary(await api.importData(file, dryRun));
    } catch (e) {
      setImportError(e instanceof Error ? e.message : t("Import failed."));
    } finally {
      setBusy(false);
    }
  }

  const card =
    "rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900";
  const primaryBtn =
    "inline-flex items-center gap-2 rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40";
  const ghostBtn =
    "rounded-full border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800 disabled:opacity-40";

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Import / export")}</h2>
      <p className="mb-4 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
        {t(
          "Export the catalog (product types, products, categories, sections, sets, pools and inventory) including images as a ZIP, and import such an archive back. Bookings, users and other personal data are never included.",
        )}
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Export */}
        <section className={card}>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <Download aria-hidden className="h-4 w-4 text-brand-600" />
            {t("Export")}
          </h3>
          <button type="button" onClick={() => runExport(false)} disabled={exporting} className={primaryBtn}>
            {exporting ? t("Preparing…") : t("Export whole system")}
          </button>

          <div className="mt-4 border-t border-slate-100 pt-4 dark:border-slate-800">
            <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
              {t("Or export a single pool (with the products its devices need):")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={poolId}
                onChange={(e) => setPoolId(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">{t("Choose a pool…")}</option>
                {poolList.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => runExport(true)}
                disabled={exporting || !poolId}
                className={ghostBtn}
              >
                {t("Export pool")}
              </button>
            </div>
          </div>
          {exportError && <div className="mt-3"><ErrorBox message={exportError} /></div>}
        </section>

        {/* Import */}
        <section className={card}>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <Upload aria-hidden className="h-4 w-4 text-brand-600" />
            {t("Import")}
          </h3>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
            {t("Existing entries are matched by their key (name, inventory number…) and updated; missing ones are created. Run a dry run first to preview.")}
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setSummary(null);
              setImportError(null);
            }}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-full file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-slate-700 hover:file:bg-slate-200 dark:text-slate-300 dark:file:bg-slate-800 dark:file:text-slate-200"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={() => runImport(true)} disabled={!file || busy} className={ghostBtn}>
              {busy ? t("Working…") : t("Dry run (preview)")}
            </button>
            <button type="button" onClick={() => runImport(false)} disabled={!file || busy} className={primaryBtn}>
              {t("Import")}
            </button>
          </div>

          {importError && <div className="mt-3"><ErrorBox message={importError} /></div>}
          {summary && <ImportResult summary={summary} />}
        </section>
      </div>
    </div>
  );
}

function ImportResult({ summary }: { summary: ImportSummary }) {
  const { t } = useTranslation();
  const keys = Array.from(
    new Set([...Object.keys(summary.created), ...Object.keys(summary.updated)]),
  ).sort();
  return (
    <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm dark:border-emerald-900/50 dark:bg-emerald-950/30">
      <p className="font-semibold text-emerald-800 dark:text-emerald-300">
        {summary.dry_run ? t("Dry run — nothing was saved. Would change:") : t("Import complete.")}
      </p>
      <ul className="mt-1 space-y-0.5 text-slate-700 dark:text-slate-200">
        {keys.length === 0 && <li>{t("No changes.")}</li>}
        {keys.map((k) => (
          <li key={k}>
            {k}: {t("{{n}} new", { n: summary.created[k] ?? 0 })}, {t("{{n}} updated", { n: summary.updated[k] ?? 0 })}
          </li>
        ))}
        {summary.media > 0 && <li>{t("{{n}} media files", { n: summary.media })}</li>}
      </ul>
    </div>
  );
}
