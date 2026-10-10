// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { Star } from "lucide-react";
import { localizedText } from "@basicbar/ui";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ManageTabs } from "../components/ManageTabs";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton } from "../components/RowActions";
import { ResourceForm, resourceToInput } from "../components/ResourceForm";
import { safeHttpUrl } from "../safeUrl";
import { formatDate, formatDateTime } from "../dates";
import type {
  AttributeDef,
  ManageProduct,
  Paginated,
  ProductType,
  ResourceDetail,
  ResourcePool,
} from "../types";

const STATUS_BADGE: Record<string, string> = {
  available: "text-green-700 dark:text-green-300",
  blocked: "text-amber-600 dark:text-amber-300",
  defective: "text-red-600 dark:text-red-300",
  retired: "text-slate-400 dark:text-slate-300",
};

function fmt(iso: string | null): string {
  return iso ? formatDateTime(iso) : "—";
}

export function AdminInventoryDetailPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { id } = useParams();
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [savingCondition, setSavingCondition] = useState(false);
  const [editing, setEditing] = useState(false);
  const { data, loading, error } = useFetch<ResourceDetail>(
    () => api.getInventoryItem(id!),
    [id, version],
  );
  const products = useFetch<Paginated<ManageProduct>>(
    () => api.listManagedProducts({ pageSize: 2000 }),
    [],
  );
  const productTypes = useFetch<Paginated<ProductType>>(
    () => api.listProductTypes({ pageSize: 2000 }),
    [],
  );
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000, lending: true }),
    [],
  );

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);

  const productType = data
    ? productTypes.data?.results.find(
        (pt) => pt.id === products.data?.results.find((p) => p.id === data.product)?.product_type,
      )
    : undefined;
  const deviceAttrs: AttributeDef[] = (productType?.attribute_schema ?? []).filter(
    (a) => a.scope === "device",
  );

  function attrValue(attr: AttributeDef, value: unknown): React.ReactNode {
    if (value === null || value === undefined || value === "") return "—";
    if (attr.type === "date") return formatDate(String(value));
    if (attr.type === "short_text" || attr.type === "long_text") {
      return localizedText(value as never) || "—";
    }
    if (attr.type === "url") {
      const href = safeHttpUrl(value);
      if (!href) return String(value);
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand-700 underline dark:text-brand-300"
        >
          {String(value)}
        </a>
      );
    }
    return String(value);
  }

  async function saveCondition(rating: number, conditionNote: string) {
    if (!data) return;
    setSavingCondition(true);
    try {
      await api.updateResource(data.id, {
        condition_rating: rating,
        condition_note: conditionNote,
      });
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Failed."));
    } finally {
      setSavingCondition(false);
    }
  }

  async function resolveDefect() {
    if (!data) return;
    setBusy(true);
    try {
      await api.markResourceAvailable(data.id);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Failed."));
    } finally {
      setBusy(false);
    }
  }

  async function reportDefect() {
    if (!data) return;
    setBusy(true);
    try {
      const res = await api.markResourceDefective(data.id, note.trim());
      setNote("");
      if (res.rebooked || res.unfulfilled) {
        alert(
          t("Marked defective. {{count}} booking(s) moved to another unit", {
            count: res.rebooked,
          }) +
            (res.unfulfilled
              ? t(
                  "; {{count}} could not be moved — those borrowers were notified.",
                  { count: res.unfulfilled },
                )
              : "."),
        );
      }
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : t("Failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <Link to="/manage/inventory" className="text-sm text-slate-500 hover:underline dark:text-slate-300">
        {t("‹ Back to inventory")}
      </Link>

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <div className="mt-3 space-y-5">
          <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {data.inventory_number}
                </h2>
                {/* The form needs the product, type and pool lists. */}
                {!editing && products.data && productTypes.data && pools.data && (
                  <EditButton label={t("Edit device")} onClick={() => setEditing(true)} />
                )}
              </div>
              <span className={`text-sm font-medium ${STATUS_BADGE[data.status] ?? ""}`}>
                {t(data.status)}
              </span>
            </div>
            {editing ? (
              <div className="mt-3">
                <ResourceForm
                  initial={resourceToInput(data)}
                  resourceId={data.id}
                  autoSuggest={false}
                  allProducts={products.data?.results ?? []}
                  allPools={pools.data?.results ?? []}
                  productTypes={productTypes.data?.results ?? []}
                  onClose={() => setEditing(false)}
                  onSaved={() => {
                    setEditing(false);
                    refetch();
                  }}
                />
              </div>
            ) : (
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
              <Row label={t("Product")} value={data.product_title} />
              <Row label={t("Pool")} value={data.pool_name} />
              <Row label={t("QR code")} value={data.qr_code_id} />
              <Row label={t("Storage location")} value={data.storage_location || "—"} />
              <Row label={t("Value")} value={data.value ? `€ ${data.value}` : "—"} />
              <Row label={t("Procurement date")} value={data.procurement_date ? formatDate(data.procurement_date) : "—"} />
              <Row label={t("Warranty end")} value={data.warranty_end ? formatDate(data.warranty_end) : "—"} />
              <Row label={t("Serial number")} value={data.serial_number || "—"} />
              {deviceAttrs.map((attr) => (
                <Row
                  key={attr.key}
                  label={localizedText(attr.label) || attr.key}
                  value={attrValue(attr, data.attributes?.[attr.key])}
                />
              ))}
              <Row
                label={t("Institution")}
                value={data.owning_institution || data.procuring_institution || "—"}
              />
            </dl>
            )}

            <div className="mt-4">
              <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
                {t("Condition (lender-only)")}
              </p>
              <div className="mt-1 flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    disabled={savingCondition}
                    aria-label={t("Set condition to {{n}} of 5", { n })}
                    onClick={() => saveCondition(n, data.condition_note)}
                    className={
                      n <= data.condition_rating
                        ? "text-brand-500"
                        : "text-slate-300 dark:text-slate-300"
                    }
                  >
                    <Star className="h-5 w-5 fill-current" />
                  </button>
                ))}
                <span className="ml-2 text-xs text-slate-600 dark:text-slate-300">
                  {data.condition_rating}/5
                </span>
              </div>
              <textarea
                defaultValue={data.condition_note}
                placeholder={t("Condition details (optional)…")}
                onBlur={(e) => {
                  if (e.target.value !== data.condition_note) {
                    saveCondition(data.condition_rating, e.target.value);
                  }
                }}
                className="mt-2 w-full rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                rows={2}
              />
            </div>

            {data.status === "defective" ? (
              <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm dark:bg-red-950/40">
                <p className="font-medium text-red-700 dark:text-red-300">
                  {t("Current defect")}
                  {data.defect_note ? `: ${data.defect_note}` : ""}
                </p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={resolveDefect}
                  className="mt-2 rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
                >
                  {t("Resolve defect (mark available)")}
                </button>
              </div>
            ) : (
              data.status === "available" && (
                <div className="mt-4 flex items-center gap-2">
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={t("Describe a defect…")}
                    className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                  />
                  <button
                    type="button"
                    disabled={busy}
                    onClick={reportDefect}
                    className="rounded-full border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    {t("Mark defective")}
                  </button>
                </div>
              )
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Defect history")}</h3>
            {data.defects.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">{t("No defects recorded.")}</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
                    <tr>
                      <th className="px-3 py-2">{t("Note")}</th>
                      <th className="px-3 py-2">{t("Reported")}</th>
                      <th className="px-3 py-2">{t("Resolved")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.defects.map((d) => (
                      <tr key={d.id} className="border-t border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-200">{d.note || "—"}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{fmt(d.reported_at)}</td>
                        <td className="px-3 py-2">
                          {d.resolved_at ? (
                            <span className="text-slate-600 dark:text-slate-300">{fmt(d.resolved_at)}</span>
                          ) : (
                            <span className="font-medium text-red-600 dark:text-red-300">{t("open")}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Lending history")}</h3>
            {data.bookings.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">{t("No bookings yet.")}</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
                    <tr>
                      <th className="px-3 py-2">{t("Borrower")}</th>
                      <th className="px-3 py-2">{t("From")}</th>
                      <th className="px-3 py-2">{t("To")}</th>
                      <th className="px-3 py-2">{t("Status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.bookings.map((b) => (
                      <tr key={b.booking_id} className="border-t border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-200">{b.borrower}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{fmt(b.start)}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{fmt(b.end)}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{t(b.status)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <dt className="text-slate-600 dark:text-slate-300">{label}</dt>
      <dd className="text-slate-900 dark:text-slate-100">{value}</dd>
    </>
  );
}
