// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { formatDate, formatDateTime } from "../dates";
import { ManageTabs } from "../components/ManageTabs";
import { Empty, ErrorBox, Loading } from "../components/Status";
import type {
  LendingOverview,
  Paginated,
  ResourceBooking,
  TreePool,
  TreeProduct,
  TreeResource,
} from "../types";

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  confirmed: "bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300",
  handed_out: "bg-purple-100 text-purple-800 dark:bg-purple-950/50 dark:text-purple-300",
  returned: "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-300",
  cancelled: "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
};

function fmt(iso: string | null): string {
  if (!iso) return "–";
  const d = new Date(iso);
  const hasTime = d.getHours() !== 0 || d.getMinutes() !== 0;
  return hasTime ? formatDateTime(iso) : formatDate(iso);
}

function Chevron({ open }: { open: boolean }) {
  return (
    <span className={`inline-block w-3 text-slate-400 dark:text-slate-400 ${open ? "rotate-90" : ""}`}>
      ›
    </span>
  );
}

export function BorrowersPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const { data, loading, error } = useFetch<LendingOverview>(
    () => api.getLendingOverview(),
    [],
  );

  const q = query.trim().toLowerCase();
  // Filter the tree to resources whose inventory number matches the search.
  const pools = useMemo(() => {
    const all = data?.pools ?? [];
    if (!q) return all;
    return all
      .map((pool) => ({
        ...pool,
        products: pool.products
          .map((product) => ({
            ...product,
            resources: product.resources.filter((r) =>
              r.inventory_number.toLowerCase().includes(q),
            ),
          }))
          .filter((product) => product.resources.length > 0),
      }))
      .filter((pool) => pool.products.length > 0);
  }, [data, q]);

  if (user && !user.is_lender) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>
    );
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("Search resource (inventory number)…")}
        className="mb-4 w-full max-w-sm rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
      />

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}
      {data && pools.length === 0 && (
        <Empty
          label={
            q
              ? t("No matching resources.")
              : t("No resources in your pools yet.")
          }
        />
      )}

      {data && pools.length > 0 && (
        <div className="space-y-2">
          {pools.map((pool) => (
            <PoolNode key={pool.id} pool={pool} forceOpen={Boolean(q)} />
          ))}
        </div>
      )}
    </div>
  );
}

function PoolNode({ pool, forceOpen }: { pool: TreePool; forceOpen: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const expanded = forceOpen || open;
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold text-slate-900 hover:bg-slate-50 dark:text-slate-100 dark:hover:bg-slate-800"
      >
        <Chevron open={expanded} />
        {pool.name}
        <span className="ml-auto text-xs font-normal text-slate-400 dark:text-slate-400">
          {t("{{count}} product", { count: pool.products.length })}
        </span>
      </button>
      {expanded && (
        <div className="space-y-1 border-t border-slate-100 px-2 py-2 dark:border-slate-800">
          {pool.products.map((product) => (
            <ProductNode key={product.id} product={product} forceOpen={forceOpen} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProductNode({
  product,
  forceOpen,
}: {
  product: TreeProduct;
  forceOpen: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const expanded = forceOpen || open;
  return (
    <div className="rounded-md">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-slate-800 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        <Chevron open={expanded} />
        <span className="font-medium">{product.title}</span>
        <span className="ml-auto text-xs text-slate-400 dark:text-slate-400">
          {t("{{count}} booking", { count: product.booking_count })}
        </span>
      </button>
      {expanded && (
        <div className="ml-4 space-y-1 border-l border-slate-100 pl-2 dark:border-slate-800">
          {product.resources.map((resource) => (
            <ResourceNode key={resource.id} resource={resource} />
          ))}
        </div>
      )}
    </div>
  );
}

function ResourceNode({ resource }: { resource: TreeResource }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
      >
        <Chevron open={open} />
        <span className="font-mono text-xs text-slate-700 dark:text-slate-300">
          {resource.inventory_number}
        </span>
        {resource.status !== "available" && (
          <span className="rounded-full bg-slate-100 px-1.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            {resource.status}
          </span>
        )}
        <span className="ml-auto text-xs text-slate-400 dark:text-slate-400">
          {t("{{count}} booking", { count: resource.booking_count })}
        </span>
      </button>
      {open && <ResourceBookings resourceId={resource.id} />}
    </div>
  );
}

function ResourceBookings({ resourceId }: { resourceId: number }) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const { data, loading, error } = useFetch<Paginated<ResourceBooking>>(
    () => api.getResourceBorrowers(resourceId, page),
    [resourceId, page],
  );

  if (loading)
    return <p className="px-2 py-2 text-xs text-slate-400 dark:text-slate-400">{t("Loading…")}</p>;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  if (data.count === 0) {
    return (
      <p className="px-2 py-2 text-xs text-slate-400 dark:text-slate-400">{t("No bookings yet.")}</p>
    );
  }

  const pageSize = 10;
  const totalPages = Math.max(1, Math.ceil(data.count / pageSize));

  return (
    <div className="mb-1 ml-4 rounded-md bg-slate-50 p-2 dark:bg-slate-800/50">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-slate-400 dark:text-slate-400">
          <tr>
            <th className="px-2 py-1 font-medium">{t("Borrower")}</th>
            <th className="px-2 py-1 font-medium">{t("Period")}</th>
            <th className="px-2 py-1 font-medium">{t("Status")}</th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((b, i) => (
            <tr key={`${b.code}-${i}`} className="border-t border-slate-200/60 dark:border-slate-800">
              <td className="px-2 py-1">
                <span className="font-medium text-slate-800 dark:text-slate-200">{b.borrower}</span>
                {b.borrower_name && (
                  <span className="text-slate-400 dark:text-slate-400"> · {b.borrower_name}</span>
                )}
                <span className="block text-xs text-slate-400 dark:text-slate-400">{b.code}</span>
              </td>
              <td className="px-2 py-1 text-xs text-slate-500 dark:text-slate-400">
                {fmt(b.start)} – {fmt(b.end)}
              </td>
              <td className="px-2 py-1">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    STATUS_STYLE[b.status] ?? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                  }`}
                >
                  {t(b.status)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="mt-2 flex items-center justify-end gap-3 text-xs text-slate-500 dark:text-slate-400">
          <button
            type="button"
            disabled={!data.previous}
            onClick={() => setPage((p) => p - 1)}
            className="rounded px-2 py-0.5 hover:bg-slate-200 disabled:opacity-40 dark:hover:bg-slate-700"
          >
            {t("‹ Prev")}
          </button>
          <span>{t("Page {{page}} / {{totalPages}}", { page, totalPages })}</span>
          <button
            type="button"
            disabled={!data.next}
            onClick={() => setPage((p) => p + 1)}
            className="rounded px-2 py-0.5 hover:bg-slate-200 disabled:opacity-40 dark:hover:bg-slate-700"
          >
            {t("Next ›")}
          </button>
        </div>
      )}
    </div>
  );
}
