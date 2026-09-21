// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { ManageTabs } from "../components/ManageTabs";
import { ErrorBox, Loading } from "../components/Status";
import type {
  CapacityMetric,
  CapacityStats,
  DefectStats,
  ProductStat,
  ProductStatsResponse,
  ProductTimeseries,
  TimeseriesPoint,
} from "../types";

const RANGES = [
  { days: 30, label: i18n.t("30 days") },
  { days: 90, label: i18n.t("90 days") },
  { days: 365, label: i18n.t("12 months") },
];

const BUCKETS: { key: "day" | "week" | "month"; label: string }[] = [
  { key: "day", label: i18n.t("Day") },
  { key: "week", label: i18n.t("Week") },
  { key: "month", label: i18n.t("Month") },
];

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toLocaleDateString("en-CA");
}

function formatDuration(hours: number): string {
  if (hours >= 48) return `${Math.round(hours / 24)} d`;
  return `${Math.round(hours)} h`;
}

function TrendBadge({ value }: { value: number }) {
  if (value === 0) return <span className="text-slate-400 dark:text-slate-400">→ 0</span>;
  const up = value > 0;
  return (
    <span className={up ? "text-green-700 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
      {up ? "▲ +" : "▼ "}
      {value}
    </span>
  );
}

export function StatsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [days, setDays] = useState(90);
  const [pool, setPool] = useState<number | "">("");
  const [selected, setSelected] = useState<number | null>(null);
  const [bucket, setBucket] = useState<"day" | "week" | "month">("week");

  const to = new Date().toLocaleDateString("en-CA");
  const from = isoDaysAgo(days);

  const { data, loading, error } = useFetch<ProductStatsResponse>(
    () => api.getProductStats({ from, to, pool: pool || undefined }),
    [from, to, pool],
  );

  const products = data?.products ?? [];

  // Default-select the most-booked product; keep selection valid as data changes.
  useEffect(() => {
    if (products.length === 0) {
      setSelected(null);
    } else if (!products.some((p) => p.id === selected)) {
      setSelected(products[0].id);
    }
  }, [products, selected]);

  if (user && !user.is_lender) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const maxBookings = products[0]?.bookings ?? 0;
  const totalBookings = products.reduce((sum, p) => sum + p.bookings, 0);
  const borrowed = products.filter((p) => p.bookings > 0).length;
  const rising = [...products]
    .filter((p) => p.trend > 0)
    .sort((a, b) => b.trend - a.trend)
    .slice(0, 5);
  const falling = [...products]
    .filter((p) => p.trend < 0)
    .sort((a, b) => a.trend - b.trend)
    .slice(0, 5);
  const selectedProduct = products.find((p) => p.id === selected) ?? null;

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r.days}
              type="button"
              onClick={() => setDays(r.days)}
              className={`rounded-full px-3 py-1 text-sm ${
                days === r.days
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
        {data && data.pools.length > 1 && (
          <select
            value={pool}
            onChange={(e) => setPool(e.target.value ? Number(e.target.value) : "")}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">{t("All pools")}</option>
            {data.pools.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <span className="text-xs text-slate-400 dark:text-slate-400">
          {from} – {to}
        </span>
      </div>

      <CapacitySection />

      {loading && <Loading />}
      {error && <ErrorBox message={error} />}

      {data && (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Kpi label={t("Bookings")} value={totalBookings} />
            <Kpi label={t("Products borrowed")} value={borrowed} />
            <Kpi label={t("Products in scope")} value={products.length} />
          </div>

          {selectedProduct && (
            <section className="mb-6 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {t("Usage over time · {{title}}", { title: selectedProduct.title })}
                </h2>
                <div className="flex gap-1">
                  {BUCKETS.map((b) => (
                    <button
                      key={b.key}
                      type="button"
                      onClick={() => setBucket(b.key)}
                      className={`rounded-full px-2.5 py-0.5 text-xs ${
                        bucket === b.key
                          ? "bg-slate-900 text-white"
                          : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                      }`}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              </div>
              <Timeseries
                productId={selectedProduct.id}
                from={from}
                to={to}
                pool={pool || undefined}
                bucket={bucket}
              />
            </section>
          )}

          <section className="mb-6">
            <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              {t("All products by bookings")}
            </h2>
            <p className="mb-2 text-xs text-slate-400 dark:text-slate-400">
              {t(
                "Select a product to see its usage over time. Never-borrowed products appear with 0 (candidates to retire).",
              )}
            </p>
            {products.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">{t("No products in scope.")}</p>
            ) : (
              <ul className="max-h-96 space-y-1.5 overflow-y-auto pr-1">
                {products.map((p, i) => (
                  <BarRow
                    key={p.id}
                    rank={i + 1}
                    product={p}
                    max={maxBookings}
                    selected={p.id === selected}
                    onSelect={() => setSelected(p.id)}
                  />
                ))}
              </ul>
            )}
          </section>

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <TrendList title={t("Rising demand")} items={rising} empty={t("No risers.")} />
            <TrendList title={t("Falling demand")} items={falling} empty={t("No fallers.")} />
          </div>

          <DefectSection pool={pool || undefined} />
        </>
      )}
    </div>
  );
}

function DefectSection({ pool }: { pool?: number }) {
  const { t } = useTranslation();
  const { data, loading, error } = useFetch<DefectStats>(
    () => api.getDefectStats(pool),
    [pool],
  );
  if (loading) return null;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const top = data.products.slice(0, 10);
  const max = top[0]?.incidents ?? 0;
  return (
    <section className="mt-8">
      <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Defects")}</h2>
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("Defective now")} value={data.currently_defective} />
        <Kpi label={t("Ever defective")} value={data.ever_defective} />
        <Kpi label={t("Total incidents")} value={data.incidents} />
        <Kpi label={t("Resources")} value={data.resources_total} />
      </div>
      {top.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">{t("No defects recorded.")}</p>
      ) : (
        <>
          <h3 className="mb-2 text-xs font-medium text-slate-500 dark:text-slate-400">
            {t("Most problematic products (by defect incidents)")}
          </h3>
          <ul className="space-y-1.5">
            {top.map((p, i) => {
              const pct = max > 0 ? Math.max(4, Math.round((p.incidents / max) * 100)) : 0;
              return (
                <li key={p.id} className="flex items-center gap-3 text-sm">
                  <span className="w-5 shrink-0 text-right text-xs text-slate-400 dark:text-slate-400">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex items-center justify-between gap-2">
                      <span className="truncate font-medium text-slate-800 dark:text-slate-200">
                        {p.title}
                      </span>
                      <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
                        {t("{{count}} incident", { count: p.incidents })}
                        {p.currently_defective > 0 && (
                          <span className="text-red-600 dark:text-red-400">
                            {" "}
                            · {t("{{count}} down now", { count: p.currently_defective })}
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                      <div
                        className="h-full rounded-full bg-red-400"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  );
}

/** Deployment-wide totals against the optional creation caps (system-wide,
 *  independent of the date/pool filter). Only shows a limit when one is set. */
function CapacitySection() {
  const { t } = useTranslation();
  const { data } = useFetch<CapacityStats>(() => api.getCapacityStats(), []);
  if (!data) return null;
  return (
    <div className="mb-5">
      <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Inventory & limits")}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <CapacityKpi label={t("Resources")} metric={data.resources} />
        <CapacityKpi label={t("Products")} metric={data.products} />
        <CapacityKpi label={t("Users")} metric={data.users} />
      </div>
    </div>
  );
}

function CapacityKpi({ label, metric }: { label: string; metric: CapacityMetric }) {
  const { t } = useTranslation();
  const pct =
    metric.max && metric.max > 0
      ? Math.min(100, Math.round((metric.count / metric.max) * 100))
      : null;
  const nearFull = pct !== null && pct >= 90;
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        {metric.count}
        {metric.max !== null && (
          <span className="text-base font-medium text-slate-400 dark:text-slate-400">
            {" / "}{metric.max}
          </span>
        )}
      </p>
      {metric.max === null ? (
        <p className="text-xs text-slate-400 dark:text-slate-400">{t("no limit")}</p>
      ) : (
        <>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              className={`h-full rounded-full ${nearFull ? "bg-red-500" : "bg-brand-400"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-400 dark:text-slate-400">
            {t("{{pct}}% of limit", { pct })}
          </p>
        </>
      )}
    </div>
  );
}

