// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Minus, Plus, X } from "lucide-react";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { usePagedList } from "../usePagedList";
import { ManageTabs } from "../components/ManageTabs";
import { ListToolbar } from "../components/ListToolbar";
import { Pager } from "../components/Pager";
import { GroupedProductPicker } from "../components/GroupedProductPicker";
import { ProductImagesField, applyGalleryPlan, galleryPlanDirty } from "../components/ProductImagesField";
import type { GalleryPlan } from "../components/ProductImagesField";
import { CategoryPicker, usePickableCategories } from "../components/CategoryPicker";
import { ReorderControls } from "../components/ReorderControls";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { TranslatableField } from "@basicbar/ui";
import { RichTextEditor } from "@basicbar/ui/rich-text-editor";
import { moveBefore, startDrag } from "../useReorder";
import { toggleSortedId } from "../categories";
import { poolAccent } from "../poolAccent";
import type {
  ManageSet,
  ManageSetInput,
  ManageSetItem,
  Paginated,
  SetImage,
  ResourcePool,
  SetPoolProduct,
} from "../types";
import { FormActionBar, sameFormValue } from "../components/FormActionBar";

const EMPTY: ManageSetInput = {
  name_de: "",
  name_en: "",
  description_de: "",
  description_en: "",
  resource_pool: null,
  categories: [],
  items: [],
};

function toInput(s: ManageSet): ManageSetInput {
  return {
    name_de: s.name_de ?? "",
    name_en: s.name_en ?? "",
    description_de: s.description_de ?? "",
    description_en: s.description_en ?? "",
    resource_pool: s.resource_pool,
    categories: [...s.categories].sort((a, b) => a - b),
    items: s.items.map((i) => ({ product: i.product, quantity: i.quantity })),
  };
}

const MAX_QUANTITY = 999;
const NO_IMAGES: SetImage[] = [];

