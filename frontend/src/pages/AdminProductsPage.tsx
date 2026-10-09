// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { FormSection } from "../components/FormSection";
import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { EyeOff, FileText } from "lucide-react";
import { ApiError, api, mediaUrl } from "../api";
import type { PdfAction } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { usePagedList } from "../usePagedList";
import { ManageTabs } from "../components/ManageTabs";
import { ListToolbar } from "../components/ListToolbar";
import { Pager } from "../components/Pager";
import { AiAssistPanel } from "../components/AiAssistPanel";
import { ProductImagesField } from "../components/ProductImagesField";
import type { GalleryPlan } from "../components/ProductImagesField";
import { OrderedPicker } from "../components/OrderedPicker";
import { MultiSelectList } from "../components/MultiSelectList";
import { categoryTree, pathLabel, toggleSortedId } from "../categories";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { TranslatableField, isEmptyHtml } from "@basicbar/ui";
import { RichTextEditor } from "@basicbar/ui/rich-text-editor";
import { localizedText } from "@basicbar/ui";
import type {
  CategorySuggestion,
  ManageCategory,
  AttributeDef,
  ManageProduct,
  ManageProductInput,
  Paginated,
  ProductImage,
  ProductType,
} from "../types";
import { FormActionBar, sameFormValue } from "../components/FormActionBar";
import { DurationLimitField } from "../components/DurationLimitField";
import { durationCount, limitValue } from "../durations";
import type { PoolDurationLimit } from "../types";

const EMPTY: ManageProductInput = {
  title_de: "",
  title_en: "",
  description_de: "",
  description_en: "",
  short_description_de: "",
  short_description_en: "",
  return_info_de: "",
  return_info_en: "",
  product_type: 0,
  lending_type: "days",
  min_duration: null,
  max_duration: null,
  min_gap: 0,
  missing_notice_lead: 0,
  attributes: {},
  complementary_products: [],
  categories: [],
};

function toInput(p: ManageProduct): ManageProductInput {
  return {
    title_de: p.title_de ?? "",
    title_en: p.title_en ?? "",
    description_de: p.description_de ?? "",
    description_en: p.description_en ?? "",
    short_description_de: p.short_description_de ?? "",
    short_description_en: p.short_description_en ?? "",
    return_info_de: p.return_info_de ?? "",
    return_info_en: p.return_info_en ?? "",
    product_type: p.product_type,
    lending_type: p.lending_type,
    min_duration: p.min_duration,
    max_duration: p.max_duration,
    min_gap: p.min_gap ?? 0,
    missing_notice_lead: p.missing_notice_lead ?? 0,
    attributes: p.attributes,
    complementary_products: p.complementary_products,
    categories: [...(p.categories ?? [])].sort((a, b) => a - b),
  };
}

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
              ? { ...EMPTY }
              : toInput(editing)
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

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

/** Inline marker next to an attribute label: this attribute is not shown to
 *  borrowers in the shop (#54). Sits on the label line so the form grid keeps
 *  its row alignment; visible attributes get no marker (visible is the norm). */
function HiddenInShopBadge() {
  const { t } = useTranslation();
  return (
    <span className="ml-1.5 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-slate-100 px-1.5 align-middle text-[10px] font-medium leading-4 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
      <EyeOff aria-hidden className="h-3 w-3" />
      {t("Not visible in the shop")}
    </span>
  );
}

function AttributeField({
  attr,
  value,
  onChange,
}: {
  attr: AttributeDef;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const hiddenBadge = attr.visible ? undefined : <HiddenInShopBadge />;
  if (attr.type === "short_text" || attr.type === "long_text") {
    // A legacy value may still be a plain string (pre-bilingual data) — treat
    // it as the German value so it keeps displaying.
    const obj =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, string>)
        : { de: value == null ? "" : String(value), en: "" };
    return (
      <TranslatableField
        label={localizedText(attr.label) || attr.key}
        required={attr.required}
        multiline={attr.type === "long_text"}
        values={{ de: obj.de ?? "", en: obj.en ?? "" }}
        onChange={(lang, text) => onChange({ ...obj, [lang]: text })}
        inputClass={inputClass}
        labelAddon={hiddenBadge}
      />
    );
  }
  const str = value == null ? "" : String(value);
  const common = {
    value: str,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange(e.target.value),
    className: `mt-1 ${inputClass}`,
  };
  const typeMap: Record<string, string> = {
    number: "number",
    date: "date",
    time: "time",
    url: "url",
  };

  return (
    <label className="block text-xs text-slate-600 dark:text-slate-300">
      {localizedText(attr.label) || attr.key}
      {attr.required && <span className="text-red-500"> *</span>}
      {hiddenBadge}
      <input type={typeMap[attr.type] ?? "text"} {...common} />
    </label>
  );
}