function BarRow({
  rank,
  product,
  max,
  selected,
  onSelect,
}: {
  rank: number;
  product: ProductStat;
  max: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const pct = max > 0 ? Math.round((product.bookings / max) * 100) : 0;
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={`flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left text-sm ${
          selected ? "bg-slate-100 ring-1 ring-slate-300 dark:bg-slate-800 dark:ring-slate-600" : "hover:bg-slate-50 dark:hover:bg-slate-800"
        }`}
      >
        <span className="w-5 shrink-0 text-right text-xs text-slate-400 dark:text-slate-400">{rank}</span>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center justify-between gap-2">
            <span className="truncate font-medium text-slate-800 dark:text-slate-200">
              {product.title}
            </span>
            <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
              {product.bookings}× · {formatDuration(product.booked_hours)} ·{" "}
              <TrendBadge value={product.trend} />
            </span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              className="h-full rounded-full bg-slate-800 dark:bg-slate-300"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      </button>
    </li>
  );
}

function Timeseries({
  productId,
  from,
  to,
  pool,
  bucket,
}: {
  productId: number;
  from: string;
  to: string;
  pool?: number;
  bucket: "day" | "week" | "month";
}) {
  const { data, loading, error } = useFetch<ProductTimeseries>(
    () => api.getProductTimeseries(productId, { from, to, pool, bucket }),
    [productId, from, to, pool, bucket],
  );
  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  return <LineChart series={data.series} bucket={bucket} />;
}

