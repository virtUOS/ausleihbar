// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Copy, Package, Pencil, Plus, Star, Trash2 } from "lucide-react";
import { localizedText } from "@basicbar/ui";
import { setPoolScopeLocked } from "../poolScope";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api, type ItemPropertyFilter } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { usePagedList } from "../usePagedList";
import { formatDate, formatPeriodEnd } from "../dates";
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
  Paginated,
  ProductItemSummary,
  ProductType,
  ResourcePool,
} from "../types";
import {
  EMPTY_RESOURCE,
  ResourceForm,
  resourceToInput,
  statusLabel,
} from "../components/ResourceForm";
import { ResourceStatusCell } from "../components/ResourceStatusCell";
import { EMPTY_PRODUCT, ProductForm, productToInput } from "../components/ProductForm";

/** Items listed per expanded product (one request, no paging inside a panel). */
const ITEMS_PER_PRODUCT = 200;

type EditState =
  | { kind: "new-product" }
  | { kind: "edit-product"; product: ManageProduct }
  | { kind: "new-item"; productId: number | null }
  | { kind: "edit-item"; resource: ManageResource }
  | { kind: "duplicate-item"; resource: ManageResource }
  | null;

/** Item-level filters shared by the product list and the expanded panels. */
interface ItemFilters extends ItemPropertyFilter {
  pool?: number;
  status?: string;
}

const SELECT_CLASS =
  "rounded-md border border-slate-300 px-2 py-1 text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

const CHIP = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium";
const CHIP_GREEN = `${CHIP} bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300`;
const CHIP_AMBER = `${CHIP} bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300`;
const CHIP_RED = `${CHIP} bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300`;
const CHIP_SLATE = `${CHIP} bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300`;
const CHIP_BRAND = `${CHIP} bg-brand-100 text-slate-900`;