function PdfAttributeField({
  attr,
  value,
  pending,
  onPick,
  onClearPending,
  onRemove,
}: {
  attr: AttributeDef;
  value: string;
  pending?: PdfAction;
  onPick: (file: File) => void;
  onClearPending: () => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const fileName = value ? decodeURIComponent(value.split("/").pop() ?? "") : "";
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function pickPdf(files?: FileList | null) {
    const file = Array.from(files ?? []).find((f) => f.type === "application/pdf");
    if (file) onPick(file);
  }

  return (
    <div className="col-span-2 text-xs text-slate-600 dark:text-slate-300">
      {localizedText(attr.label) || attr.key}
      {attr.required && <span className="text-red-500"> *</span>}
      {!attr.visible && <HiddenInShopBadge />}
      <div
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          pickPdf(e.dataTransfer.files);
        }}
        className={`mt-1 flex cursor-pointer flex-wrap items-center gap-3 rounded-lg border-2 border-dashed p-3 ${
          dragOver ? "border-slate-900 bg-slate-50 dark:bg-slate-800/50" : "border-slate-300 dark:border-slate-600"
        }`}
      >
        <FileText aria-hidden className="h-5 w-5 shrink-0 text-slate-400" />
        {pending?.kind === "set" ? (
          <span className="text-sm text-slate-700 dark:text-slate-200">
            {pending.file.name}{" "}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClearPending();
              }}
              className="ml-1 text-xs text-slate-500 hover:underline dark:text-slate-300"
            >
              {t("Discard selection")}
            </button>
          </span>
        ) : value ? (
          <span className="text-sm text-slate-700 dark:text-slate-200">
            <a
              href={mediaUrl(value)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-slate-900 underline underline-offset-2 dark:text-slate-100"
            >
              {fileName || t("Open PDF")}
            </a>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              className="ml-3 text-xs text-red-600 hover:underline dark:text-red-400"
            >
              {t("Remove")}
            </button>
          </span>
        ) : (
          <span className="text-sm text-slate-400 dark:text-slate-300">
            {t("Drop a PDF here or click to upload")}
          </span>
        )}
      </div>
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        onChange={(e) => {
          pickPdf(e.target.files);
          e.target.value = "";
        }}
        className="hidden"
      />
    </div>
  );
}

/** Human-readable file size, e.g. "512 KB" or "2.3 MB". */
function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function PdfDropZone({ file, onPick }: { file: File | null; onPick: (f: File) => void }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const take = (files?: FileList | null) => {
    const pdf = Array.from(files ?? []).find((f) => f.type === "application/pdf");
    if (pdf) onPick(pdf);
  };
  return (
    <div
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        take(e.dataTransfer.files);
      }}
      className={`flex cursor-pointer items-center gap-2 rounded-lg border-2 border-dashed p-3 text-sm ${
        dragOver ? "border-slate-900 bg-slate-50 dark:bg-slate-800/50" : "border-slate-300 dark:border-slate-600"
      }`}
    >
      <FileText aria-hidden className="h-5 w-5 shrink-0 text-slate-400" />
      <span className={file ? "text-slate-700 dark:text-slate-200" : "text-slate-400 dark:text-slate-300"}>
        {file ? `${file.name} (${formatFileSize(file.size)})` : t("Drop a PDF here or click to upload")}
      </span>
      <span className="ml-auto shrink-0 text-xs text-slate-400 dark:text-slate-300">{t("Max. 20 MB")}</span>
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        onChange={(e) => {
          take(e.target.files);
          e.target.value = "";
        }}
        className="hidden"
      />
    </div>
  );
}

/** AI category suggestions above the category picker (#98): a button to ask,
 *  then each suggested category with its path and reason (plain text) and an
 *  "Apply" action; "Apply all" adds every one not yet selected. Applying only
 *  ever adds to the selection. */
