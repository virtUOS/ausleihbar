// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, Trash2 } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { AdminTabs } from "../components/AdminTabs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import type { TrashItem, TrashSetting } from "../types";

/** Datetime formatting for `deleted_at` / `purge_at`, which are ISO timestamps. */
function fmtDateTime(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AdminTrashPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const confirm = useConfirm();
  const toast = useToast();
  const [version, setVersion] = useState(0);
  const refetch = () => setVersion((v) => v + 1);

  const trash = useFetch<TrashItem[]>(() => api.listTrash(), [version]);

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  // Local map from the API's type slug to a translated label (grep-reused where
  // an existing key already fit; "Category"/"Section"/"Resource"/"Set" were new).
  const TYPE_LABELS: Record<string, string> = {
    section: t("Section"),
    category: t("Category"),
    "product-type": t("Product type"),
    product: t("Product"),
    resource: t("Resource"),
    set: t("Set"),
    pool: t("Resource pool"),
  };

  const rows = trash.data ?? [];

  async function restore(item: TrashItem) {
    try {
      await api.restoreTrash(item.type, item.id);
      toast.success(t("Restored."));
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Failed."));
    }
  }

  async function purge(item: TrashItem) {
    if (
      !(await confirm({
        message: t("Permanently delete “{{label}}”? This cannot be undone.", {
          label: item.label,
        }),
        confirmLabel: t("Delete permanently"),
        danger: true,
      }))
    )
      return;
    try {
      await api.purgeTrashItem(item.type, item.id);
      toast.success(t("Deleted."));
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Failed."));
    }
  }

  async function emptyAll() {
    if (
      !(await confirm({
        message: t(
          "Empty the trash? Everything listed here that you may manage will be permanently deleted. This cannot be undone.",
        ),
        confirmLabel: t("Empty trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.emptyTrash();
      toast.success(t("Trash emptied."));
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Failed."));
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      {user?.is_staff && <RetentionEditor />}

      <div className="mb-4 mt-6 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Trash")}</h2>
        {rows.length > 0 && (
          <button
            type="button"
            onClick={emptyAll}
            className="rounded-full border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 transition-colors duration-150 hover:bg-red-50 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/40"
          >
            {t("Empty trash")}
          </button>
        )}
      </div>

      {trash.loading && <Loading />}
      {trash.error && <ErrorBox message={trash.error} />}

      {trash.data && rows.length === 0 && <Empty label={t("Trash is empty.")} />}

      {trash.data && rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("Type")}</th>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Deleted")}</th>
                <th className="px-3 py-2">{t("Auto-deletes")}</th>
                <th className="px-3 py-2 text-right" />
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr
                  key={`${item.type}-${item.id}`}
                  className="border-t border-slate-100 dark:border-slate-800"
                >
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {TYPE_LABELS[item.type] ?? item.type}
                  </td>
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">
                    {item.label}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    <div>{fmtDateTime(item.deleted_at, i18n.language)}</div>
                    {item.deleted_by && (
                      <div className="text-xs text-slate-400 dark:text-slate-500">
                        {t("Deleted by {{name}}", { name: item.deleted_by })}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {t("Auto-deletes {{date}}", { date: fmtDateTime(item.purge_at, i18n.language) })}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5">
                      <button
                        type="button"
                        onClick={() => restore(item)}
                        title={t("Restore")}
                        aria-label={t("Restore")}
                        className="inline-flex items-center justify-center rounded-md p-2 text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                      >
                        <RotateCcw aria-hidden className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => purge(item)}
                        title={t("Delete permanently")}
                        aria-label={t("Delete permanently")}
                        className="inline-flex items-center justify-center rounded-md p-2 text-slate-400 transition-colors duration-150 hover:bg-red-50 hover:text-red-600 dark:text-slate-500 dark:hover:bg-red-950/40 dark:hover:text-red-300"
                      >
                        <Trash2 aria-hidden className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RetentionEditor() {
  const { t } = useTranslation();
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const setting = useFetch<TrashSetting>(() => api.getTrashSetting(), []);
  useEffect(() => {
    if (setting.data) setDays(setting.data.retention_days);
  }, [setting.data]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.updateTrashSetting({ retention_days: days });
      setDays(res.retention_days);
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Failed.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Retention")}</h2>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t("Trashed items are permanently deleted automatically once this many days have passed.")}
      </p>
      <form onSubmit={save} className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-500 dark:text-slate-400">
          {t("Keep deleted items for {{count}} day", { count: days })}
          <input
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(Number(e.target.value || 0))}
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
