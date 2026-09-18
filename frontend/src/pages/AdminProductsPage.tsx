// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { FileText } from "lucide-react";
import { api, mediaUrl } from "../api";
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
import { MultiSelectList } from "../components/MultiSelectList";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { TranslatableField } from "@basicbar/ui";
import { localizedText } from "@basicbar/ui";
import type {
  AttributeDef,
  ManageCategory,
  ManageProduct,
  ManageProductInput,
  Paginated,
  ProductImage,
  ProductType,
} from "../types";

const EMPTY: ManageProductInput = {
  title_de: "",
  title_en: "",
  description_de: "",
  description_en: "",
  return_info_de: "",
  return_info_en: "",
  product_type: 0,
  lending_type: "days",
  min_duration: null,
  max_duration: null,
  min_gap: 0,
  missing_notice_lead: 0,
  attributes: {},
  categories: [],
};

function toInput(p: ManageProduct): ManageProductInput {
  return {
    title_de: p.title_de ?? "",
    title_en: p.title_en ?? "",
    description_de: p.description_de ?? "",
    description_en: p.description_en ?? "",
    return_info_de: p.return_info_de ?? "",
    return_info_en: p.return_info_en ?? "",
    product_type: p.product_type,
    lending_type: p.lending_type,
    min_duration: p.min_duration,
    max_duration: p.max_duration,
    min_gap: p.min_gap ?? 0,
    missing_notice_lead: p.missing_notice_lead ?? 0,
    attributes: p.attributes,
    categories: p.categories,
  };
}

