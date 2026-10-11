// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { usePagedList } from "../usePagedList";
import { ManageTabs } from "../components/ManageTabs";
import { ListToolbar } from "../components/ListToolbar";
import { Pager } from "../components/Pager";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import type { ManageProduct, Paginated, ProductType } from "../types";
import {
  EMPTY_PRODUCT,
  ProductForm,
  productToInput,
} from "../components/ProductForm";

export function AdminProductsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [editing, setEditing] = useState<ManageProduct | "new" | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const products = usePagedList<ManageProduct>(
    ({ page, search }) =>
      api.listManagedProducts({ page, search, productType: typeFilter || undefined }),
    typeFilter,
  );
  const types = useFetch<Paginated<ProductType>>(() => api.listProductTypes({ pageSize: 2000 }), []);

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = products.reload;

  async function remove(product: ManageProduct) {
    if (
      !(await confirm({
        message: t("Move product “{{title}}” to the trash?", { title: product.title }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteProduct(product.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const productTypes = types.data?.results ?? [];

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Products")}</h2>
        {editing === null && productTypes.length > 0 && (
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
          >
            {t("+ New product")}
          </button>
        )}
      </div>

      {editing === null && productTypes.length === 0 && !types.loading && (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Create a product type first — products are based on one.")}
        </p>
      )}

      {editing !== null && (
        <ProductForm
          initial={
            editing === "new"
              ? { ...EMPTY_PRODUCT }
              : productToInput(editing)
          }
          initialImages={editing === "new" ? [] : editing.images}
          productId={editing === "new" ? null : editing.id}
          poolDefaults={editing === "new" ? [] : (editing.pool_duration_defaults ?? [])}
          productTypes={productTypes}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {editing === null && (
        <div className="mb-3 flex flex-wrap gap-2 text-sm">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label={t("Filter by product type")}
            className="rounded-md border border-slate-300 px-2 py-1 text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">{t("All product types")}</option>
            {productTypes.map((pt) => (
              <option key={pt.id} value={pt.id}>
                {pt.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {editing === null && (
        <ListToolbar
          search={products.search}
          onSearch={products.setSearch}
        />
      )}

      {(products.loading || types.loading) && <Loading />}
      {products.error && <ErrorBox message={products.error} />}

      {editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Title")}</th>
                <th className="px-3 py-2">{t("Type")}</th>
                <th className="px-3 py-2">{t("Lending")}</th>
                <th className="px-3 py-2">{t("Resources")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {products.items.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => setEditing(p)}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{p.title}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.product_type_name}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.lending_type}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.resource_count}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
                      <EditButton onClick={() => setEditing(p)} />
                      <DeleteButton onClick={() => remove(p)} />
                    </div>
                  </td>
                </tr>
              ))}
              {products.items.length === 0 && !products.loading && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t("No products yet.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {editing === null && <Pager list={products} />}
    </div>
  );
}

