// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { localizedText } from "@basicbar/ui";
import { api, ApiError } from "../api";
import i18n from "../i18n";
import { DateField } from "./DateField";
import { AttributeField } from "./AttributeField";
import { RESOURCE_STATUSES } from "../types";
import type {
  ManageProduct,
  ManageResource,
  ManageResourceInput,
  ProductType,
  ResourcePool,
} from "../types";
import { FormActionBar, sameFormValue } from "./FormActionBar";
import { DurationLimitField } from "./DurationLimitField";
import { durationCount, limitValue } from "../durations";

export const EMPTY_RESOURCE: ManageResourceInput = {
  product: 0,
  resource_pool: 0,
  inventory_number: "",
  serial_number: "",
  attributes: {},
  qr_code_id: "",
  status: "available",
  defect_note: "",
  storage_location: "",
  procurement_date: null,
  warranty_end: null,
  value: null,
  procuring_institution: "",
  owning_institution: "",
  condition_rating: 5,
  condition_note: "",
  min_duration: null,
  max_duration: null,
};

export function resourceToInput(r: ManageResource): ManageResourceInput {
  return {
    product: r.product,
    resource_pool: r.resource_pool,
    inventory_number: r.inventory_number,
    serial_number: r.serial_number ?? "",
    attributes: r.attributes ?? {},
    qr_code_id: r.qr_code_id,
    status: r.status,
    defect_note: r.defect_note,
    storage_location: r.storage_location,
    procurement_date: r.procurement_date,
    warranty_end: r.warranty_end,
    value: r.value,
    procuring_institution: r.procuring_institution,
    owning_institution: r.owning_institution,
    condition_rating: r.condition_rating,
    condition_note: r.condition_note,
    min_duration: r.min_duration ?? null,
    max_duration: r.max_duration ?? null,
  };
}

export function statusLabel(status: string): string {
  switch (status) {
    case "available":
      return i18n.t("Available");
    case "blocked":
      return i18n.t("Blocked");
    case "defective":
      return i18n.t("Defective");
    case "retired":
      return i18n.t("Retired");
    default:
      return status;
  }
}

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs text-slate-600 dark:text-slate-300">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}