function formatTick(iso: string, bucket: "day" | "week" | "month"): string {
  const d = new Date(iso);
  if (bucket === "month") {
    return d.toLocaleDateString(i18n.language, { month: "short", year: "2-digit" });
  }
  return d.toLocaleDateString(i18n.language, { day: "2-digit", month: "2-digit" });
}

function LineChart({
  series,
  bucket,
}: {
  series: TimeseriesPoint[];
  bucket: "day" | "week" | "month";
}) {
  const { t } = useTranslation();
  const W = 640;
  const H = 200;
  const padL = 26;
  const padR = 10;
  const padT = 10;
  const padB = 26;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const n = series.length;
  const max = Math.max(1, ...series.map((s) => s.bookings));
  const total = series.reduce((sum, s) => sum + s.bookings, 0);

  if (n === 0 || total === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">{t("No bookings in this period.")}</p>;
  }

  const x = (i: number) => padL + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => padT + innerH - (v / max) * innerH;
  const line = series.map((s, i) => `${x(i)},${y(s.bookings)}`).join(" ");
  const area = `${x(0)},${padT + innerH} ${line} ${x(n - 1)},${padT + innerH}`;

  const tickEvery = Math.max(1, Math.ceil(n / 6));
  const ticks = series
    .map((s, i) => ({ s, i }))
    .filter(({ i }) => i % tickEvery === 0 || i === n - 1);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
      {/* y gridlines at 0 and max */}
      <line x1={padL} y1={y(0)} x2={W - padR} y2={y(0)} stroke="#e2e8f0" />
      <line x1={padL} y1={y(max)} x2={W - padR} y2={y(max)} stroke="#f1f5f9" />
      <text x={2} y={y(max) + 4} fontSize="10" fill="#94a3b8">
        {max}
      </text>
      <text x={2} y={y(0) + 4} fontSize="10" fill="#94a3b8">
        0
      </text>
      <polygon points={area} fill="#0f172a" opacity="0.07" />
      <polyline points={line} fill="none" stroke="#0f172a" strokeWidth="2" />
      {series.map((s, i) => (
        <circle key={s.start} cx={x(i)} cy={y(s.bookings)} r="2.5" fill="#0f172a">
          <title>
            {formatTick(s.start, bucket)}: {s.bookings}
          </title>
        </circle>
      ))}
      {ticks.map(({ s, i }) => (
        <text
          key={s.start}
          x={x(i)}
          y={H - 8}
          fontSize="10"
          fill="#94a3b8"
          textAnchor="middle"
        >
          {formatTick(s.start, bucket)}
        </text>
      ))}
    </svg>
  );
}

function TrendList({
  title,
  items,
  empty,
}: {
  title: string;
  items: ProductStat[];
  empty: string;
}) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {items.map((p) => (
            <li
              key={p.id}
              className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
            >
              <span className="truncate text-slate-800 dark:text-slate-200">{p.title}</span>
              <span className="shrink-0 text-xs">
                <span className="text-slate-400 dark:text-slate-400">
                  {p.prev_bookings} → {p.bookings}{" "}
                </span>
                <TrendBadge value={p.trend} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
