// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ManageTabs } from "../components/ManageTabs";
import { ErrorBox, Loading } from "../components/Status";
import { DateField } from "../components/DateField";
import { FORMATS, printStylesheet, type LabelFormat } from "../components/qrLabelFormats";
import { QrLabelPicker, useLabelQr } from "../components/QrLabelPicker";
import type { ManageResource, Paginated, ResourcePool } from "../types";

/** A single printable device label: QR sticker + inventory number + product. */
function DeviceLabel({
  resource,
  format,
}: {
  resource: ManageResource;
  format: LabelFormat;
}) {
  const src = useLabelQr(`item:${resource.id}`, () => api.getInventoryQr(resource.id));

  const qr = `${Math.max(format.h - 6, 16)}mm`;
  return (
    <div
      className="qr-label flex items-center gap-2 rounded-md border border-slate-300 p-1.5 dark:border-slate-600"
      style={{ width: `${format.w}mm`, height: `${format.h}mm`, breakInside: "avoid" }}
    >
      <div
        className="flex shrink-0 items-center justify-center bg-white"
        style={{ width: qr, height: qr }}
      >
        {src ? (
          <img src={src} alt="" className="h-full w-full object-contain" />
        ) : (
          <span className="text-[8px] text-slate-400 dark:text-slate-300">…</span>
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate text-xs font-semibold text-slate-900 dark:text-slate-100">
          {resource.inventory_number}
        </p>
        <p className="truncate text-[10px] text-slate-600 dark:text-slate-300">{resource.product_title}</p>
        <p className="truncate text-[9px] text-slate-400 dark:text-slate-300">{resource.pool_name}</p>
      </div>
    </div>
  );
}

export function AdminQrLabelsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const pools = useFetch<Paginated<ResourcePool>>(() => api.listPools({ lending: true }), []);
  const [poolId, setPoolId] = useState<number | null>(null);
  const [createdAfter, setCreatedAfter] = useState("");
  const [formatId, setFormatId] = useState(FORMATS[0].id);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const format = FORMATS.find((f) => f.id === formatId) ?? FORMATS[0];
  // Static print stylesheet for the chosen format (page size + label layout).
  const printHref = printStylesheet(format);

  const poolList = pools.data?.results ?? [];
  useEffect(() => {
    if (poolId === null && poolList.length) setPoolId(poolList[0].id);
  }, [poolList, poolId]);

  const inventory = useFetch<Paginated<ManageResource>>(
    () =>
      poolId
        ? api.listInventory({
            pool: poolId,
            created_after: createdAfter || undefined,
            // All units: the search and "select all" work on the whole pool.
            pageSize: 2000, // the API maximum
          })
        : Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
    [poolId, createdAfter],
  );
  const items = useMemo(
    () =>
      (inventory.data?.results ?? []).map((r) => ({
        id: r.id,
        resource: r,
        search: [r.inventory_number, r.product_title, r.serial_number, r.storage_location].filter(Boolean).join(" "),
      })),
    [inventory.data],
  );
  // A new pool starts with an empty selection; the date filter keeps it,
  // but only listed labels are printed (and counted).
  useEffect(() => setSelected(new Set()), [poolId]);
  const printCount = items.filter((i) => selected.has(i.id)).length;

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  return (
    <div>
      <link rel="stylesheet" href={printHref} />
      <div className="print:hidden">
        <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
        <ManageTabs showPoolScope />

        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("QR labels")}</h2>
            <p className="text-xs text-slate-600 dark:text-slate-300">
              {t(
                "Printable item QR stickers. Each code links to the product page; the lending desk scans it to hand the unit out.",
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-slate-600 dark:text-slate-300">
              {t("Pool")}
              <select
                value={poolId ?? ""}
                onChange={(e) => setPoolId(Number(e.target.value))}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                {poolList.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-slate-600 dark:text-slate-300">
              {t("Created since")}
              <DateField
                className="mt-1 block"
                ariaLabel={t("Created since")}
                value={createdAfter}
                onChange={setCreatedAfter}
              />
            </label>
            <label className="text-xs text-slate-600 dark:text-slate-300">
              {t("Format")}
              <select
                value={formatId}
                onChange={(e) => setFormatId(e.target.value)}
                className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                {FORMATS.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            {createdAfter && (
              <button
                type="button"
                onClick={() => setCreatedAfter("")}
                className="rounded-full border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {t("Clear date")}
              </button>
            )}
            <button
              type="button"
              onClick={() => window.print()}
              disabled={printCount === 0}
              className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
            >
              {t("Print {{count}} label", { count: printCount })}
            </button>
          </div>
        </div>

        {(pools.loading || inventory.loading) && <Loading />}
        {inventory.error && <ErrorBox message={inventory.error} />}

      </div>

      {inventory.data && (
        <QrLabelPicker
          items={items}
          selected={selected}
          onSelectedChange={setSelected}
          render={(item) => <DeviceLabel resource={item.resource} format={format} />}
          emptyText={t("No items in this pool.")}
        />
      )}
    </div>
  );
}