export function ResourceForm({
  initial,
  resourceId,
  autoSuggest,
  allProducts,
  productTypes,
  allPools,
  onClose,
  onSaved,
}: {
  initial: ManageResourceInput;
  resourceId: number | null;
  autoSuggest: boolean;
  allProducts: ManageProduct[];
  productTypes: ProductType[];
  allPools: ResourcePool[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ManageResourceInput>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Once the user edits the inventory number, stop auto-suggesting.
  const [numberLocked, setNumberLocked] = useState(false);

  // When creating or duplicating, propose a free inventory number for the
  // selected pool (unless the user has taken over that field). The QR code ID
  // is assigned by the server when left empty (#50).
  useEffect(() => {
    if (!autoSuggest || numberLocked || !form.resource_pool) return;
    let cancelled = false;
    api
      .suggestInventoryNumber(form.resource_pool)
      .then((s) => {
        if (!cancelled)
          setForm((f) => ({
            ...f,
            inventory_number: s.inventory_number,
          }));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [form.resource_pool, autoSuggest, numberLocked]);

  function set<K extends keyof ManageResourceInput>(
    key: K,
    value: ManageResourceInput[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // What "inherit from product" resolves to (#109): the product's own value,
  // else the pool's default in the product's unit, else no limit. Computed
  // here so it follows product/pool changes in the form before saving.
  const product = allProducts.find((p) => p.id === form.product) ?? null;
  const pool = allPools.find((p) => p.id === form.resource_pool) ?? null;
  const unit = product?.lending_type ?? "days";
  // Properties the product type scopes to the individual device (#106).
  const deviceSchema =
    productTypes
      .find((pt) => pt.id === product?.product_type)
      ?.attribute_schema.filter((a) => a.scope === "device") ?? [];
  function inherited(side: "min" | "max"): { value: number | null; hint: string } {
    if (!product) return { value: null, hint: t("Choose a product to see the inherited value.") };
    const own = limitValue(side === "min" ? product.min_duration : product.max_duration);
    if (own) {
      return {
        value: own,
        hint: t("{{value}} – from the product", { value: durationCount(own, unit) }),
      };
    }
    const fromPool = pool ? limitValue(pool[`default_${side}_${unit}`]) : null;
    if (fromPool && pool) {
      return {
        value: fromPool,
        hint: t("{{value}} – from pool {{pool}}", {
          value: durationCount(fromPool, unit),
          pool: pool.name,
        }),
      };
    }
    return { value: null, hint: side === "min" ? t("no minimum") : t("Not limited") };
  }
  const inheritedMin = inherited("min");
  const inheritedMax = inherited("max");

  // An auto-suggested inventory number is not a user change.
  const dirty = !sameFormValue(
    numberLocked ? form : { ...form, inventory_number: initial.inventory_number },
    initial,
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.product || !form.resource_pool) {
      setError(t("Please choose a product and a resource pool."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (resourceId === null) await api.createResource(form);
      else await api.updateResource(resourceId, form);
      onSaved();
    } catch (err) {
      const nested =
        err instanceof ApiError
          ? (err.data as { attributes?: unknown } | undefined)?.attributes
          : undefined;
      if (nested && typeof nested === "object" && !Array.isArray(nested)) {
        // Per-property errors: show "Label: message" for each.
        setError(
          Object.entries(nested as Record<string, unknown>)
            .map(([key, msg]) => {
              const def = deviceSchema.find((a) => a.key === key);
              const text = [msg].flat().map(String).map((m) => i18n.t(m)).join(" ");
              return `${def ? localizedText(def.label) || key : key}: ${text}`;
            })
            .join(" "),
        );
      } else {
        setError(err instanceof Error ? err.message : t("Save failed."));
      }
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
        {resourceId === null
          ? t("New resource")
          : t("Edit {{number}}", { number: initial.inventory_number })}
      </h3>

      <div className="grid grid-cols-2 gap-3">
        <Field label={t("Product")}>
          <select
            value={form.product}
            onChange={(e) => set("product", Number(e.target.value))}
            className={inputClass}
          >
            <option value={0}>{t("— Select a product —")}</option>
            {allProducts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("Resource pool")}>
          <select
            value={form.resource_pool}
            onChange={(e) => set("resource_pool", Number(e.target.value))}
            className={inputClass}
          >
            <option value={0}>{t("— Select a pool —")}</option>
            {allPools.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("Inventory number")}>
          <input
            required
            value={form.inventory_number}
            onChange={(e) => {
              setNumberLocked(true);
              set("inventory_number", e.target.value);
            }}
            className={inputClass}
          />
          {autoSuggest && !numberLocked && (
            <span className="mt-0.5 block text-[11px] text-slate-400 dark:text-slate-300">
              {t("Auto-suggested from the pool — edit to override.")}
            </span>
          )}
        </Field>
        <Field label={t("Serial number")}>
          <input
            value={form.serial_number}
            onChange={(e) => set("serial_number", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label={t("Status")}>
          <select
            value={form.status}
            onChange={(e) =>
              set("status", e.target.value as ManageResourceInput["status"])
            }
            className={inputClass}
          >
            {RESOURCE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("Defect note")}>
          <input
            value={form.defect_note}
            onChange={(e) => set("defect_note", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label={t("Storage location")}>
          <input
            value={form.storage_location}
            onChange={(e) => set("storage_location", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label={t("Value (€)")}>
          <input
            value={form.value ?? ""}
            onChange={(e) => set("value", e.target.value || null)}
            placeholder={t("e.g. 1200.00")}
            className={inputClass}
          />
        </Field>
        <Field label={t("Procurement date")}>
          <DateField
            className="mt-1 block"
            ariaLabel={t("Procurement date")}
            value={form.procurement_date ?? ""}
            onChange={(v) => set("procurement_date", v || null)}
          />
        </Field>
        <Field label={t("Warranty end")}>
          <DateField
            className="mt-1 block"
            ariaLabel={t("Warranty end")}
            value={form.warranty_end ?? ""}
            onChange={(v) => set("warranty_end", v || null)}
          />
        </Field>
        <Field label={t("Procuring institution")}>
          <input
            value={form.procuring_institution}
            onChange={(e) => set("procuring_institution", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label={t("Owning institution")}>
          <input
            value={form.owning_institution}
            onChange={(e) => set("owning_institution", e.target.value)}
            className={inputClass}
          />
        </Field>
      </div>

      {deviceSchema.length > 0 && (
        <fieldset className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800">
          <legend className="px-1 text-xs font-medium text-slate-600 dark:text-slate-300">
            {t("Properties")}
          </legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {deviceSchema.map((a) => (
              <AttributeField
                key={a.key}
                attr={a}
                value={form.attributes[a.key] ?? a.default}
                onChange={(v) => set("attributes", { ...form.attributes, [a.key]: v })}
              />
            ))}
          </div>
        </fieldset>
      )}

      <fieldset className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800">
        <legend className="px-1 text-xs font-medium text-slate-600 dark:text-slate-300">
          {t("Lending duration")}
        </legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <DurationLimitField
            label={t("Min duration")}
            value={form.min_duration}
            onChange={(v) => set("min_duration", v)}
            unit={unit}
            inheritLabel={t("Inherit from product")}
            inheritedHint={inheritedMin.hint}
            suggestion={inheritedMin.value}
          />
          <DurationLimitField
            label={t("Max duration")}
            value={form.max_duration}
            onChange={(v) => set("max_duration", v)}
            unit={unit}
            inheritLabel={t("Inherit from product")}
            inheritedHint={inheritedMax.hint}
            suggestion={inheritedMax.value}
          />
        </div>
      </fieldset>

      <details className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800">
        <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-300">
          {t("Advanced")}
        </summary>
        <div className="mt-2">
          <Field label={t("QR code ID")}>
            <input
              value={form.qr_code_id}
              onChange={(e) => set("qr_code_id", e.target.value)}
              className={inputClass}
            />
            <span className="mt-0.5 block text-[11px] text-slate-500 dark:text-slate-400">
              {resourceId === null
                ? t("Assigned automatically if left empty. Printed labels use this ID — change it only for existing labels.")
                : t("Clearing it keeps the current ID. Printed labels use this ID — change it only for existing labels.")}
            </span>
          </Field>
        </div>
      </details>

      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

      <FormActionBar saving={busy} onCancel={onClose} dirty={dirty} />
    </form>
  );
}