function CategorySuggestionsPanel({
  suggestions,
  selected,
  busy,
  error,
  canSuggest,
  onSuggest,
  onApply,
  onDismiss,
}: {
  suggestions: CategorySuggestion[] | null;
  selected: number[];
  busy: boolean;
  error: string | null;
  canSuggest: boolean;
  onSuggest: () => void;
  onApply: (ids: number[]) => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
  const chosen = new Set(selected);
  const open = (suggestions ?? []).filter((s) => !chosen.has(s.id));
  return (
    <AiAssistPanel title={t("Suggest categories (AI)")}>
      <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
        {t("Suggests up to 3 existing categories from the title and descriptions. These texts are sent to the configured AI service; nothing is changed until you apply a suggestion.")}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSuggest}
          disabled={busy || !canSuggest}
          className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 hover:bg-brand-500 disabled:opacity-40"
        >
          {busy ? t("Suggesting…") : t("Suggest categories")}
        </button>
        {!canSuggest && !busy && (
          <span className="text-xs text-slate-600 dark:text-slate-300">
            {t("Enter a title or description first.")}
          </span>
        )}
        {error && (
          <span role="alert" className="text-xs text-red-600 dark:text-red-400">
            {error}
          </span>
        )}
      </div>
      {/* Always mounted so screen readers announce content changes. */}
      <div className={suggestions ? "mt-3" : undefined} aria-live="polite" aria-busy={busy}>
        {suggestions && (
          <>
            {suggestions.length === 0 ? (
              <p className="text-xs text-slate-600 dark:text-slate-300">
                {t("No matching categories found.")}
              </p>
            ) : (
              <ul className="space-y-1.5">
                {suggestions.map((s) => {
                  const isChosen = chosen.has(s.id);
                  return (
                    <li
                      key={s.id}
                      className="flex items-start justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{s.path}</p>
                        {s.reason && (
                          <p className="text-xs text-slate-600 dark:text-slate-300">{s.reason}</p>
                        )}
                      </div>
                      {isChosen ? (
                        <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                          {t("Selected")}
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onApply([s.id])}
                          aria-label={t("Apply category {{path}}", { path: s.path })}
                          className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                        >
                          {t("Apply")}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="mt-2 flex items-center gap-3">
              {open.length > 0 && (
                <button
                  type="button"
                  onClick={() => onApply(open.map((s) => s.id))}
                  className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {t("Apply all")}
                </button>
              )}
              <button
                type="button"
                onClick={onDismiss}
                className="text-xs font-medium text-slate-600 underline underline-offset-2 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
              >
                {t("Dismiss suggestions")}
              </button>
            </div>
          </>
        )}
      </div>
    </AiAssistPanel>
  );
}

type ExtractionResult = {
  title: Record<string, string>;
  description: Record<string, string>;
  short_description?: Record<string, string>;
  attributes: Record<string, unknown>;
};

const isEmptyVal = (v: unknown) =>
  v === undefined ||
  v === null ||
  v === "" ||
  (Array.isArray(v) && v.length === 0) ||
  (typeof v === "object" &&
    v !== null &&
    !Array.isArray(v) &&
    Object.values(v as Record<string, unknown>).every((x) => x == null || x === ""));

/** Merge a PDF extraction into the form: only empty fields are filled.
 *  Pure — returns the new form and how many fields were filled. */
function applyExtraction(
  f: ManageProductInput,
  result: ExtractionResult,
): { next: ManageProductInput; count: number } {
  const next = { ...f, attributes: { ...f.attributes } };
  let count = 0;
  const fill = (
    key:
      | "title_de"
      | "title_en"
      | "description_de"
      | "description_en"
      | "short_description_de"
      | "short_description_en",
    val?: string,
  ) => {
    // Product details are rich text: an editor left blank holds e.g. "<p></p>".
    const rich = key.startsWith("description_");
    const empty = rich ? isEmptyHtml(next[key]) : isEmptyVal(next[key]);
    if (empty && val && !(rich && isEmptyHtml(val))) {
      next[key] = val;
      count++;
    }
  };
  fill("title_de", result.title.de);
  fill("title_en", result.title.en);
  fill("description_de", result.description.de);
  fill("description_en", result.description.en);
  fill("short_description_de", result.short_description?.de);
  fill("short_description_en", result.short_description?.en);
  for (const [key, val] of Object.entries(result.attributes)) {
    if (isEmptyVal(next.attributes[key]) && !isEmptyVal(val)) {
      next.attributes[key] = val as never;
      count++;
    }
  }
  return { next, count };
}

function ProductForm({
  initial,
  initialImages,
  productId,
  poolDefaults,
  productTypes,
  onClose,
  onSaved,
}: {
  initial: ManageProductInput;
  initialImages: ProductImage[];
  productId: number | null;
  /** Pool defaults per pool holding a unit, in the saved lending unit (#109). */
  poolDefaults: PoolDurationLimit[];
  productTypes: ProductType[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const allProducts = useFetch<Paginated<ManageProduct>>(
    () => api.listManagedProducts({ pageSize: 2000 }),
    [],
  );
  const categories = useFetch<ManageCategory[]>(() => api.listManagedCategories(), []);
  // Only categories reachable in the shop (not below a trashed one) can be
  // picked; their path ("Kameras › Video") is the label.
  const categoryOptions = useMemo(
    () =>
      categoryTree(categories.data ?? []).ordered.map((c) => ({
        id: c.id,
        label: pathLabel(c),
      })),
    [categories.data],
  );
  const pickableIds = useMemo(() => new Set(categoryOptions.map((o) => o.id)), [categoryOptions]);
  const [form, setForm] = useState<ManageProductInput>(initial);
  const formRef = useRef(form);
  formRef.current = form;
  // Latest gallery plan from ProductImagesField, applied after save.
  const galleryPlan = useRef<GalleryPlan>({ order: [], deletes: [] });
  // Whether the gallery plan differs from the stored images (for the
  // "Unsaved changes" hint).
  const [galleryDirty, setGalleryDirty] = useState(false);
  const onGalleryChange = useCallback(
    (plan: GalleryPlan) => {
      galleryPlan.current = plan;
      setGalleryDirty(
        plan.deletes.length > 0 ||
          plan.order.some((item) => item.file) ||
          plan.order.map((item) => item.existingId).join(",") !==
            initialImages.map((img) => img.id).join(","),
      );
    },
    [initialImages],
  );
  // Pending PDF uploads/removals per `pdf` attribute key, applied after save.
  const [pdfActions, setPdfActions] = useState<Record<string, PdfAction>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // AI feature 2: fill empty fields from an uploaded PDF manual (never
  // persisted on its own — the normal Save still applies afterwards).
  const [aiPdf, setAiPdf] = useState<File | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiFilled, setAiFilled] = useState<number | null>(null);
  // AI category suggestions (#98): up to 3 existing categories from the
  // product's texts; null = none requested yet / dismissed.
  const [catSuggestions, setCatSuggestions] = useState<CategorySuggestion[] | null>(null);
  const [catBusy, setCatBusy] = useState(false);
  const [catError, setCatError] = useState<string | null>(null);
  const [typeQuery, setTypeQuery] = useState("");
  const typeNeedle = typeQuery.trim().toLowerCase();
  const visibleTypes = typeNeedle
    ? productTypes.filter(
        (pt) => pt.id === form.product_type || pt.name.toLowerCase().includes(typeNeedle),
      )
    : productTypes;
  const showTypeSearch = productTypes.length > 10;

  async function runExtract() {
    if (!aiPdf) return;
    setAiBusy(true);
    setAiError(null);
    setAiFilled(null);
    try {
      const { title, description, short_description, attributes } = await api.extractProductFromPdf(
        form.product_type,
        aiPdf,
      );
      // formRef (not the closure's `form`) so edits typed while the request
      // ran are kept.
      const { next, count } = applyExtraction(formRef.current, {
        title,
        description,
        short_description,
        attributes,
      });
      setForm(next);
      setAiFilled(count);
      setAiPdf(null);
      // Follow up once with category suggestions from the filled-in texts.
      void runSuggestCategories(next);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : t("Extraction failed."));
    } finally {
      setAiBusy(false);
    }
  }

  /** The texts the category suggestion is based on (German first). */
  function suggestionInput(f: ManageProductInput) {
    const pick = (de: string | null, en: string | null) => (de || en || "").trim();
    const richPick = (de: string | null, en: string | null) =>
      !isEmptyHtml(de) ? (de ?? "") : !isEmptyHtml(en) ? (en ?? "") : "";
    return {
      title: pick(f.title_de, f.title_en),
      shortDescription: pick(f.short_description_de, f.short_description_en),
      description: richPick(f.description_de, f.description_en),
      productType: f.product_type || null,
    };
  }

  const canSuggestCategories = (() => {
    const input = suggestionInput(form);
    return Boolean(input.title || input.shortDescription || input.description);
  })();

  async function runSuggestCategories(source: ManageProductInput = formRef.current) {
    const input = suggestionInput(source);
    if (!input.title && !input.shortDescription && !input.description) return;
    setCatBusy(true);
    setCatError(null);
    try {
      const { suggestions } = await api.suggestCategories(input);
      setCatSuggestions(suggestions);
    } catch (err) {
      setCatSuggestions(null);
      setCatError(
        err instanceof ApiError && err.status === 503
          ? t("The AI service is not available.")
          : t("AI suggestion failed."),
      );
    } finally {
      setCatBusy(false);
    }
  }

  /** Add suggested categories to the selection (never removes any). */
  function applyCategories(ids: number[]) {
    setForm((f) => {
      let categories = f.categories;
      for (const id of ids) {
        if (pickableIds.has(id) && !categories.includes(id)) {
          categories = toggleSortedId(categories, id);
        }
      }
      return { ...f, categories };
    });
  }

  function set<K extends keyof ManageProductInput>(key: K, value: ManageProductInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // What "inherit from pool" resolves to, per pool holding a unit (#109):
  // "DigiLab: at most 7 days · Videostudio: not limited".
  function poolHint(side: "min" | "max"): string {
    if (poolDefaults.length === 0) return t("Taken from the device's pool.");
    if (form.lending_type !== initial.lending_type) {
      return t("Taken from the device's pool (its default for the new lending type applies after saving).");
    }
    return poolDefaults
      .map((row) => {
        const v = limitValue(row[side]);
        const text = v
          ? t(side === "min" ? "at least {{value}}" : "at most {{value}}", {
              value: durationCount(v, form.lending_type),
            })
          : side === "min"
            ? t("no minimum")
            : t("Not limited");
        return `${row.pool_name}: ${text}`;
      })
      .join(" · ");
  }

  // Ranges that would leave units unbookable (#109): own min above own max,
  // or an own min/max that clashes with a pool's default for the other side.
  const ownMin = limitValue(form.min_duration);
  const ownMax = limitValue(form.max_duration);
  const durationWarnings: string[] = [];
  if (ownMin && ownMax && ownMin > ownMax) {
    durationWarnings.push(t("The minimum duration can't exceed the maximum."));
  } else if (form.lending_type === initial.lending_type) {
    const minClash = ownMin && !ownMax
      ? poolDefaults.filter((row) => {
          const max = limitValue(row.max);
          return max !== null && ownMin > max;
        })
      : [];
    const maxClash = ownMax && !ownMin
      ? poolDefaults.filter((row) => {
          const min = limitValue(row.min);
          return min !== null && ownMax < min;
        })
      : [];
    if (minClash.length) {
      durationWarnings.push(
        t("The minimum is above the default maximum of these pools, so their units can't be booked: {{pools}}", {
          pools: minClash
            .map((row) => `${row.pool_name} (${t("at most {{value}}", { value: durationCount(limitValue(row.max)!, form.lending_type) })})`)
            .join(", "),
        }),
      );
    }
    if (maxClash.length) {
      durationWarnings.push(
        t("The maximum is below the default minimum of these pools, so their units can't be booked: {{pools}}", {
          pools: maxClash
            .map((row) => `${row.pool_name} (${t("at least {{value}}", { value: durationCount(limitValue(row.min)!, form.lending_type) })})`)
            .join(", "),
        }),
      );
    }
  }
  // Changing the lending type re-reads the numbers in the other unit.
  const unitChangedWithOwnValues =
    form.lending_type !== initial.lending_type && (ownMin !== null || ownMax !== null);

  const schema =
    productTypes.find((t) => t.id === form.product_type)?.attribute_schema ?? [];

  // Attribute values already set that the selected type's schema doesn't define
  // — switching type keeps them in the form (so switching back restores them),
  // but they are dropped on save. Surface them as a warning (the change is
  // still allowed).
  const schemaKeys = new Set(schema.map((a) => a.key));
  const lostAttributeKeys = Object.entries(form.attributes)
    .filter(([key, value]) => {
      if (schemaKeys.has(key)) return false;
      return !(value === undefined || value === null || value === "" ||
        (Array.isArray(value) && value.length === 0));
    })
    .map(([key]) => key);

  function setAttr(key: string, value: unknown) {
    setForm((f) => ({ ...f, attributes: { ...f.attributes, [key]: value } }));
  }

  function sameComplements(a: number[], b: number[]) {
    return a.length === b.length && a.every((id, i) => id === b[i]);
  }

  function toggleCategory(id: number) {
    setForm((f) => ({ ...f, categories: toggleSortedId(f.categories, id) }));
  }

  const dirty =
    !sameFormValue(form, initial) ||
    Object.keys(pdfActions).length > 0 ||
    galleryDirty;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.product_type) {
      setError(t("Please choose a product type."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let saved: ManageProduct;
      // Only pickable categories are offered and sent; the backend keeps a
      // product's links to trashed categories by itself. On edit they are
      // sent only when changed here (ids are kept sorted).
      const chosenCategories = form.categories.filter((id) => pickableIds.has(id));
      if (productId === null) {
        saved = await api.createProduct({ ...form, categories: chosenCategories });
      } else {
        // M3: if complements weren't touched in this session, don't send them
        // — another lender may have linked/unlinked one meanwhile, and
        // re-sending our (possibly stale) snapshot would silently undo that.
        const { complementary_products, categories, ...rest } = form;
        const payload: Partial<ManageProductInput> = { ...rest };
        if (!sameComplements(complementary_products, initial.complementary_products)) {
          payload.complementary_products = complementary_products;
        }
        if (!sameComplements(categories, initial.categories)) payload.categories = chosenCategories;
        saved = await api.updateProduct(productId, payload);
      }
      // Apply the gallery plan: delete removed, upload new (in order), reorder.
      const plan = galleryPlan.current;
      for (const id of plan.deletes) await api.deleteProductImage(saved.id, id);
      const finalIds: number[] = [];
      for (const item of plan.order) {
        if (item.file) {
          const created = await api.uploadProductImage(saved.id, item.file);
          finalIds.push(created.id);
        } else if (item.existingId) {
          finalIds.push(item.existingId);
        }
      }
      if (finalIds.length > 1) await api.reorderProductImages(saved.id, finalIds);
      for (const [key, action] of Object.entries(pdfActions)) {
        await api.applyProductPdf(saved.id, key, action);
      }
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
        {productId === null ? t("New product") : t("Edit {{title}}", { title: initial.title_de })}
      </h3>

      <FormSection id="product-general-heading" title={t("General")}>
        {/* Product type is chosen first — it drives the AI extraction below. */}
        <div className="text-xs text-slate-600 dark:text-slate-300">
          <label htmlFor="product-type-select" className="block">{t("Product type")}</label>
          {showTypeSearch && (
            <input
              type="search"
              value={typeQuery}
              onChange={(e) => setTypeQuery(e.target.value)}
              placeholder={t("Search product types…")}
              aria-label={t("Search product types…")}
              className={`mt-1 ${inputClass}`}
            />
          )}
          <select
            id="product-type-select"
            value={form.product_type || ""}
            onChange={(e) => set("product_type", Number(e.target.value))}
            required
            className={`mt-1 ${inputClass}`}
          >
            <option value="" disabled>
              {t("— Choose a product type —")}
            </option>
            {visibleTypes.map((pt) => (
              <option key={pt.id} value={pt.id}>
                {pt.name}
              </option>
            ))}
          </select>
          {showTypeSearch && typeNeedle && visibleTypes.every((pt) => pt.id === form.product_type) && (
            <span role="status" className="mt-1 block text-xs text-slate-600 dark:text-slate-300">
              {t("No product type found.")}
            </span>
          )}
        </div>

        {user?.ai_enabled && form.product_type ? (
          <AiAssistPanel title={t("Fill from PDF (AI)")}>
            <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">
              {t("Reads a PDF (e.g. a manual or data sheet) and fills in the title, descriptions and properties — only empty fields; existing entries are kept. The text of the PDF is sent to the configured AI service for this; the PDF is not stored. Max. 20 MB.")}
            </p>
            <PdfDropZone file={aiPdf} onPick={setAiPdf} />
            <div className="mt-2 flex items-center gap-3">
              <button
                type="button"
                onClick={runExtract}
                disabled={!aiPdf || aiBusy}
                className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 hover:bg-brand-500 disabled:opacity-40"
              >
                {aiBusy ? t("Filling…") : t("Fill in")}
              </button>
              {aiFilled !== null && (
                <span className="text-xs text-slate-600 dark:text-slate-300">
                  {t("{{count}} field filled", { count: aiFilled })}
                </span>
              )}
              {aiError && <span className="text-xs text-red-600 dark:text-red-400">{aiError}</span>}
            </div>
          </AiAssistPanel>
        ) : null}

        <TranslatableField
          label={t("Title")}
          required
          values={{ de: form.title_de, en: form.title_en }}
          onChange={(lang, v) => setForm((f) => ({ ...f, [`title_${lang}`]: v }))}
          inputClass={inputClass}
        />

        <TranslatableField
          label={t("Short description")}
          values={{ de: form.short_description_de, en: form.short_description_en }}
          onChange={(lang, v) =>
            setForm((f) => ({ ...f, [`short_description_${lang}`]: v }))
          }
          inputClass={inputClass}
        />

        <TranslatableField
          label={t("Product details")}
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

        <div className="block text-xs text-slate-600 dark:text-slate-300">
          {t("Images")}
          <div className="mt-1">
            <ProductImagesField
              initialImages={initialImages}
              onChange={onGalleryChange}
            />
          </div>
        </div>
      </FormSection>

      <FormSection id="product-lending-heading" title={t("Lending terms")}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block text-xs text-slate-600 dark:text-slate-300">
            {t("Lending type")}
            <select
              value={form.lending_type}
              onChange={(e) =>
                set("lending_type", e.target.value as ManageProductInput["lending_type"])
              }
              className={`mt-1 ${inputClass}`}
            >
              <option value="days">{t("Days")}</option>
              <option value="hours">{t("Hours")}</option>
            </select>
          </label>
          {/* Keeps min and max duration side by side in the next row. */}
          <div className="hidden sm:block" aria-hidden="true" />
          <DurationLimitField
            label={t("Min duration")}
            value={form.min_duration}
            onChange={(v) => set("min_duration", v)}
            unit={form.lending_type}
            inheritLabel={t("Inherit from pool")}
            inheritedHint={poolHint("min")}
          />
          <DurationLimitField
            label={t("Max duration")}
            value={form.max_duration}
            onChange={(v) => set("max_duration", v)}
            unit={form.lending_type}
            inheritLabel={t("Inherit from pool")}
            inheritedHint={poolHint("max")}
          />
          {(unitChangedWithOwnValues || durationWarnings.length > 0) && (
            <div className="space-y-1 sm:col-span-2" role="status">
              {unitChangedWithOwnValues && (
                <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                  {form.lending_type === "hours"
                    ? t("The lending type changed: the min/max values above now count hours instead of days.")
                    : t("The lending type changed: the min/max values above now count days instead of hours.")}
                </p>
              )}
              {durationWarnings.map((text) => (
                <p
                  key={text}
                  className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                >
                  {text}
                </p>
              ))}
            </div>
          )}
          <label className="block text-xs text-slate-600 dark:text-slate-300">
            {form.lending_type === "hours"
              ? t("Min gap between bookings (hours)")
              : t("Min gap between bookings (days)")}
            <input
              type="number"
              min={0}
              value={form.min_gap}
              onChange={(e) => set("min_gap", Number(e.target.value) || 0)}
              className={`mt-1 ${inputClass}`}
            />
          </label>
          <label className="block text-xs text-slate-600 dark:text-slate-300">
            {form.lending_type === "hours"
              ? t("Notify borrower if missing — lead (hours)")
              : t("Notify borrower if missing — lead (days)")}
            <input
              type="number"
              min={0}
              value={form.missing_notice_lead}
              onChange={(e) => set("missing_notice_lead", Number(e.target.value) || 0)}
              className={`mt-1 ${inputClass}`}
            />
          </label>
        </div>
      </FormSection>

      <FormSection id="product-placement-heading" title={t("Placement in the shop")}>
        <div>
          <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">
            {t("Categories — where the product appears in the shop navigation.")}
          </p>
          {user?.ai_enabled && (
            <div className="mb-2">
              <CategorySuggestionsPanel
                suggestions={
                  // Only pickable categories can be applied (once the tree is loaded).
                  categories.data
                    ? (catSuggestions?.filter((s) => pickableIds.has(s.id)) ?? null)
                    : catSuggestions
                }
                selected={form.categories}
                busy={catBusy}
                error={catError}
                canSuggest={canSuggestCategories}
                onSuggest={() => runSuggestCategories()}
                onApply={applyCategories}
                onDismiss={() => {
                  setCatSuggestions(null);
                  setCatError(null);
                }}
              />
            </div>
          )}
          <MultiSelectList
            options={categoryOptions}
            selected={form.categories.filter((id) => pickableIds.has(id))}
            onToggle={toggleCategory}
            placeholder={t("Search categories…")}
            emptyText={t("No categories available.")}
          />
        </div>

        <div>
          <OrderedPicker
            label={t("Complementary devices")}
            options={(allProducts.data?.results ?? []).map((p) => ({ id: p.id, label: p.title }))}
            value={form.complementary_products}
            onChange={(ids) => set("complementary_products", ids)}
            excludeIds={productId != null ? [productId] : []}
            placeholder={t("Add a device…")}
            emptyText={t("No complementary devices yet.")}
          />
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {t("Linked both ways — the other device lists this one too.")}
          </p>
        </div>
      </FormSection>

      {(lostAttributeKeys.length > 0 || (form.product_type > 0 && schema.length > 0)) && (
        <FormSection id="product-properties-heading" title={t("Properties")}>
          {lostAttributeKeys.length > 0 && (
            <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300">
              {t(
                "These set values are not part of the chosen type and will be removed on save: {{keys}}",
                { keys: lostAttributeKeys.join(", ") },
              )}
            </p>
          )}
          {form.product_type > 0 && schema.length > 0 && (
            <div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {schema.map((attr) =>
                attr.type === "pdf" ? (
                  <PdfAttributeField
                    key={attr.key}
                    attr={attr}
                    value={
                      typeof form.attributes[attr.key] === "string"
                        ? (form.attributes[attr.key] as string)
                        : ""
                    }
                    pending={pdfActions[attr.key]}
                    onPick={(file) =>
                      setPdfActions((p) => ({ ...p, [attr.key]: { kind: "set", file } }))
                    }
                    onClearPending={() =>
                      setPdfActions((p) => {
                        const next = { ...p };
                        delete next[attr.key];
                        return next;
                      })
                    }
                    onRemove={() => {
                      setPdfActions((p) => ({ ...p, [attr.key]: { kind: "clear" } }));
                      setAttr(attr.key, "");
                    }}
                  />
                ) : (
                  <AttributeField
                    key={attr.key}
                    attr={attr}
                    value={form.attributes[attr.key] ?? attr.default}
                    onChange={(v) => setAttr(attr.key, v)}
                  />
                ),
              )}
            </div>
            {schema.some((a) => !a.visible) && (
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
                {user?.is_staff ? (
                  <a
                    href={`/admin/product-types?edit=${form.product_type}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-700 underline underline-offset-2 dark:text-brand-300"
                  >
                    {t("Change shop visibility in the product type →")}
                    <span className="sr-only"> {t("(opens in a new tab)")}</span>
                  </a>
                ) : (
                  t("Shop visibility is set by an administrator in the product type.")
                )}
              </p>
            )}
            </div>
          )}
        </FormSection>
      )}

      <FormSection id="product-lenders-heading" title={t("For lenders")}>
        <TranslatableField
          label={t("Return information")}
          hint={t("Shown to lenders at return (e.g. what to check). Not visible to borrowers.")}
          values={{ de: form.return_info_de, en: form.return_info_en }}
          onChange={(lang, v) =>
            setForm((f) => ({ ...f, [`return_info_${lang}`]: v }))
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
      </FormSection>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <FormActionBar saving={busy} onCancel={onClose} dirty={dirty} surface="card" />
    </form>
  );
}
