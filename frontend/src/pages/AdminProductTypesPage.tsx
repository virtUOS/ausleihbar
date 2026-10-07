// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ListToolbar } from "../components/ListToolbar";
import { AttributeSchemaEditor } from "../components/AttributeSchemaEditor";
import { AiAssistPanel } from "../components/AiAssistPanel";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DuplicateButton, DeleteButton } from "../components/RowActions";
import { TranslatableField } from "@basicbar/ui";
import type { Paginated, ProductType, ProductTypeInput } from "../types";
import { FormActionBar, sameFormValue } from "../components/FormActionBar";

const EMPTY: ProductTypeInput = {
  name_de: "",
  name_en: "",
  description_de: "",
  description_en: "",
  attribute_schema: [],
};

function toInput(pt: ProductType): ProductTypeInput {
  return {
    name_de: pt.name_de ?? "",
    name_en: pt.name_en ?? "",
    description_de: pt.description_de ?? "",
    description_en: pt.description_en ?? "",
    attribute_schema: pt.attribute_schema,
  };
}

/** Pre-fill a *new* type from an existing one, keeping its attribute schema
 *  and suffixing the name per language so it doesn't collide with the
 *  original. (Products stay with the original.) */
function cloneInput(pt: ProductType): ProductTypeInput {
  return {
    name_de: pt.name_de ? `${pt.name_de} (Kopie)` : "",
    name_en: pt.name_en ? `${pt.name_en} (copy)` : "",
    description_de: pt.description_de ?? "",
    description_en: pt.description_en ?? "",
    attribute_schema: pt.attribute_schema,
  };
}

/** Editor target: a new type, an existing one to edit, or a clone source. */
type Editing = ProductType | "new" | { clone: ProductType } | null;

