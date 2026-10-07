// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Fragment, useMemo, useState } from "react";
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
import { OrderList, moveId } from "../components/OrderList";
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
import { FormActionBar, sameFormValue } from "../components/FormActionBar";
import { PATH_SEPARATOR, categoryTree, pathLabel, subtreeIds, toggleSortedId } from "../categories";

const EMPTY: ManageCategoryInput = {
  name_de: "",
  name_en: "",
  description_de: "",
  description_en: "",
  parent: null,
  sections: [],
  product_order: [],
};

function toInput(c: ManageCategory): ManageCategoryInput {
  return {
    name_de: c.name_de ?? "",
    name_en: c.name_en ?? "",
    description_de: c.description_de ?? "",
    description_en: c.description_en ?? "",
    parent: c.parent,
    sections: [...c.sections].sort((a, b) => a - b),
    // `products` is the direct products in their current shop order.
    product_order: c.products,
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
  const categories = useFetch<ManageCategory[]>(() => api.listManagedCategories(), [version]);
  const sections = useFetch<Paginated<ManageSection>>(
    () => api.listManagedSections({ pageSize: 2000 }),
    [],
  );
  const rows = useMemo(() => categories.data ?? [], [categories.data]);
  const tree = useMemo(() => categoryTree(rows), [rows]);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const needle = query.trim().toLowerCase();
  const searching = !reordering && needle !== "";
  const matches = searching
    ? tree.ordered.filter((c) => pathLabel(c).toLowerCase().includes(needle))
    : [];

  async function remove(category: ManageCategory) {
    if (
      !(await confirm({
        message: t("Move category “{{name}}” to the trash?", { name: category.name }),
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

  const rowProps = {
    reordering,
    onEdit: (c: ManageCategory) => setEditing(c),
    onDelete: remove,
  };

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
                onClick={() => {
                  // Leaving reorder mode reloads the saved positions.
                  if (reordering) refetch();
                  setReordering((r) => !r);
                }}
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

      {editing === null && !reordering && (
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
          {t(
            "Categories are the shop navigation: section › category › subcategory › product. Top-level categories are placed in sections; products are assigned to categories in the product form.",
          )}
        </p>
      )}

      {reordering && (
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
          {t(
            "Drag rows to reorder, or use the ↑ / ↓ buttons. Categories move only among their siblings (same parent). Changes are saved automatically.",
          )}
        </p>
      )}

      {editing !== null && (
        <CategoryForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          category={editing === "new" ? null : editing}
          tree={tree}
          allSections={sections.data?.results ?? []}
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
          count={searching ? matches.length : tree.ordered.length}
          hidePager
          placeholder={t("Search categories…")}
        />
      )}

      {(categories.loading || sections.loading) && <Loading />}
      {categories.error && <ErrorBox message={categories.error} />}

      {categories.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Products")}</th>
                <th className="px-3 py-2">{t("Subcategories")}</th>
                <th className="px-3 py-2 text-right">{reordering ? t("Order") : ""}</th>
              </tr>
            </thead>
            <tbody>
              {searching ? (
                matches.map((c) => (
                  <CategoryRow
                    key={c.id}
                    category={c}
                    showPath
                    isFirst
                    isLast
                    {...rowProps}
                  />
                ))
              ) : (
                <CategoryRows parent={null} childrenOf={tree.childrenOf} {...rowProps} />
              )}
              {(searching ? matches.length === 0 : tree.ordered.length === 0) && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {searching ? t("No categories available.") : t("No categories yet.")}
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

type RowActions = {
  reordering: boolean;
  onEdit: (c: ManageCategory) => void;
  onDelete: (c: ManageCategory) => void;
};

/** The children of `parent` (recursively), reorderable among themselves. */
function CategoryRows({
  parent,
  childrenOf,
  ...actions
}: { parent: number | null; childrenOf: Map<number | null, ManageCategory[]> } & RowActions) {
  const items = childrenOf.get(parent) ?? [];
  const reorder = useReorder(items, (ids) => api.reorderCategories(parent, ids));
  const shown = actions.reordering ? reorder.order : items;
  return (
    <>
      {shown.map((c, i) => (
        <Fragment key={c.id}>
          <CategoryRow
            category={c}
            isFirst={i === 0}
            isLast={i === shown.length - 1}
            reorder={reorder}
            {...actions}
          />
          <CategoryRows parent={c.id} childrenOf={childrenOf} {...actions} />
        </Fragment>
      ))}
    </>
  );
}

function CategoryRow({
  category: c,
  showPath = false,
  isFirst,
  isLast,
  reorder,
  reordering,
  onEdit,
  onDelete,
}: {
  category: ManageCategory;
  showPath?: boolean;
  isFirst: boolean;
  isLast: boolean;
  reorder?: ReturnType<typeof useReorder<ManageCategory>>;
} & RowActions) {
  const { t } = useTranslation();
  const drag = reordering && reorder;
  const parentPath = c.path.slice(0, -1).join(PATH_SEPARATOR);
  return (
    <tr
      draggable={!!drag}
      onDragStart={drag ? (e) => reorder.onDragStart(c.id, e) : undefined}
      onDragEnter={drag ? () => reorder.onDragEnter(c.id) : undefined}
      onDragOver={drag ? (e) => e.preventDefault() : undefined}
      onDrop={drag ? reorder.onDrop : undefined}
      onDragEnd={drag ? reorder.onDragEnd : undefined}
      onClick={reordering ? undefined : () => onEdit(c)}
      className={`border-t border-slate-100 dark:border-slate-800 ${
        reordering
          ? "cursor-grab bg-white dark:bg-slate-900"
          : "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800"
      }`}
    >
      <td
        className="py-2 pr-3 font-medium text-slate-900 dark:text-slate-100"
        style={{ paddingLeft: `${0.75 + (showPath ? 0 : c.depth) * 1.25}rem` }}
      >
        {/* Depth in text for screen readers; the indent is visual only. */}
        <span className="sr-only">
          {c.depth === 0
            ? t("Top-level category")
            : t("Level {{level}}, in {{path}}", { level: c.depth + 1, path: parentPath })}
          {": "}
        </span>
        {c.depth > 0 && !showPath && (
          <span aria-hidden className="mr-1.5 text-slate-400 dark:text-slate-500">
            ↳
          </span>
        )}
        {showPath && parentPath && (
          <span aria-hidden className="font-normal text-slate-500 dark:text-slate-400">
            {parentPath}
            {PATH_SEPARATOR}
          </span>
        )}
        {c.name}
      </td>
      <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{c.product_count}</td>
      <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{c.child_count}</td>
      <td className="px-3 py-2 text-right">
        {drag ? (
          <div className="flex justify-end">
            <ReorderControls
              label={pathLabel(c)}
              isFirst={isFirst}
              isLast={isLast}
              onUp={() => reorder.move(c.id, -1)}
              onDown={() => reorder.move(c.id, 1)}
            />
          </div>
        ) : (
          <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
            <EditButton onClick={() => onEdit(c)} />
            <DeleteButton onClick={() => onDelete(c)} />
          </div>
        )}
      </td>
    </tr>
  );
}

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function CategoryForm({
  initial,
  category,
  tree,
  allSections,
  onClose,
  onSaved,
}: {
  initial: ManageCategoryInput;
  category: ManageCategory | null;
  tree: ReturnType<typeof categoryTree>;
  allSections: ManageSection[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ManageCategoryInput>(initial);
  const [imageAction, setImageAction] = useState<ImageAction>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = !sameFormValue(form, initial) || imageAction !== null;
  const hasProducts = initial.product_order.length > 0;
  // Titles for the product order list (only needed when there are products).
  const products = useFetch<Paginated<ManageProduct> | null>(
    () => (hasProducts ? api.listManagedProducts({ pageSize: 2000 }) : Promise.resolve(null)),
    [hasProducts],
  );

  // A category can't move below itself or one of its descendants.
  const excluded = category ? subtreeIds(category.id, tree.childrenOf) : new Set<number>();
  const parentOptions = tree.ordered.filter((c) => !excluded.has(c.id));
  const isTopLevel = form.parent === null;

  function toggleSection(id: number) {
    setForm((f) => ({ ...f, sections: toggleSortedId(f.sections, id) }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    // Only top-level categories sit in sections: moving below a parent
    // clears them in the same request.
    const payload: ManageCategoryInput = { ...form, sections: isTopLevel ? form.sections : [] };
    try {
      const saved =
        category === null
          ? await api.createCategory(payload)
          : await api.updateCategory(category.id, payload);
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
      className="mb-5 space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {category === null ? t("New category") : t("Edit {{title}}", { title: initial.name_de })}
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
        onChange={(lang, v) => setForm((f) => ({ ...f, [`description_${lang}`]: v }))}
        inputClass={inputClass}
      />

      <label className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Parent category")}
        <select
          value={form.parent ?? ""}
          onChange={(e) =>
            setForm((f) => ({ ...f, parent: e.target.value === "" ? null : Number(e.target.value) }))
          }
          className={`mt-1 ${inputClass}`}
        >
          <option value="">{t("— None (top-level category) —")}</option>
          {parentOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {pathLabel(c)}
            </option>
          ))}
        </select>
      </label>
      {!isTopLevel && initial.sections.length > 0 && (
        <p role="status" className="text-xs text-amber-800 dark:text-amber-300">
          {t("Moving below a parent category removes this category from its sections.")}
        </p>
      )}

      <div className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Image")}
        <div className="mt-1">
          <ImageCropField
            currentUrl={category?.image ?? null}
            aspect={4 / 3}
            fallback={symbolFor(form.name_de ?? "")}
            onChange={setImageAction}
          />
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Sections (Sparten)")}</p>
        {isTopLevel ? (
          <MultiSelectList
            options={allSections.map((s) => ({ id: s.id, label: s.title }))}
            selected={form.sections}
            onToggle={toggleSection}
            placeholder={t("Search sections…")}
            emptyText={t("No sections available.")}
          />
        ) : (
          <p className="text-xs text-slate-600 dark:text-slate-300">
            {t("Only top-level categories can be placed in a section. A subcategory appears in the sections of its top-level category.")}
          </p>
        )}
      </div>

      {category !== null && (
        <div>
          <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">
            {hasProducts
              ? t("Products directly in this category. Assign products in the product form; subcategories keep their own order.")
              : t("No products directly in this category yet. Assign products in the product form.")}
          </p>
          <OrderList
            label={t("Order of the products")}
            ids={form.product_order}
            labelFor={(id) =>
              products.data?.results.find((p) => p.id === id)?.title ?? `#${id}`
            }
            onMove={(id, delta) =>
              setForm((f) => ({ ...f, product_order: moveId(f.product_order, id, delta) }))
            }
            onReorder={(next) => setForm((f) => ({ ...f, product_order: next }))}
          />
        </div>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <FormActionBar saving={busy} onCancel={onClose} dirty={dirty} />
    </form>
  );
}