/** "Gegenstände": products that expand to their physical items (#88). */
export function ManageItemsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [editing, setEditing] = useState<EditState>(null);
  // The open edit form is client-side state a scope switch (remount) would discard.
  const formOpen = editing !== null;
  useEffect(() => {
    setPoolScopeLocked(formOpen);
    return () => setPoolScopeLocked(false);
  }, [formOpen]);

  const [poolFilter, setPoolFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [attrKey, setAttrKey] = useState("");
  const [attrMode, setAttrMode] = useState<"before" | "empty">("before");
  const [attrDate, setAttrDate] = useState("");
  const [itemOrdering, setItemOrdering] = useState("inventory_number");
  // Bumped after an item change so the open panels refetch.
  const [itemsVersion, setItemsVersion] = useState(0);
  // Bumped after a product change so the full product list (pickers) reloads.
  const [productsVersion, setProductsVersion] = useState(0);

  const productTypes = useFetch<Paginated<ProductType>>(
    () => api.listProductTypes({ pageSize: 2000 }),
    [],
  );
  const products = useFetch<Paginated<ManageProduct>>(
    () => api.listManagedProducts({ pageSize: 2000 }),
    [productsVersion],
  );
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000, lending: true }),
    [],
  );
  const allTypes = productTypes.data?.results ?? [];
  const allProducts = products.data?.results ?? [];
  const allPools = pools.data?.results ?? [];

  // Every date property filled in per item, across all product types.
  const dateProps = useMemo(() => {
    const seen = new Map<string, string>();
    for (const pt of allTypes) {
      for (const a of pt.attribute_schema ?? []) {
        if (a.scope === "device" && a.type === "date" && !seen.has(a.key)) {
          seen.set(a.key, localizedText(a.label) || a.key);
        }
      }
    }
    return [...seen].map(([key, label]) => ({ key, label }));
  }, [allTypes]);
  const attrLabel = dateProps.find((p) => p.key === attrKey)?.label ?? attrKey;

  // The property filter only narrows once it is complete.
  const attrActive = !!attrKey && (attrMode === "empty" || !!attrDate);
  const filters: ItemFilters = {
    pool: poolFilter ? Number(poolFilter) : undefined,
    status: statusFilter || undefined,
    ...(attrActive
      ? {
          attr: attrKey,
          attrBefore: attrMode === "before" ? attrDate : undefined,
          attrEmpty: attrMode === "empty",
        }
      : {}),
  };
  const itemFilterActive = !!(filters.pool || filters.status || filters.attr);
  const filtersKey = `${poolFilter}|${statusFilter}|${typeFilter}|${
    attrActive ? `${attrKey}|${attrMode}|${attrDate}` : ""
  }`;

  const list = usePagedList<ProductItemSummary>(
    ({ page, search }) =>
      api.listInventoryByProduct({
        page,
        search,
        productType: typeFilter ? Number(typeFilter) : undefined,
        ...filters,
      }),
    filtersKey,
  );

  // Products whose expansion the user toggled. With an item filter active all
  // listed products start expanded, so a toggle collapses them instead. A
  // filter change starts over.
  const [toggled, setToggled] = useState<Set<number>>(new Set());
  const searchActive = searchTerms.length > 0;
  useEffect(() => setToggled(new Set()), [filtersKey, searchActive]);
  // A search term expands the listed products too, so matching items show.
  const searchTerms = list.search
    .replace(/,/g, " ")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  const autoExpand = itemFilterActive || searchTerms.length > 0;
  const isExpanded = (id: number) => (autoExpand ? !toggled.has(id) : toggled.has(id));
  function toggle(id: number) {
    setToggled((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // A property column sort makes no sense once that property is gone.
  useEffect(() => {
    if (itemOrdering.replace(/^-/, "").startsWith("attr:") && itemOrdering.replace(/^-?attr:/, "") !== attrKey) {
      setItemOrdering("inventory_number");
    }
  }, [attrKey, itemOrdering]);

  if (user && !user.is_lender) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>
    );
  }

  // After an item change: product summaries and open panels, not the full
  // product list (that one only changes with products).
  function refreshAll() {
    list.reload();
    setItemsVersion((v) => v + 1);
  }
  function refreshProducts() {
    refreshAll();
    setProductsVersion((v) => v + 1);
  }

  async function editProduct(id: number) {
    try {
      setEditing({ kind: "edit-product", product: await api.getManagedProduct(id) });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Loading failed."));
    }
  }

  async function removeProduct(product: ProductItemSummary) {
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
      refreshProducts();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  async function removeItem(resource: ManageResource) {
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
      refreshAll();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const canAddItem = allProducts.length > 0 && allPools.length > 0;
  const closeForm = () => setEditing(null);
  const savedForm = () => {
    const productForm = editing?.kind === "new-product" || editing?.kind === "edit-product";
    setEditing(null);
    if (productForm) refreshProducts();
    else refreshAll();
  };

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs showPoolScope />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Items")}</h2>
        {editing === null && (
          <div className="flex flex-wrap gap-2">
            {allTypes.length > 0 && (
              <button
                type="button"
                onClick={() => setEditing({ kind: "new-product" })}
                className="rounded-full border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-800"
              >
                {t("+ New product")}
              </button>
            )}
            {canAddItem && (
              <button
                type="button"
                onClick={() => setEditing({ kind: "new-item", productId: null })}
                className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("+ New item")}
              </button>
            )}
          </div>
        )}
      </div>

      {editing === null && allTypes.length === 0 && !productTypes.loading && (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Create a product type first — products are based on one.")}
        </p>
      )}
      {editing === null && allTypes.length > 0 && !canAddItem && !products.loading && !pools.loading && (
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          {t("Create at least one product and one resource pool first.")}
        </p>
      )}

      {(editing?.kind === "new-product" || editing?.kind === "edit-product") && (
        <ProductForm
          initial={editing.kind === "new-product" ? { ...EMPTY_PRODUCT } : productToInput(editing.product)}
          initialImages={editing.kind === "new-product" ? [] : editing.product.images}
          productId={editing.kind === "new-product" ? null : editing.product.id}
          poolDefaults={
            editing.kind === "new-product" ? [] : (editing.product.pool_duration_defaults ?? [])
          }
          productTypes={allTypes}
          onClose={closeForm}
          onSaved={savedForm}
        />
      )}

      {(editing?.kind === "new-item" || editing?.kind === "edit-item" || editing?.kind === "duplicate-item") && (
        <ResourceForm
          initial={
            editing.kind === "new-item"
              ? { ...EMPTY_RESOURCE, ...(editing.productId ? { product: editing.productId } : {}) }
              : editing.kind === "duplicate-item"
                ? { ...resourceToInput(editing.resource), inventory_number: "", qr_code_id: "", serial_number: "" }
                : resourceToInput(editing.resource)
          }
          resourceId={editing.kind === "edit-item" ? editing.resource.id : null}
          autoSuggest={editing.kind !== "edit-item"}
          allProducts={allProducts}
          productTypes={allTypes}
          allPools={allPools}
          onClose={closeForm}
          onSaved={savedForm}
        />
      )}

      {editing === null && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
            <select
              value={poolFilter}
              onChange={(e) => setPoolFilter(e.target.value)}
              aria-label={t("Filter by pool")}
              className={SELECT_CLASS}
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
              aria-label={t("Filter by status")}
              className={SELECT_CLASS}
            >
              <option value="">{t("All statuses")}</option>
              {RESOURCE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              aria-label={t("Filter by product type")}
              className={SELECT_CLASS}
            >
              <option value="">{t("All product types")}</option>
              {allTypes.map((pt) => (
                <option key={pt.id} value={pt.id}>
                  {pt.name}
                </option>
              ))}
            </select>
            {dateProps.length > 0 && (
              <span className="inline-flex flex-wrap items-center gap-2">
                <select
                  value={attrKey}
                  onChange={(e) => setAttrKey(e.target.value)}
                  aria-label={t("Filter by property")}
                  className={SELECT_CLASS}
                >
                  <option value="">{t("No property filter")}</option>
                  {dateProps.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.label}
                    </option>
                  ))}
                </select>
                {attrKey && (
                  <select
                    value={attrMode}
                    onChange={(e) => setAttrMode(e.target.value as "before" | "empty")}
                    aria-label={t("Property condition")}
                    className={SELECT_CLASS}
                  >
                    <option value="before">{t("older than")}</option>
                    <option value="empty">{t("empty")}</option>
                  </select>
                )}
                {attrKey && attrMode === "before" && (
                  <input
                    type="date"
                    value={attrDate}
                    onChange={(e) => setAttrDate(e.target.value)}
                    aria-label={t("Date")}
                    className={SELECT_CLASS}
                  />
                )}
              </span>
            )}
          </div>
          <ListToolbar
            search={list.search}
            onSearch={list.setSearch}
            placeholder={t("Search product, inventory or serial number…")}
          />
        </>
      )}

      {(list.loading || productTypes.loading || pools.loading) && <Loading />}
      {list.error && <ErrorBox message={list.error} />}

      {editing === null && (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {list.items.map((p) => {
            const open = isExpanded(p.id);
            const panelId = `product-items-${p.id}`;
            return (
              <li key={p.id}>
                <div className="flex items-center gap-2 pr-2 hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <button
                    type="button"
                    onClick={() => toggle(p.id)}
                    aria-expanded={open}
                    aria-controls={open ? panelId : undefined}
                    className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2.5 text-left"
                  >
                    <ChevronRight
                      aria-hidden="true"
                      className={`h-4 w-4 shrink-0 text-slate-400 transition-transform duration-150 dark:text-slate-400 ${
                        open ? "rotate-90" : ""
                      }`}
                    />
                    {p.image ? (
                      <img src={p.image} alt="" className="h-10 w-10 shrink-0 rounded-md object-cover" />
                    ) : (
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-100 dark:bg-slate-800">
                        <Package aria-hidden="true" className="h-5 w-5 text-slate-400 dark:text-slate-400" />
                      </span>
                    )}
                    <span className="min-w-0 flex-1 basis-40">
                      <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                        {p.title}
                      </span>
                      <span className="block text-xs text-slate-500 dark:text-slate-400">
                        {p.product_type_name} · {t("{{count}} item", { count: p.item_count })}
                      </span>
                    </span>
                    <ProductChips product={p} />
                  </button>
                  <KebabMenu
                    label={t("Actions for {{title}}", { title: p.title })}
                    items={[
                      { label: t("Edit product"), icon: Pencil, onClick: () => editProduct(p.id) },
                      ...(allPools.length > 0
                        ? [{ label: t("Add item"), icon: Plus, onClick: () => setEditing({ kind: "new-item", productId: p.id }) }]
                        : []),
                      ...(p.item_count === 0
                        ? [{ label: t("Delete"), icon: Trash2, danger: true, onClick: () => removeProduct(p) }]
                        : []),
                    ]}
                  />
                </div>
                {open && (
                  <div id={panelId} className="border-t border-slate-100 bg-slate-50/60 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/40">
                    <ProductItems
                      productId={p.id}
                      filters={filters}
                      filtersKey={filtersKey}
                      ordering={itemOrdering}
                      onSort={setItemOrdering}
                      propertyKey={attrKey}
                      propertyLabel={attrLabel}
                      version={itemsVersion}
                      highlightTerms={searchTerms}
                      onChanged={refreshAll}
                      onEdit={(r) => setEditing({ kind: "edit-item", resource: r })}
                      onDuplicate={(r) => setEditing({ kind: "duplicate-item", resource: r })}
                      onDelete={removeItem}
                    />
                  </div>
                )}
              </li>
            );
          })}
          {list.items.length === 0 && !list.loading && (
            <li className="px-3 py-6 text-center text-sm text-slate-600 dark:text-slate-300">
              {t("No products match.")}
            </li>
          )}
        </ul>
      )}
      {editing === null && <Pager list={list} />}
    </div>
  );
}

