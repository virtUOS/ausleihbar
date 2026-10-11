// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { setPoolScopeLocked } from "../poolScope";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { Link, useNavigate } from "react-router-dom";
import { Pencil, Copy, Trash2, Star } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { usePagedList } from "../usePagedList";
import { ManageTabs } from "../components/ManageTabs";
import { ListToolbar } from "../components/ListToolbar";
import { Pager } from "../components/Pager";
import { ErrorBox, Loading } from "../components/Status";
import { SortableTh } from "../components/SortableTh";
import { KebabMenu } from "../components/KebabMenu";
import { RESOURCE_STATUSES } from "../types";
import type {
  ManageProduct,
  ManageResource,
  ManageResourceInput,
  Paginated,
  ProductType,
  ResourcePool,
} from "../types";
import {
  EMPTY_RESOURCE,
  ResourceForm,
  resourceToInput,
  statusLabel,
} from "../components/ResourceForm";

const STATUS_BADGE: Record<string, string> = {
  available: "text-green-700 dark:text-green-300",
  blocked: "text-amber-600 dark:text-amber-300",
  defective: "text-red-600 dark:text-red-300",
  retired: "text-slate-400 dark:text-slate-300",
};

/** Inline status editor for the inventory table. Marking a working unit
 *  defective runs the rebooking/notify flow (and asks for a note); returning a
 *  repaired unit to service uses the repair flow; other changes are a plain
 *  status update. */
