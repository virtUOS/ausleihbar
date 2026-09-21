// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import type { ImageAction } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ListToolbar } from "../components/ListToolbar";
import { MultiSelectList } from "../components/MultiSelectList";
import { ImageCropField } from "../components/ImageCropField";
import { TranslatableField } from "@basicbar/ui";
import { ReorderControls } from "../components/ReorderControls";
import { symbolFor } from "../emoji";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { useReorder } from "../useReorder";
import type {
  ManageCategory,
  ManageCategoryInput,
  ManageProduct,
  ManageSection,
  Paginated,
} from "../types";

const EMPTY: ManageCategoryInput = {
  title_de: "",
  title_en: "",
  description_de: "",
  description_en: "",
  image: "",
  products: [],
  sections: [],
};

function toInput(c: ManageCategory): ManageCategoryInput {
  return {
    title_de: c.title_de ?? "",
    title_en: c.title_en ?? "",
    description_de: c.description_de ?? "",
    description_en: c.description_en ?? "",
    image: c.image,
    products: c.products,
    sections: c.sections,
  };
}

export function AdminCategoriesPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<ManageCategory | "new" | null>(null);
  const [reordering, setReordering] = useState(false);
  const [query, setQuery] = useState("");
  // Load the full list (reordering needs every row); filter/search client-side.
  const categories = useFetch<Paginated<ManageCategory>>(
    () => api.listManagedCategories({ pageSize: 2000 }),
    [version],
  );
  const products = useFetch<Paginated<ManageProduct>>(
    () => api.listManagedProducts({ pageSize: 2000 }),
    [],
  );
  const sections = useFetch<Paginated<ManageSection>>(
    () => api.listManagedSections({ pageSize: 2000 }),
    [],
  );
  const rows = categories.data?.results ?? [];
  const reorder = useReorder(rows, api.reorderCategories);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const filtered = query.trim()
    ? rows.filter((c) => c.title.toLowerCase().includes(query.trim().toLowerCase()))
    : rows;
  const displayRows = reordering ? reorder.order : filtered;

  async function remove(category: ManageCategory) {
    if (
      !(await confirm({
        message: t("Move category “{{title}}” to the trash?", { title: category.title }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteCategory(category.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const allProducts = products.data?.results ?? [];
  const allSections = sections.data?.results ?? [];

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Administration")}</h1>
      <AdminTabs />

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Categories")}</h2>
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
                {t("+ New category")}
              </button>
            )}
          </div>
        )}
      </div>

      {reordering && (
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          {t(
            "Drag rows to reorder, or use the ↑ / ↓ buttons. New categories are always added at the end. Changes are saved automatically.",
          )}
        </p>
      )}

      {editing !== null && (
        <CategoryForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          categoryId={editing === "new" ? null : editing.id}
          allProducts={allProducts}
          allSections={allSections}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {editing === null && !reordering && rows.length > 0 && (
        <ListToolbar
          search={query}
          onSearch={setQuery}
          count={filtered.length}
          hidePager
          placeholder={t("Search categories…")}
        />
      )}

      {(categories.loading || products.loading) && <Loading />}
      {categories.error && <ErrorBox message={categories.error} />}

      {categories.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("Title")}</th>
                <th className="px-3 py-2">{t("Products")}</th>
                <th className="px-3 py-2 text-right">
                  {reordering ? t("Order") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((c, i) => (
                <tr
                  key={c.id}
                  draggable={reordering}
                  onDragStart={reordering ? () => reorder.onDragStart(c.id) : undefined}
                  onDragEnter={reordering ? () => reorder.onDragEnter(c.id) : undefined}
                  onDragOver={reordering ? (e) => e.preventDefault() : undefined}
                  onDrop={reordering ? reorder.onDrop : undefined}
                  className={`border-t border-slate-100 dark:border-slate-800 ${
                    reordering ? "cursor-grab bg-white dark:bg-slate-900" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{c.title}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{c.product_count}</td>
                  <td className="px-3 py-2 text-right">
                    {reordering ? (
                      <div className="flex justify-end">
                        <ReorderControls
                          label={c.title}
                          isFirst={i === 0}
                          isLast={i === displayRows.length - 1}
                          onUp={() => reorder.move(c.id, -1)}
                          onDown={() => reorder.move(c.id, 1)}
                        />
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center justify-end gap-0.5">
                          <EditButton onClick={() => setEditing(c)} />
                          <DeleteButton onClick={() => remove(c)} />
                        </div>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {displayRows.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                    {t("No categories yet.")}
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

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function CategoryForm({
  initial,
  categoryId,
  allProducts,
  allSections,
  onClose,
  onSaved,
}: {
  initial: ManageCategoryInput;
  categoryId: number | null;
  allProducts: ManageProduct[];
  allSections: ManageSection[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ManageCategoryInput>(initial);
  const [imageAction, setImageAction] = useState<ImageAction>(null);
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

  // Move a product within the saved display order (delta -1 up / +1 down).
  function moveProduct(id: number, delta: number) {
    setForm((f) => {
      const order = [...f.products];
      const from = order.indexOf(id);
      const to = from + delta;
      if (from === -1 || to < 0 || to >= order.length) return f;
      [order[from], order[to]] = [order[to], order[from]];
      return { ...f, products: order };
    });
  }

  function toggleSection(id: number) {
    setForm((f) => ({
      ...f,
      sections: f.sections.includes(id)
        ? f.sections.filter((s) => s !== id)
        : [...f.sections, id],
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved =
        categoryId === null
          ? await api.createCategory(form)
          : await api.updateCategory(categoryId, form);
      await api.applyImage("categories", saved.id, imageAction);
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
        {categoryId === null
          ? t("New category")
          : t("Edit {{title}}", { title: initial.title_de })}
      </h3>

      <TranslatableField
        label={t("Title")}
        required
        values={{ de: form.title_de, en: form.title_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`title_${lang}`]: v }))}
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
      <div className="block text-xs text-slate-500 dark:text-slate-400">
        {t("Image")}
        <div className="mt-1">
          <ImageCropField
            currentUrl={form.image}
            aspect={4 / 3}
            fallback={symbolFor(form.title_de ?? "")}
            onChange={setImageAction}
          />
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">{t("Sections (Sparten)")}</p>
        <MultiSelectList
          options={allSections.map((s) => ({ id: s.id, label: s.title }))}
          selected={form.sections}
          onToggle={toggleSection}
          placeholder={t("Search sections…")}
          emptyText={t("No sections available.")}
        />
      </div>

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

      {form.products.length > 1 && (
        <div>
          <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
            {t("Order in the category")}
          </p>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {form.products.map((id, index) => {
              const product = allProducts.find((p) => p.id === id);
              return (
                <li key={id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="min-w-0 truncate text-slate-800 dark:text-slate-100">
                    {product ? product.title : `#${id}`}
                  </span>
                  <ReorderControls
                    label={product ? product.title : `#${id}`}
                    isFirst={index === 0}
                    isLast={index === form.products.length - 1}
                    onUp={() => moveProduct(id, -1)}
                    onDown={() => moveProduct(id, 1)}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

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