export function AdminProductTypesPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<Editing>(null);
  const [query, setQuery] = useState("");
  // Load the full list (sorted by name); filter/search client-side.
  const types = useFetch<Paginated<ProductType>>(
    () => api.listProductTypes({ pageSize: 2000 }),
    [version],
  );
  const rows = types.data?.results ?? [];

  const [searchParams, setSearchParams] = useSearchParams();
  // Deep link from the product form (#54): /admin/product-types?edit=<id>.
  useEffect(() => {
    const id = Number(searchParams.get("edit"));
    if (!id) return;
    let cancelled = false;
    api
      .getProductType(id)
      .then((pt) => {
        if (!cancelled) setEditing(pt);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setSearchParams({}, { replace: true });
      });
    return () => {
      cancelled = true;
    };
  }, [searchParams, setSearchParams]);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? rows.filter((pt) => pt.name.toLowerCase().includes(needle))
    : rows;

  async function remove(pt: ProductType) {
    if (
      !(await confirm({
        message: t("Move product type “{{name}}” to the trash?", { name: pt.name }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deleteProductType(pt.id);
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
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Product types")}</h2>
        {editing === null && (
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
          >
            {t("+ New type")}
          </button>
        )}
      </div>

      {editing !== null && (
        <TypeForm
          initial={
            editing === "new"
              ? EMPTY
              : "clone" in editing
                ? cloneInput(editing.clone)
                : toInput(editing)
          }
          typeId={editing === "new" || "clone" in editing ? null : editing.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {editing === null && rows.length > 0 && (
        <ListToolbar
          search={query}
          onSearch={setQuery}
          count={filtered.length}
          hidePager
          placeholder={t("Search product types…")}
        />
      )}

      {types.loading && <Loading />}
      {types.error && <ErrorBox message={types.error} />}

      {types.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Attributes")}</th>
                <th className="px-3 py-2">{t("Products")}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((pt) => (
                <tr
                  key={pt.id}
                  onClick={() => setEditing(pt)}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{pt.name}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                    {pt.attribute_schema.length}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{pt.product_count}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
                      <EditButton onClick={() => setEditing(pt)} />
                      <DuplicateButton
                        label={t("Clone type")}
                        onClick={() => setEditing({ clone: pt })}
                      />
                      {/* A type still used by products can't be deleted (the
                          API refuses); say so up front instead of failing. */}
                      <DeleteButton
                        onClick={() => remove(pt)}
                        disabled={pt.product_count > 0}
                        label={
                          pt.product_count > 0
                            ? `${t("Delete")}: ${t("Still used by products")}`
                            : undefined
                        }
                        className="disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-slate-400"
                      />
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t("No product types yet.")}
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

function TypeForm({
  initial,
  typeId,
  onClose,
  onSaved,
}: {
  initial: ProductTypeInput;
  typeId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [form, setForm] = useState<ProductTypeInput>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Per-attribute count of products with a filled, non-default value (§5.2):
  // the editor warns when removing one of these.
  const [usage, setUsage] = useState<Record<string, number>>({});
  // AI attribute-suggestion block: optional extra hints (transient, not saved).
  const [aiHints, setAiHints] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  useEffect(() => {
    if (typeId !== null) api.getAttributeUsage(typeId).then(setUsage).catch(() => {});
  }, [typeId]);

  async function runSuggest() {
    setAiBusy(true);
    setAiError(null);
    try {
      const existing = form.attribute_schema.map((a) => a.key);
      const { attributes } = await api.suggestAttributes({
        name: (form.name_de || form.name_en || "").trim(),
        description: (form.description_de || form.description_en || "").trim(),
        hints: aiHints.trim(),
        existingKeys: existing,
      });
      const have = new Set(existing);
      const merged = [...form.attribute_schema];
      for (const a of attributes) {
        if (!have.has(a.key)) {
          merged.push(a);
          have.add(a.key);
        }
      }
      setForm((f) => ({ ...f, attribute_schema: merged }));
      setAiHints("");
    } catch {
      setAiError(t("AI suggestion failed."));
    } finally {
      setAiBusy(false);
    }
  }

  const dirty = !sameFormValue(form, initial);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (typeId === null) await api.createProductType(form);
      else await api.updateProductType(typeId, form);
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
        {typeId === null ? t("New product type") : t("Edit {{name}}", { name: initial.name_de })}
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
      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Attributes")}</p>
        {user?.ai_enabled && (
          <div className="mb-3">
            <AiAssistPanel title={t("Suggest attributes with AI")}>
              <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">
                {t("Uses the type's name and description above. Add optional hints:")}
              </p>
              <textarea
                value={aiHints}
                onChange={(e) => setAiHints(e.target.value)}
                rows={2}
                maxLength={2000}
                placeholder={t("Additional hints for the AI (optional)")}
                className="w-full rounded-md border border-slate-200 p-2 text-sm dark:border-slate-700 dark:bg-slate-800"
              />
              <div className="mt-2 flex items-center gap-3">
                <button
                  type="button"
                  onClick={runSuggest}
                  disabled={
                    aiBusy ||
                    !(form.name_de || form.name_en || form.description_de || form.description_en || aiHints.trim())
                  }
                  className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 hover:bg-brand-500 disabled:opacity-40"
                >
                  {aiBusy ? t("Generating…") : t("Generate suggestions")}
                </button>
                {aiError && (
                  <span className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400">
                    {aiError}
                    <button
                      type="button"
                      onClick={() => setAiError(null)}
                      aria-label={t("Dismiss")}
                      className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-200"
                    >
                      ×
                    </button>
                  </span>
                )}
              </div>
            </AiAssistPanel>
          </div>
        )}
        <AttributeSchemaEditor
          value={form.attribute_schema}
          onChange={(v) => setForm((f) => ({ ...f, attribute_schema: v }))}
          removeWarnings={usage}
        />
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

      <FormActionBar saving={busy} onCancel={onClose} dirty={dirty} />
    </form>
  );
}