function StatusCell({
  resource,
  onChanged,
}: {
  resource: ManageResource;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  async function change(next: string) {
    if (next === resource.status) return;
    setBusy(true);
    try {
      if (next === "defective" && resource.status === "available") {
        const note = window.prompt(
          t("Mark defective — what's wrong? (optional)"),
          "",
        );
        if (note === null) return; // cancelled
        const res = await api.markResourceDefective(resource.id, note.trim());
        if (res.unfulfilled) {
          window.alert(
            t(
              "{{rebooked}} booking(s) moved; {{unfulfilled}} could not be moved — those borrowers were notified.",
              { rebooked: res.rebooked, unfulfilled: res.unfulfilled },
            ),
          );
        }
      } else if (next === "available" && resource.status === "defective") {
        await api.markResourceAvailable(resource.id);
      } else {
        await api.updateResource(resource.id, {
          status: next as ManageResourceInput["status"],
          defect_note: next === "defective" ? resource.defect_note : "",
        });
      }
      onChanged();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={resource.status}
        disabled={busy}
        onChange={(e) => change(e.target.value)}
        aria-label={t("Status")}
        className={`rounded-md border border-slate-300 bg-white px-1.5 py-0.5 text-sm font-medium disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 ${
          STATUS_BADGE[resource.status] ?? ""
        }`}
      >
        {RESOURCE_STATUSES.map((s) => (
          <option key={s} value={s}>
            {statusLabel(s)}
          </option>
        ))}
      </select>
      {resource.status === "defective" && resource.defect_note && (
        <span className="text-xs font-normal text-slate-400 dark:text-slate-300">
          ({resource.defect_note})
        </span>
      )}
    </div>
  );
}

type EditState =
  | { kind: "new" }
  | { kind: "edit"; resource: ManageResource }
  | { kind: "duplicate"; resource: ManageResource }
  | null;

export function AdminInventoryPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<EditState>(null);
  // The open edit form is client-side state a scope switch (remount) would discard.
  const formOpen = editing !== null;
  useEffect(() => {
    setPoolScopeLocked(formOpen);
    return () => setPoolScopeLocked(false);
  }, [formOpen]);
  const [poolFilter, setPoolFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [ordering, setOrdering] = useState("inventory_number");

  const resources = usePagedList<ManageResource>(
    ({ page, search }) =>
      api.listInventory({
        page,
        search,
        pool: poolFilter ? Number(poolFilter) : undefined,
        status: statusFilter || undefined,
        ordering,
      }),
    `${poolFilter}|${statusFilter}|${ordering}`,
  );
  const products = useFetch<Paginated<ManageProduct>>(
    () => api.listManagedProducts({ pageSize: 2000 }),
    [],
  );
  const productTypes = useFetch<Paginated<ProductType>>(
    () => api.listProductTypes({ pageSize: 2000 }),
    [],
  );
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000, lending: true }),
    [],
  );

  if (user && !user.is_lender) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>
    );
  }

  const refetch = resources.reload;
  const allProducts = products.data?.results ?? [];
  const allPools = pools.data?.results ?? [];

  async function remove(resource: ManageResource) {
    if (
      !(await confirm({
        message: t("Move resource “{{number}}” to the trash?", {
          number: resource.inventory_number,
        }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteResource(resource.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs showPoolScope />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Resources")}</h2>
        {editing === null && allProducts.length > 0 && allPools.length > 0 && (
          <button
            type="button"
            onClick={() => setEditing({ kind: "new" })}
            className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
          >
            {t("+ New resource")}
          </button>
        )}
      </div>

      {editing === null && (allProducts.length === 0 || allPools.length === 0) &&
        !products.loading && !pools.loading && (
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
            {t("Create at least one product and one resource pool first.")}
          </p>
        )}

      {editing === null && (
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <select
            value={poolFilter}
            onChange={(e) => setPoolFilter(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">{t("All pools")}</option>
            {allPools.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">{t("All statuses")}</option>
            {RESOURCE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </div>
      )}

      {editing !== null && (
        <ResourceForm
          initial={
            editing.kind === "new"
              ? { ...EMPTY_RESOURCE }
              : editing.kind === "duplicate"
                ? { ...resourceToInput(editing.resource), inventory_number: "", qr_code_id: "", serial_number: "" }
                : resourceToInput(editing.resource)
          }
          resourceId={editing.kind === "edit" ? editing.resource.id : null}
          autoSuggest={editing.kind !== "edit"}
          allProducts={allProducts}
          productTypes={productTypes.data?.results ?? []}
          allPools={allPools}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {editing === null && (
        <ListToolbar
          search={resources.search}
          onSearch={resources.setSearch}
          placeholder={t("Search inventory number, serial, product…")}
        />
      )}

      {(resources.loading || products.loading || pools.loading) && <Loading />}
      {resources.error && <ErrorBox message={resources.error} />}

      {editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <SortableTh field="inventory_number" label={t("Inventory no.")} active={ordering} onSort={setOrdering} />
                <SortableTh field="product__title" label={t("Product")} active={ordering} onSort={setOrdering} />
                <SortableTh field="resource_pool__name" label={t("Pool")} active={ordering} onSort={setOrdering} />
                <SortableTh field="status" label={t("Status")} active={ordering} onSort={setOrdering} />
                <SortableTh field="condition_rating" label={t("Condition")} active={ordering} onSort={setOrdering} />
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {resources.items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => navigate(`/manage/inventory/${r.id}`)}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40"
                >
                  <td className="px-3 py-2 font-medium">
                    <Link
                      to={`/manage/inventory/${r.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-slate-900 hover:underline dark:text-slate-100"
                    >
                      {r.inventory_number}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{r.product_title}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{r.pool_name}</td>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <StatusCell resource={r} onChanged={refetch} />
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 text-slate-700 dark:text-slate-200">
                      <Star className="h-3.5 w-3.5 fill-current text-brand-500" />
                      {r.condition_rating}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                    <KebabMenu
                      items={[
                        { label: t("Edit"), icon: Pencil, onClick: () => setEditing({ kind: "edit", resource: r }) },
                        { label: t("Duplicate"), icon: Copy, onClick: () => setEditing({ kind: "duplicate", resource: r }) },
                        { label: t("Delete"), icon: Trash2, danger: true, onClick: () => remove(r) },
                      ]}
                    />
                  </td>
                </tr>
              ))}
              {resources.items.length === 0 && !resources.loading && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t("No resources match.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {editing === null && <Pager list={resources} />}
    </div>
  );
}