export function AdminProductsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const { user } = useAuth();
  const [editing, setEditing] = useState<ManageProduct | "new" | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("");
  const products = usePagedList<ManageProduct>(
    ({ page, search }) =>
      api.listManagedProducts({ page, search, category: categoryFilter || undefined }),
    categoryFilter,
  );
  const types = useFetch<Paginated<ProductType>>(() => api.listProductTypes(), []);
  const categories = useFetch<Paginated<ManageCategory>>(
    () => api.listManagedCategories({ pageSize: 2000 }),
    [],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = products.reload;

  async function remove(product: ManageProduct) {
    if (
      !(await confirm({
        message: t("Delete product “{{title}}”?", { title: product.title }),
        confirmLabel: t("Delete"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteProduct(product.id);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Delete failed."));
    }
  }

  const productTypes = types.data?.results ?? [];
  const allCategories = categories.data?.results ?? [];
  const categoryName = new Map(allCategories.map((c) => [c.id, c.title]));

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
        <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
          {t("Create a product type first — products are based on one.")}
        </p>
      )}

      {editing !== null && (
        <ProductForm
          initial={
            editing === "new"
              ? { ...EMPTY, product_type: productTypes[0]?.id ?? 0 }
              : toInput(editing)
          }
          initialImages={editing === "new" ? [] : editing.images}
          productId={editing === "new" ? null : editing.id}
          productTypes={productTypes}
          allCategories={allCategories}
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
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">{t("All categories")}</option>
            <option value="none">{t("No category")}</option>
            {allCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
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
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2">{t("Title")}</th>
                <th className="px-3 py-2">{t("Type")}</th>
                <th className="px-3 py-2">{t("Categories")}</th>
                <th className="px-3 py-2">{t("Lending")}</th>
                <th className="px-3 py-2">{t("Resources")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {products.items.map((p) => (
                <tr key={p.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{p.title}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.product_type_name}</td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                    {p.categories.length
                      ? p.categories
                          .map((id) => categoryName.get(id))
                          .filter(Boolean)
                          .join(", ")
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.lending_type}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.resource_count}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5">
                      <EditButton onClick={() => setEditing(p)} />
                      <DeleteButton onClick={() => remove(p)} />
                    </div>
                  </td>
                </tr>
              ))}
              {products.items.length === 0 && !products.loading && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
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

function AttributeField({
  attr,
  value,
  onChange,
}: {
  attr: AttributeDef;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
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
    <label className="block text-xs text-slate-500 dark:text-slate-400">
      {localizedText(attr.label) || attr.key}
      {attr.required && <span className="text-red-500"> *</span>}
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
    <div className="col-span-2 text-xs text-slate-500 dark:text-slate-400">
      {localizedText(attr.label) || attr.key}
      {attr.required && <span className="text-red-500"> *</span>}
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
              className="ml-1 text-xs text-slate-500 hover:underline dark:text-slate-400"
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
          <span className="text-sm text-slate-400 dark:text-slate-500">
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
      <span className={file ? "text-slate-700 dark:text-slate-200" : "text-slate-400 dark:text-slate-500"}>
        {file ? `${file.name} (${formatFileSize(file.size)})` : t("Drop a PDF here or click to upload")}
      </span>
      <span className="ml-auto shrink-0 text-xs text-slate-400 dark:text-slate-500">{t("Max. 20 MB")}</span>
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

function ProductForm({
  initial,
  initialImages,
  productId,
  productTypes,
  allCategories,
  onClose,
  onSaved,
}: {
  initial: ManageProductInput;
  initialImages: ProductImage[];
  productId: number | null;
  productTypes: ProductType[];
  allCategories: ManageCategory[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [form, setForm] = useState<ManageProductInput>(initial);
  // Latest gallery plan from ProductImagesField, applied after save.
  const galleryPlan = useRef<GalleryPlan>({ order: [], deletes: [] });
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

  const isEmptyVal = (v: unknown) =>
    v === undefined ||
    v === null ||
    v === "" ||
    (Array.isArray(v) && v.length === 0) ||
    (typeof v === "object" &&
      v !== null &&
      !Array.isArray(v) &&
      Object.values(v as Record<string, unknown>).every((x) => x == null || x === ""));

  async function runExtract() {
    if (!aiPdf) return;
    setAiBusy(true);
    setAiError(null);
    setAiFilled(null);
    try {
      const { title, description, attributes } = await api.extractProductFromPdf(
        form.product_type,
        aiPdf,
      );
      let count = 0;
      setForm((f) => {
        const next = { ...f, attributes: { ...f.attributes } };
        const fill = (
          key: "title_de" | "title_en" | "description_de" | "description_en",
          val?: string,
        ) => {
          if (isEmptyVal(next[key]) && val) {
            next[key] = val;
            count++;
          }
        };
        fill("title_de", title.de);
        fill("title_en", title.en);
        fill("description_de", description.de);
        fill("description_en", description.en);
        for (const [key, val] of Object.entries(attributes)) {
          if (isEmptyVal(next.attributes[key]) && !isEmptyVal(val)) {
            next.attributes[key] = val as never;
            count++;
          }
        }
        return next;
      });
      setAiFilled(count);
      setAiPdf(null);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : t("Extraction failed."));
    } finally {
      setAiBusy(false);
    }
  }

  function set<K extends keyof ManageProductInput>(key: K, value: ManageProductInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function toggleCategory(id: number) {
    setForm((f) => ({
      ...f,
      categories: f.categories.includes(id)
        ? f.categories.filter((c) => c !== id)
        : [...f.categories, id],
    }));
  }

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

  function numberOrNull(v: string): number | null {
    return v === "" ? null : Number(v);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved =
        productId === null
          ? await api.createProduct(form)
          : await api.updateProduct(productId, form);
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

      {/* Product type is chosen first — it drives the AI extraction below. */}
      <label className="block text-xs text-slate-500 dark:text-slate-400">
        {t("Product type")}
        <select
          value={form.product_type}
          onChange={(e) => set("product_type", Number(e.target.value))}
          className={`mt-1 ${inputClass}`}
        >
          {productTypes.map((pt) => (
            <option key={pt.id} value={pt.id}>
              {pt.name}
            </option>
          ))}
        </select>
      </label>

      {user?.ai_enabled && form.product_type ? (
        <AiAssistPanel title={t("Fill from PDF (AI)")}>
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
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {t("{{count}} field filled", { count: aiFilled })}
              </span>
            )}
            {aiError && <span className="text-xs text-red-600 dark:text-red-400">{aiError}</span>}
          </div>
        </AiAssistPanel>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <TranslatableField
          label={t("Title")}
          required
          values={{ de: form.title_de, en: form.title_en }}
          onChange={(lang, v) => setForm((f) => ({ ...f, [`title_${lang}`]: v }))}
          inputClass={inputClass}
        />
        <label className="block text-xs text-slate-500 dark:text-slate-400">
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
        <div className="block text-xs text-slate-500 dark:text-slate-400">
          {t("Images")}
          <div className="mt-1">
            <ProductImagesField
              initialImages={initialImages}
              onChange={(plan) => {
                galleryPlan.current = plan;
              }}
            />
          </div>
        </div>
        <label className="block text-xs text-slate-500 dark:text-slate-400">
          {t("Min duration")}
          <input
            type="number"
            min={0}
            value={form.min_duration ?? ""}
            onChange={(e) => set("min_duration", numberOrNull(e.target.value))}
            className={`mt-1 ${inputClass}`}
          />
        </label>
        <label className="block text-xs text-slate-500 dark:text-slate-400">
          {t("Max duration")}
          <input
            type="number"
            min={0}
            value={form.max_duration ?? ""}
            onChange={(e) => set("max_duration", numberOrNull(e.target.value))}
            className={`mt-1 ${inputClass}`}
          />
        </label>
        <label className="block text-xs text-slate-500 dark:text-slate-400">
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
        <label className="block text-xs text-slate-500 dark:text-slate-400">
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

      <TranslatableField
        label={t("Description")}
        multiline
        values={{ de: form.description_de, en: form.description_en }}
        onChange={(lang, v) =>
          setForm((f) => ({ ...f, [`description_${lang}`]: v }))
        }
        inputClass={inputClass}
      />

      <TranslatableField
        label={t("Return information")}
        multiline
        hint={t("Shown to lenders at return (e.g. what to check). Not visible to borrowers.")}
        values={{ de: form.return_info_de, en: form.return_info_en }}
        onChange={(lang, v) =>
          setForm((f) => ({ ...f, [`return_info_${lang}`]: v }))
        }
        inputClass={inputClass}
      />

      <div>
        <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">{t("Categories")}</p>
        <MultiSelectList
          options={allCategories.map((c) => ({ id: c.id, label: c.title }))}
          selected={form.categories}
          onToggle={toggleCategory}
          placeholder={t("Search categories…")}
          emptyText={t("No categories available.")}
        />
      </div>

      {lostAttributeKeys.length > 0 && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300">
          {t(
            "These set values are not part of the chosen type and will be removed on save: {{keys}}",
            { keys: lostAttributeKeys.join(", ") },
          )}
        </p>
      )}

      {schema.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-slate-600 dark:text-slate-300">{t("Attributes")}</p>
          <div className="grid grid-cols-2 gap-3">
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