/** Status summary of a product's items; zero counts are left out. */
function ProductChips({ product: p }: { product: ProductItemSummary }) {
  const { t } = useTranslation();
  return (
    <span className="flex w-full flex-wrap gap-1 pl-7 sm:w-auto sm:justify-end sm:pl-0">
      {p.counts.available > 0 && (
        <span className={CHIP_GREEN}>{t("{{count}} available", { count: p.counts.available })}</span>
      )}
      {p.lent_out > 0 && (
        <span className={CHIP_BRAND}>
          {t("{{count}} lent out", { count: p.lent_out })}
          {p.next_return && <> · {t("until {{date}}", { date: formatPeriodEnd(p.next_return) })}</>}
        </span>
      )}
      {p.overdue > 0 && (
        <span className={`${CHIP_RED} font-semibold`}>
          {t("{{count}} overdue", { count: p.overdue })}
          {p.overdue_since && <> · {t("due {{date}}", { date: formatPeriodEnd(p.overdue_since) })}</>}
        </span>
      )}
      {p.counts.blocked > 0 && (
        <span className={CHIP_AMBER}>{t("{{count}} blocked", { count: p.counts.blocked })}</span>
      )}
      {p.counts.defective > 0 && (
        <span className={CHIP_RED}>{t("{{count}} defective", { count: p.counts.defective })}</span>
      )}
      {p.counts.retired > 0 && (
        <span className={CHIP_SLATE}>{t("{{count}} retired", { count: p.counts.retired })}</span>
      )}
    </span>
  );
}