export function AdminSetsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [editing, setEditing] = useState<ManageSet | "new" | null>(null);
  const sets = usePagedList<ManageSet>(
    ({ page, search }) => api.listSets({ page, search }),
  );
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000 }),
    [],
  );
  // Lenders may only choose pools they manage (admins: every pool).
  const isAdmin = !!user?.is_staff;
  const lendingPools = useFetch<Paginated<ResourcePool> | null>(
    () => (isAdmin ? Promise.resolve(null) : api.listPools({ pageSize: 2000, lending: true })),
    [isAdmin],
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
        message: t("Move set “{{name}}” to the trash?", { name: set.name }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteSet(set.id);
      refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const allPools = pools.data?.results ?? [];
  const poolById = new Map(allPools.map((p) => [p.id, p]));
  const choosablePools = isAdmin ? allPools : (lendingPools.data?.results ?? []);

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <p className="mb-4 text-xs text-slate-600 dark:text-slate-300">
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
          initialImages={editing === "new" ? NO_IMAGES : editing.images}
          initialItems={editing === "new" ? [] : editing.items}
          initialPoolName={editing === "new" ? null : editing.pool_name}
          allPools={allPools}
          choosablePools={choosablePools}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
          onImageError={(message) => toast.error(message)}
        />
      )}

      {editing === null && (
        <ListToolbar
          search={sets.search}
          onSearch={sets.setSearch}
        />
      )}

      {(sets.loading || pools.loading) && <Loading />}
      {sets.error && <ErrorBox message={sets.error} />}

      {editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="w-12 px-3 py-2">
                  <span className="sr-only">{t("Image")}</span>
                </th>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Pool")}</th>
                <th className="px-3 py-2">{t("Products")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sets.items.map((s) => {
                const pool = s.resource_pool !== null ? poolById.get(s.resource_pool) : undefined;
                return (
                  <tr
                    key={s.id}
                    onClick={() => setEditing(s)}
                    className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                  >
                    <td className="px-3 py-2">
                      <div className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-md bg-slate-100 text-lg dark:bg-slate-800">
                        {s.image ? (
                          <img src={s.image} alt="" className="h-full w-full object-cover" />
                        ) : (
                          <span aria-hidden>🎒</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{s.name}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                      {s.resource_pool === null ? (
                        <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
                          {t("Pool missing")}
                        </span>
                      ) : (
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs ${poolAccent(pool?.accent_color).border}`}
                        >
                          <span
                            aria-hidden
                            className={`h-2 w-2 shrink-0 rounded-full ${poolAccent(pool?.accent_color).dot}`}
                          />
                          {s.pool_name}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{s.product_count}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
                        <EditButton onClick={() => setEditing(s)} />
                        <DeleteButton onClick={() => remove(s)} />
                      </div>
                    </td>
                  </tr>
                );
              })}
              {sets.items.length === 0 && !sets.loading && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
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

const stepButton =
  "inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-300 text-slate-700 hover:bg-slate-100 disabled:opacity-30 disabled:hover:bg-transparent dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

function SetForm({
  initial,
  setId,
  initialImages,
  initialItems,
  initialPoolName,
  allPools,
  choosablePools,
  onClose,
  onSaved,
  onImageError,
}: {
  initial: ManageSetInput;
  setId: number | null;
  initialImages: SetImage[];
  initialItems: ManageSetItem[];
  initialPoolName: string | null;
  /** Every pool (colours, current pool). */
  allPools: ResourcePool[];
  /** Pools the user may choose for the set. */
  choosablePools: ResourcePool[];
  onClose: () => void;
  onSaved: () => void;
  /** The set was saved, but its images could not all be stored. */
  onImageError: (message: string) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ManageSetInput>(initial);
  // Latest gallery plan from ProductImagesField, applied after save.
  const galleryPlan = useRef<GalleryPlan>({ order: [], deletes: [] });
  const [galleryDirty, setGalleryDirty] = useState(false);
  const onGalleryChange = useCallback(
    (plan: GalleryPlan) => {
      galleryPlan.current = plan;
      setGalleryDirty(galleryPlanDirty(plan, initialImages));
    },
    [initialImages],
  );
  const {
    options: categoryOptions,
    pickableIds,
    loaded: categoriesLoaded,
  } = usePickableCategories();
  const categoriesLabelId = useId();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = !sameFormValue(form, initial) || galleryDirty;
  const pool = form.resource_pool;
  const poolSelectId = useId();
  const poolHintId = useId();

  // Products a set in the chosen pool may contain, with their unit count.
  const poolProducts = useFetch<{ products: SetPoolProduct[] }>(
    () => (pool === null ? Promise.resolve({ products: [] }) : api.listSetPoolProducts(pool, setId)),
    [pool],
  );
  const inPool = useMemo(
    () => new Map((poolProducts.data?.products ?? []).map((p) => [p.id, p])),
    [poolProducts.data],
  );
  // Without a pool nothing is checked yet (saving is blocked anyway).
  const loaded = pool !== null && poolProducts.data !== null;

  // Titles of the selected products: the stored items plus the pool's list.
  // Titles of the selected products: the stored items plus every picked one
  // (kept across pool changes), then the current pool's list.
  const [pickedTitles, setPickedTitles] = useState<Map<number, string>>(
    () => new Map(initialItems.map((i) => [i.product, i.title])),
  );
  const titles = useMemo(() => {
    const map = new Map(pickedTitles);
    for (const p of inPool.values()) map.set(p.id, p.title);
    return map;
  }, [pickedTitles, inPool]);
  const titleOf = (id: number) => titles.get(id) ?? `#${id}`;

  // Units in the pool; until the list arrives, the stored count for the stored pool.
  function unitsOf(id: number): number | null {
    if (loaded) return inPool.get(id)?.unit_count ?? 0;
    if (pool !== null && pool === initial.resource_pool) {
      return initialItems.find((i) => i.product === id)?.units_in_pool ?? null;
    }
    return null;
  }

  const missing = loaded ? form.items.filter((i) => !inPool.has(i.product)) : [];
  const selectedIds = new Set(form.items.map((i) => i.product));
  const pickable = (poolProducts.data?.products ?? []).filter((p) => !selectedIds.has(p.id));

  // Pools to choose from: active ones plus the set's current pool.
  // Choosable active pools; the set's current pool is always listed (a
  // lender may keep a pool they don't manage), even when not loaded.
  const poolOptions: { id: number; label: string }[] = choosablePools
    .filter((p) => p.is_active || p.id === initial.resource_pool)
    .map((p) => ({ id: p.id, label: p.room ? `${p.name} · ${p.room}` : p.name }));
  if (initial.resource_pool !== null && !poolOptions.some((p) => p.id === initial.resource_pool)) {
    const current = allPools.find((p) => p.id === initial.resource_pool);
    poolOptions.unshift({
      id: initial.resource_pool,
      label: current
        ? current.room ? `${current.name} · ${current.room}` : current.name
        : (initialPoolName ?? `#${initial.resource_pool}`),
    });
  }
  const chosenPool = allPools.find((p) => p.id === pool);

  function setItems(update: (items: ManageSetInput["items"]) => ManageSetInput["items"]) {
    setForm((f) => ({ ...f, items: update(f.items) }));
  }

  function addProduct(product: SetPoolProduct) {
    setItems((items) => [...items, { product: product.id, quantity: 1 }]);
    setPickedTitles((m) => new Map(m).set(product.id, product.title));
    setQuery("");
  }

  function removeProduct(id: number) {
    setItems((items) => items.filter((i) => i.product !== id));
  }

  /** Highest quantity "+" may reach: the product's units in the pool (once
   *  known), never below 1 so a product can stay listed. */
  function maxQuantity(id: number): number {
    const units = unitsOf(id);
    return units === null ? MAX_QUANTITY : Math.max(1, Math.min(MAX_QUANTITY, units));
  }

  function changeQuantity(id: number, delta: number) {
    const max = maxQuantity(id);
    setItems((items) =>
      items.map((i) => {
        if (i.product !== id) return i;
        if (delta > 0) return { ...i, quantity: Math.max(i.quantity, Math.min(max, i.quantity + delta)) };
        // Stepping down from above the cap lands on the cap right away.
        return { ...i, quantity: i.quantity > max ? max : Math.max(1, i.quantity + delta) };
      }),
    );
  }

  function moveItem(index: number, delta: number) {
    setItems((items) => {
      const target = index + delta;
      if (target < 0 || target >= items.length) return items;
      return moveBefore(items, index, target);
    });
  }

  // Drag-and-drop reordering of the items (live preview, kept on drop).
  const dragId = useRef<number | null>(null);
  const dragStart = useRef<ManageSetInput["items"] | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);

  function onDragEnter(id: number) {
    const from = dragId.current;
    if (from === null || from === id) return;
    setItems((items) => {
      const fromIndex = items.findIndex((i) => i.product === from);
      const toIndex = items.findIndex((i) => i.product === id);
      if (fromIndex < 0 || toIndex < 0) return items;
      return moveBefore(items, fromIndex, toIndex);
    });
  }

  function endDrag(keep: boolean) {
    if (dragId.current === null) return;
    const previous = dragStart.current;
    dragId.current = null;
    dragStart.current = null;
    setDraggingId(null);
    if (!keep && previous) setItems(() => previous);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Only pickable categories are offered and sent; the backend keeps a
      // set's links to trashed or hidden categories by itself. On edit they
      // are sent only when changed here (ids are kept sorted), so a stale or
      // partial tree never wipes them (like the product form).
      const chosenCategories = form.categories.filter((id) => pickableIds.has(id));
      let saved: { id: number };
      if (setId === null) {
        saved = await api.createSet({ ...form, categories: chosenCategories });
      } else {
        const { categories, ...rest } = form;
        const payload: Partial<ManageSetInput> = { ...rest };
        const unchanged =
          categories.length === initial.categories.length &&
          categories.every((id, i) => id === initial.categories[i]);
        if (!unchanged) payload.categories = chosenCategories;
        saved = await api.updateSet(setId, payload);
      }
      try {
        // Apply the gallery plan: delete removed, upload new (in order), reorder.
        await applyGalleryPlan(galleryPlan.current, {
          upload: (file) => api.uploadSetImage(saved.id, file),
          remove: (imageId) => api.deleteSetImage(saved.id, imageId),
          reorder: (ids) => api.reorderSetImages(saved.id, ids),
        });
      } catch (err) {
        // The set itself is saved — leave the form and report the images.
        onImageError(err instanceof Error ? err.message : t("Image upload failed"));
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  // Quantities above the pool's units (e.g. stored before units were retired)
  // must be reduced before saving.
  const overCap = form.items.filter((i) => {
    const units = unitsOf(i.product);
    return units !== null && !(loaded && !inPool.has(i.product)) && i.quantity > units;
  });
  // Saving waits for the category tree, so the picker shows the real links.
  const blocked =
    pool === null || !loaded || !categoriesLoaded || missing.length > 0 || overCap.length > 0;

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

      <div className="text-xs text-slate-600 dark:text-slate-300">
        <label htmlFor={poolSelectId}>
          {t("Pool")} <span aria-hidden>*</span>
        </label>
        <div className="mt-1 flex items-center gap-2">
          <span
            aria-hidden
            className={`h-3 w-3 shrink-0 rounded-full ${
              chosenPool ? poolAccent(chosenPool.accent_color).dot : "border border-slate-300 dark:border-slate-600"
            }`}
          />
          <select
            id={poolSelectId}
            required
            aria-describedby={poolHintId}
            value={pool ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                resource_pool: e.target.value ? Number(e.target.value) : null,
              }))
            }
            className={inputClass}
          >
            <option value="" disabled>
              {t("— Choose a pool —")}
            </option>
            {poolOptions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <p id={poolHintId} className="mt-1 text-[11px] text-slate-500 dark:text-slate-300">
          {t(
            "A set is booked from one pool; all its products must have resources there.",
          )}
        </p>
      </div>

      <TranslatableField
        label={t("Name")}
        required
        values={{ de: form.name_de, en: form.name_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`name_${lang}`]: v }))}
        inputClass={inputClass}
      />

      <section aria-labelledby="set-items-heading" className="space-y-2">
        <h4 id="set-items-heading" className="text-xs text-slate-600 dark:text-slate-300">
          {t("Products in this set")}
        </h4>
        {form.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-300">
            {t("No products yet — add them from the list below.")}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {form.items.map((item, index) => {
              const title = titleOf(item.product);
              const units = unitsOf(item.product);
              const notInPool = loaded && !inPool.has(item.product);
              const short = units !== null && !notInPool && item.quantity > units;
              return (
                <li
                  key={item.product}
                  draggable
                  onDragStart={(e) => {
                    startDrag(e, item.product);
                    dragId.current = item.product;
                    dragStart.current = form.items;
                    setDraggingId(item.product);
                  }}
                  onDragEnter={() => onDragEnter(item.product)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => endDrag(true)}
                  onDragEnd={() => endDrag(false)}
                  className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm ${
                    notInPool
                      ? "bg-red-50 dark:bg-red-950/30"
                      : draggingId === item.product
                        ? "bg-brand-50 dark:bg-slate-800"
                        : "bg-white dark:bg-slate-900"
                  }`}
                >
                  <ReorderControls
                    label={title}
                    isFirst={index === 0}
                    isLast={index === form.items.length - 1}
                    onUp={() => moveItem(index, -1)}
                    onDown={() => moveItem(index, 1)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-slate-900 dark:text-slate-100">
                      {title}
                    </span>
                    {notInPool ? (
                      <span className="text-xs font-medium text-red-700 dark:text-red-300">
                        {t("Not in this pool")}
                      </span>
                    ) : (
                      units !== null && (
                        <span
                          className={`text-xs ${
                            short
                              ? "font-medium text-red-700 dark:text-red-300"
                              : "text-slate-500 dark:text-slate-300"
                          }`}
                        >
                          {t("{{needed}} needed · {{inPool}} in pool", {
                            needed: item.quantity,
                            inPool: units,
                          })}
                        </span>
                      )
                    )}
                  </span>
                  <span
                    role="group"
                    aria-label={t("Quantity of {{name}}", { name: title })}
                    className="flex items-center gap-1"
                  >
                    <button
                      type="button"
                      onClick={() => changeQuantity(item.product, -1)}
                      disabled={item.quantity <= 1}
                      aria-label={t("Decrease quantity of {{product}}", { product: title })}
                      className={stepButton}
                    >
                      <Minus aria-hidden className="h-3.5 w-3.5" />
                    </button>
                    <output
                      aria-live="polite"
                      className="w-8 text-center font-semibold tabular-nums text-slate-900 dark:text-slate-100"
                    >
                      {item.quantity}
                    </output>
                    <button
                      type="button"
                      onClick={() => changeQuantity(item.product, 1)}
                      disabled={item.quantity >= maxQuantity(item.product)}
                      aria-label={t("Increase quantity of {{product}}", { product: title })}
                      className={stepButton}
                    >
                      <Plus aria-hidden className="h-3.5 w-3.5" />
                    </button>
                  </span>
                  <button
                    type="button"
                    onClick={() => removeProduct(item.product)}
                    aria-label={t("Remove {{name}}", { name: title })}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <X aria-hidden className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {missing.length > 0 && (
          <p role="alert" className="text-xs text-red-700 dark:text-red-300">
            {t("Remove the products that are not in this pool to save the set.")}
          </p>
        )}
        {overCap.length > 0 && (
          <p role="alert" className="text-xs text-red-700 dark:text-red-300">
            {t("Reduce the quantities to the units in the pool to save the set.")}
          </p>
        )}

        {pool === null ? (
          <p className="text-xs text-slate-500 dark:text-slate-300">
            {t("Choose a pool first to add products.")}
          </p>
        ) : poolProducts.loading ? (
          <Loading />
        ) : poolProducts.error ? (
          <ErrorBox message={poolProducts.error} />
        ) : (
          <GroupedProductPicker
            products={pickable}
            query={query}
            onQueryChange={setQuery}
            onPick={addProduct}
            renderMeta={(p) => t("{{units}} in pool", { units: p.unit_count })}
            placeholder={t("Search products…")}
          />
        )}
      </section>

      <div className="block text-xs text-slate-600 dark:text-slate-300">
        {t("Images")}
        <div className="mt-1">
          <ProductImagesField initialImages={initialImages} onChange={onGalleryChange} />
        </div>
      </div>

      <TranslatableField
        label={t("Description")}
        values={{ de: form.description_de, en: form.description_en }}
        onChange={(lang, v) =>
          setForm((f) => ({ ...f, [`description_${lang}`]: v }))
        }
        inputClass={inputClass}
        format="html"
        renderInput={({ value, onChange, id, lang, labelId, describedBy }) => (
          <RichTextEditor
            key={lang}
            id={id}
            labelledBy={labelId}
            describedBy={describedBy}
            value={value}
            onChange={onChange}
            onUploadImage={api.uploadRichImage}
          />
        )}
      />

      <div role="group" aria-labelledby={categoriesLabelId}>
        <p id={categoriesLabelId} className="mb-1 text-xs text-slate-600 dark:text-slate-300">
          {t("Categories — where the set appears in the shop navigation.")}
        </p>
        <CategoryPicker
          options={categoryOptions}
          pickableIds={pickableIds}
          selected={form.categories}
          onToggle={(id) =>
            setForm((f) => ({ ...f, categories: toggleSortedId(f.categories, id) }))
          }
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-300">
          {error}
        </p>
      )}

      <FormActionBar
        saving={busy}
        disabled={blocked}
        onCancel={onClose}
        dirty={dirty}
        surface="card"
      />
    </form>
  );
}
