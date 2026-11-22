// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ListToolbar } from "../components/ListToolbar";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { ReorderControls } from "../components/ReorderControls";
import { useReorder } from "../useReorder";
import { poolAccent } from "../poolAccent";
import type { Paginated, ResourcePool } from "../types";
import { ACCENT_LABELS, EMPTY_POOL, PoolForm, toPoolInput } from "../components/PoolForm";
import { PersonalPoolBadge } from "../components/PersonalPoolBadge";

export function AdminPoolsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<ResourcePool | "new" | null>(null);
  const [reordering, setReordering] = useState(false);
  const [query, setQuery] = useState("");
  // Load the full list (reordering needs every row); filter/search client-side.
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000 }),
    [version],
  );
  const rows = pools.data?.results ?? [];
  const reorder = useReorder(rows, api.reorderPools);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const filtered = query.trim()
    ? rows.filter(
        (p) =>
          p.name.toLowerCase().includes(query.trim().toLowerCase()) ||
          p.pool_id.toLowerCase().includes(query.trim().toLowerCase()),
      )
    : rows;
  const displayRows = reordering ? reorder.order : filtered;

  async function remove(pool: ResourcePool) {
    if (
      !(await confirm({
        message: t("Move pool “{{name}}” to the trash?", { name: pool.name }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deletePool(pool.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Pools")}</h2>
        {editing === null && (
          <div className="flex gap-2">
            {rows.length > 1 && (
              <button
                type="button"
                onClick={() => setReordering((r) => !r)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                  reordering
                    ? "bg-slate-900 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                {reordering ? t("Done") : t("Reorder")}
              </button>
            )}
            {!reordering && (
              <button
                type="button"
                onClick={() => setEditing("new")}
                className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("+ New pool")}
              </button>
            )}
          </div>
        )}
      </div>

      {reordering && (
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
          {t(
            "Drag rows to reorder, or use the ↑ / ↓ buttons. New pools are always added at the end. Changes are saved automatically.",
          )}
        </p>
      )}

      {editing !== null && (
        <PoolForm
          initial={editing === "new" ? EMPTY_POOL : toPoolInput(editing)}
          poolId={editing === "new" ? null : editing.id}
          personal={editing !== "new" && editing.is_personal}
          accessGroups={editing === "new" ? [] : editing.access_groups ?? []}
          onClose={() => setEditing(null)}
          onPoolPersisted={refetch}
          onSaved={() => setEditing(null)}
        />
      )}

      {editing === null && !reordering && rows.length > 0 && (
        <ListToolbar
          search={query}
          onSearch={setQuery}
          count={filtered.length}
          hidePager
          placeholder={t("Search pools…")}
        />
      )}

      {pools.loading && <Loading />}
      {pools.error && <ErrorBox message={pools.error} />}

      {pools.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Accent")}</th>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Visibility")}</th>
                <th className="px-3 py-2">{t("Active")}</th>
                <th className="px-3 py-2 text-right">
                  {reordering ? t("Order") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((pool, i) => (
                <tr
                  key={pool.id}
                  draggable={reordering}
                  onDragStart={reordering ? (e) => reorder.onDragStart(pool.id, e) : undefined}
                  onDragEnter={reordering ? () => reorder.onDragEnter(pool.id) : undefined}
                  onDragOver={reordering ? (e) => e.preventDefault() : undefined}
                  onDrop={reordering ? reorder.onDrop : undefined}
                  onDragEnd={reordering ? reorder.onDragEnd : undefined}
                  onClick={reordering ? undefined : () => setEditing(pool)}
                  className={`border-t border-slate-100 dark:border-slate-800 ${
                    reordering
                      ? "cursor-grab bg-white dark:bg-slate-900"
                      : "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800"
                  }`}
                >
                  <td className="px-3 py-2">
                    <span
                      aria-hidden
                      title={t(ACCENT_LABELS[pool.accent_color || "neutral"])}
                      className={`inline-block h-4 w-4 rounded-full ${poolAccent(pool.accent_color).dot}`}
                    />
                    <span className="sr-only">{t(ACCENT_LABELS[pool.accent_color || "neutral"])}</span>
                  </td>
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">
                    {pool.name}
                    {pool.is_personal && <PersonalPoolBadge owner={pool.owner} className="ml-2" />}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {pool.is_restricted ? t("Restricted") : t("Everyone signed in")}
                  </td>
                  <td className="px-3 py-2">
                    {pool.is_active ? (
                      <span className="text-green-700 dark:text-green-400">●</span>
                    ) : (
                      <span className="text-slate-300 dark:text-slate-300">●</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {reordering ? (
                      <div className="flex justify-end">
                        <ReorderControls
                          label={pool.name}
                          isFirst={i === 0}
                          isLast={i === displayRows.length - 1}
                          onUp={() => reorder.move(pool.id, -1)}
                          onDown={() => reorder.move(pool.id, 1)}
                        />
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
                        <EditButton onClick={() => setEditing(pool)} />
                        <DeleteButton onClick={() => remove(pool)} />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {displayRows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t("No pools yet.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