/** The items of one expanded product, filtered like the product list. */
function ProductItems({
  productId,
  filters,
  filtersKey,
  ordering,
  onSort,
  propertyKey,
  propertyLabel,
  version,
  highlightTerms,
  onChanged,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  productId: number;
  filters: ItemFilters;
  /** Changes whenever `filters` does (the object itself is rebuilt each render). */
  filtersKey: string;
  ordering: string;
  onSort: (next: string) => void;
  /** Selected date property: shown as an extra, sortable column. */
  propertyKey: string;
  propertyLabel: string;
  version: number;
  /** Lower-cased search terms; rows whose numbers contain one are highlighted. */
  highlightTerms: string[];
  onChanged: () => void;
  onEdit: (r: ManageResource) => void;
  onDuplicate: (r: ManageResource) => void;
  onDelete: (r: ManageResource) => void;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState<Paginated<ManageResource> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listInventory({ product: productId, ...filters, ordering, pageSize: ITEMS_PER_PRODUCT })
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t("Loading failed."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `filters` is rebuilt every render; `filtersKey` tracks its content.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId, filtersKey, ordering, version, i18n.resolvedLanguage]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return loading ? <Loading /> : null;

  const items = data.results;
  const columns = propertyKey ? 6 : 5;
  return (
    <div className={loading ? "opacity-60 transition-opacity" : ""}>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
            <tr>
              <SortableTh field="inventory_number" label={t("Inventory no.")} active={ordering} onSort={onSort} />
              <SortableTh field="resource_pool__name" label={t("Pool")} active={ordering} onSort={onSort} />
              <SortableTh field="status" label={t("Status")} active={ordering} onSort={onSort} />
              <SortableTh field="condition_rating" label={t("Condition")} active={ordering} onSort={onSort} />
              {propertyKey && (
                <SortableTh field={`attr:${propertyKey}`} label={propertyLabel} active={ordering} onSort={onSort} />
              )}
              <th className="px-3 py-2">
                <span className="sr-only">{t("Actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => {
              const matched =
                highlightTerms.length > 0 &&
                highlightTerms.some(
                  (term) =>
                    r.inventory_number.toLowerCase().includes(term) ||
                    (r.serial_number ?? "").toLowerCase().includes(term),
                );
              const propValue = propertyKey ? r.attributes?.[propertyKey] : undefined;
              return (
                <tr
                  key={r.id}
                  onClick={() => navigate(`/manage/inventory/${r.id}`)}
                  className={`cursor-pointer border-t border-slate-100 dark:border-slate-800 ${
                    matched
                      ? "bg-brand-50 dark:bg-brand-900/30"
                      : "hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  }`}
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
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{r.pool_name}</td>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <ResourceStatusCell resource={r} onChanged={onChanged} />
                    {r.lent_until && (
                      <div
                        className={`mt-0.5 text-xs ${
                          r.overdue
                            ? "font-semibold text-red-700 dark:text-red-300"
                            : "text-slate-500 dark:text-slate-400"
                        }`}
                      >
                        {r.overdue
                          ? t("overdue, due {{date}}", { date: formatPeriodEnd(r.lent_until) })
                          : t("lent out until {{date}}", { date: formatPeriodEnd(r.lent_until) })}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 text-slate-700 dark:text-slate-200">
                      <Star aria-hidden="true" className="h-3.5 w-3.5 fill-current text-brand-500" />
                      {r.condition_rating}
                    </span>
                  </td>
                  {propertyKey && (
                    <td className="px-3 py-2 tabular-nums text-slate-600 dark:text-slate-300">
                      {typeof propValue === "string" && propValue ? formatDate(propValue) : "–"}
                    </td>
                  )}
                  <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                    <KebabMenu
                      items={[
                        { label: t("Edit"), icon: Pencil, onClick: () => onEdit(r) },
                        { label: t("Duplicate"), icon: Copy, onClick: () => onDuplicate(r) },
                        { label: t("Delete"), icon: Trash2, danger: true, onClick: () => onDelete(r) },
                      ]}
                    />
                  </td>
                </tr>
              );
            })}
            {items.length === 0 && (
              <tr>
                <td colSpan={columns} className="px-3 py-4 text-center text-slate-600 dark:text-slate-300">
                  {t("No items match.")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {data.count > items.length && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {t("Showing the first {{shown}} of {{total}} items.", { shown: items.length, total: data.count })}
        </p>
      )}
    </div>
  );
}
