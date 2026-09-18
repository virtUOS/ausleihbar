// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { usePagedList } from "../usePagedList";
import { ManageTabs } from "../components/ManageTabs";
import { ListToolbar } from "../components/ListToolbar";
import { Pager } from "../components/Pager";
import { MultiSelectList } from "../components/MultiSelectList";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { TranslatableField } from "@basicbar/ui";
import type {
  ManageProduct,
  ManageSet,
  ManageSetInput,
  Paginated,
  ResourcePool,
} from "../types";

const EMPTY: ManageSetInput = {
  name_de: "",
  name_en: "",
  description_de: "",
  description_en: "",
  resource_pool: null,
  products: [],
};

function toInput(s: ManageSet): ManageSetInput {
  return {
    name_de: s.name_de ?? "",
    name_en: s.name_en ?? "",
    description_de: s.description_de ?? "",
    description_en: s.description_en ?? "",
    resource_pool: s.resource_pool,
    products: s.products,
  };
}

export function AdminSetsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const { user } = useAuth();
  const [editing, setEditing] = useState<ManageSet | "new" | null>(null);
  const sets = usePagedList<ManageSet>(
    ({ page, search }) => api.listSets({ page, search }),
  );
  const products = useFetch<Paginated<ManageProduct>>(
    () => api.listManagedProducts({ pageSize: 2000 }),
    [],
  );
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000 }),
    [],
  );

  if (user && !user.is_lender) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>
    );
  }

  const refetch = sets.reload;

  async function remove(set: ManageSet) {
    if (
      !(await confirm({
        message: t("Delete set “{{name}}”?", { name: set.name }),
        confirmLabel: t("Delete"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteSet(set.id);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const allProducts = products.data?.results ?? [];
  const allPools = pools.data?.results ?? [];

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t(
          "A set is a list of products that are sensibly lent together (e.g. a podcast kit). Borrowers can later add a whole set to their cart.",
        )}
      </p>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Sets")}</h2>
        {editing === null && (
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
          >
            {t("+ New set")}
          </button>
        )}
      </div>

      {editing !== null && (
        <SetForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          setId={editing === "new" ? null : editing.id}
          allProducts={allProducts}
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
          search={sets.search}
          onSearch={sets.setSearch}
        />
      )}

      {(sets.loading || products.loading) && <Loading />}
      {sets.error && <ErrorBox message={sets.error} />}

      {editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Pool")}</th>
                <th className="px-3 py-2">{t("Products")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sets.items.map((s) => (
                <tr key={s.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{s.name}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {s.pool_name ?? <span className="text-slate-400 dark:text-slate-500">—</span>}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{s.product_count}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5">
                      <EditButton onClick={() => setEditing(s)} />
                      <DeleteButton onClick={() => remove(s)} />
                    </div>
                  </td>
                </tr>
              ))}
              {sets.items.length === 0 && !sets.loading && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                    {t("No sets yet.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {editing === null && <Pager list={sets} />}
    </div>
  );
}

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function SetForm({
  initial,
  setId,
  allProducts,
  allPools,
  onClose,
  onSaved,
}: {
  initial: ManageSetInput;
  setId: number | null;
  allProducts: ManageProduct[];
  allPools: ResourcePool[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ManageSetInput>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleProduct(id: number) {
    setForm((f) => ({
      ...f,
      products: f.products.includes(id)
        ? f.products.filter((p) => p !== id)
        : [...f.products, id],
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (setId === null) await api.createSet(form);
      else await api.updateSet(setId, form);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mb-5 space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900"
    >
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {setId === null
          ? t("New set")
          : t("Edit {{name}}", { name: initial.name_de })}
      </h3>

      <TranslatableField
        label={t("Name")}
        required
        values={{ de: form.name_de, en: form.name_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`name_${lang}`]: v }))}
        inputClass={inputClass}
      />
      <TranslatableField
        label={t("Description")}
        multiline
        values={{ de: form.description_de, en: form.description_en }}
        onChange={(lang, v) =>
          setForm((f) => ({ ...f, [`description_${lang}`]: v }))
        }
        inputClass={inputClass}
      />

      <label className="block text-xs text-slate-500 dark:text-slate-400">
        {t("Pool")}
        <select
          value={form.resource_pool ?? ""}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              resource_pool: e.target.value ? Number(e.target.value) : null,
            }))
          }
          className={`mt-1 ${inputClass}`}
        >
          <option value="">{t("— No pool (not bookable) —")}</option>
          {allPools.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.room ? ` · ${p.room}` : ""}
            </option>
          ))}
        </select>
        <span className="mt-1 block text-[11px] text-slate-400 dark:text-slate-500">
          {t(
            "A set is booked from one pool; all its products must have resources there.",
          )}
        </span>
      </label>

      <div>
        <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">{t("Products")}</p>
        <MultiSelectList
          options={allProducts.map((p) => ({
            id: p.id,
            label: p.title,
            sublabel: p.product_type_name,
          }))}
          selected={form.products}
          onToggle={toggleProduct}
          placeholder={t("Search products…")}
          emptyText={t("No products available.")}
        />
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Saving…") : t("Save")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {t("Cancel")}
        </button>
      </div>
    </form>
  );
}
