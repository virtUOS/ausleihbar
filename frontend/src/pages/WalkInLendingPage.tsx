// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";
import { durationRange, limitValue } from "../durations";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { setPoolScopeLocked } from "../poolScope";
import { BookingCalendar } from "../components/BookingCalendar";
import { HourlyBookingCalendar } from "../components/HourlyBookingCalendar";
import { ManageTabs } from "../components/ManageTabs";
import { GroupedProductPicker } from "../components/GroupedProductPicker";
import { SortToggle } from "../components/SortToggle";
import { useConfirm } from "../components/ConfirmDialog";
import { ErrorBox, Loading } from "../components/Status";
import type {
  BorrowerCandidate,
  WalkinPool,
  LendingType,
  WalkinProduct,
  WalkinResource,
} from "../types";

interface DraftItem {
  product: number;
  title: string;
  start: string;
  end: string;
  resource: number;
  resourceLabel: string;
  resourceConflict: boolean;
  /** Hourly hand-out length: start/end are re-taken from "now" on submit. */
  handoutHours?: number;
  /** Effective limit range when the period lies outside it (warning only). */
  outsideRange?: string;
}

type Mode = "now" | "later";

const inputClass =
  "block w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-sm text-slate-900 dark:text-slate-100 dark:bg-slate-800";

function formatBound(value: string): string {
  // Daily slots come as plain dates; hourly slots as full datetimes.
  return value.includes("T") ? new Date(value).toLocaleString() : value;
}

/** Today as a local yyyy-mm-dd string (for the immediate-handout period). */
function todayStr(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Parse a slot bound; a date-only end covers the whole day (→ next midnight). */
function toDate(value: string, isEnd: boolean): Date {
  if (value.includes("T")) return new Date(value);
  const [y, m, d] = value.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  if (isEnd) dt.setDate(dt.getDate() + 1);
  return dt;
}

/** `d` floored to the full hour (start of an hourly hand-out). */
function floorToHour(d: Date): Date {
  const x = new Date(d);
  x.setMinutes(0, 0, 0);
  return x;
}

/** `d` plus `n` wall-clock hours (matches how the backend counts hours). */
function addHours(d: Date, n: number): Date {
  const x = new Date(d);
  x.setHours(x.getHours() + n);
  return x;
}

/** Fallback length of an hourly hand-out when the product has no max. */
const DEFAULT_HANDOUT_HOURS = 2;

/** Local wall-clock time of `d` as a timezone-free millisecond count. */
function wallClock(d: Date): number {
  return Date.UTC(
    d.getFullYear(), d.getMonth(), d.getDate(),
    d.getHours(), d.getMinutes(), d.getSeconds(), d.getMilliseconds(),
  );
}

/** The hourly hand-out period: from the current full hour for `hours` hours. */
function hourlyHandoutPeriod(hours: number): { start: string; end: string } {
  const start = floorToHour(new Date());
  return { start: start.toISOString(), end: addHours(start, hours).toISOString() };
}

/** Length of a period in the product's unit, counted like the backend:
 *  days = calendar days touched (start day inclusive), hours = started
 *  local wall-clock hours (so a DST day counts the slots, not elapsed time). */
function periodLength(start: string, end: string, unit: LendingType): number {
  const s = toDate(start, false);
  const e = toDate(end, true);
  if (unit === "hours") {
    return Math.max(1, Math.ceil((wallClock(e) - wallClock(s)) / 3_600_000));
  }
  const last = new Date(e.getTime() - 1);
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((day(last) - day(s)) / 86_400_000) + 1;
}

/** Whether `length` lies outside [min, max] (null = open side). */
function outsideLimits(length: number, min: number | null, max: number | null): boolean {
  const lo = limitValue(min);
  const hi = limitValue(max);
  return (lo !== null && length < lo) || (hi !== null && length > hi);
}

/** Whether the lending period of an item currently covers "now". */
function coversNow(item: DraftItem): boolean {
  const now = new Date();
  return toDate(item.start, false) <= now && now < toDate(item.end, true);
}

export function WalkInLendingPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const confirm = useConfirm();
  const context = useFetch<{ pools: WalkinPool[] }>(
    () => api.getWalkinContext(),
    [],
  );

  const [poolId, setPoolId] = useState<number | null>(null);
  const [borrowerQuery, setBorrowerQuery] = useState("");
  const [results, setResults] = useState<BorrowerCandidate[]>([]);
  const [borrower, setBorrower] = useState<BorrowerCandidate | null>(null);
  const [productQuery, setProductQuery] = useState("");
  const [product, setProduct] = useState<WalkinProduct | null>(null);
  const [items, setItems] = useState<DraftItem[]>([]);
  // The basket lives only in this page's state; a pool-scope switch remounts
  // the page, so lock the switch while it holds items.
  const hasItems = items.length > 0;
  useEffect(() => {
    setPoolScopeLocked(hasItems);
    return () => setPoolScopeLocked(false);
  }, [hasItems]);
  // Slot picked in the calendar, awaiting a unit choice.
  const [pending, setPending] = useState<{ start: string; end: string } | null>(null);
  const [resourceId, setResourceId] = useState<number | null>(null);
  // "now" hands out on the spot, "later" creates a confirmed booking.
  const [mode, setMode] = useState<Mode>("now");
  const handOut = mode === "now";
  // Immediate hand-outs of daily products run from today until this return
  // date, asked after the product is chosen; it is kept as the default for
  // the next daily product. Reservations use the calendars instead.
  const [returnDate, setReturnDate] = useState("");
  const [note, setNote] = useState("");
  const [dateWarning, setDateWarning] = useState(false);
  // Hourly products handed out now run from the current full hour for this
  // many hours (daily ones use the return date above) (#109).
  const [handoutHours, setHandoutHours] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const pools = context.data?.pools ?? [];
  useEffect(() => {
    if (poolId === null && pools.length) setPoolId(pools[0].id);
  }, [pools, poolId]);
  const noteRequired = !!pools.find((p) => p.id === poolId)?.require_booking_note;
  const noteMissing = noteRequired && note.trim() === "";

  const productsFetch = useFetch<{ products: WalkinProduct[] }>(
    () =>
      poolId
        ? api.getWalkinProducts(poolId)
        : Promise.resolve({ products: [] }),
    [poolId],
  );
  const products = productsFetch.data?.products ?? [];

  // The lending period awaiting a unit choice: for an immediate hand-out it is
  // today → the required return date (daily products) or the current full hour
  // + n hours (hourly products, ISO datetimes); for a reservation it is the
  // calendar slot.
  const hourlyHandOut = handOut && product?.lending_type === "hours";
  // Re-taken on every render (and again on commit/submit), so a page left
  // open past the hour doesn't hand out from a stale start.
  const hoursCount = parseInt(handoutHours, 10);
  const validHours = Number.isFinite(hoursCount) && hoursCount > 0;
  const period = !handOut
    ? pending
    : hourlyHandOut
      ? validHours
        ? hourlyHandoutPeriod(hoursCount)
        : null
      : returnDate
        ? { start: todayStr(), end: returnDate }
        : null;

  // Units of the pending product/period, so the lender can pick the one handed out.
  const resourcesFetch = useFetch<{ resources: WalkinResource[] }>(
    () =>
      period && product && poolId
        ? api.getWalkinResources(poolId, product.id, period.start, period.end)
        : Promise.resolve({ resources: [] }),
    [period?.start, period?.end, product?.id, poolId],
  );
  const resources = resourcesFetch.data?.resources ?? [];
  // Default to the first conflict-free unit (else the first), once loaded.
  useEffect(() => {
    if (!period || resources.length === 0) return;
    const free = resources.find((r) => !r.conflict);
    setResourceId((free ?? resources[0]).id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period?.start, period?.end, resources]);
  const selectedResource = resources.find((r) => r.id === resourceId) ?? null;
  // The chosen period's length vs. the limits — of the selected unit once one
  // is picked, else the product's range in this pool — so the lender sees the
  // problem before submitting.
  // Limits only warn; adding and submitting are never blocked.
  const limitsSource = selectedResource ?? product;
  const periodOutside =
    !!product &&
    !!period &&
    !!limitsSource &&
    outsideLimits(
      periodLength(period.start, period.end, product.lending_type),
      limitsSource.effective_min_duration,
      limitsSource.effective_max_duration,
    );
  const outsideRange =
    periodOutside && product && limitsSource
      ? durationRange(
          limitsSource.effective_min_duration,
          limitsSource.effective_max_duration,
          product.lending_type,
        )
      : undefined;

  // Debounced borrower search.
  useEffect(() => {
    const term = borrowerQuery.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    const handle = setTimeout(() => {
      api.searchBorrowers(term).then(setResults).catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(handle);
  }, [borrowerQuery]);

  if (user && !user.is_lender && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  function changePool(id: number) {
    setPoolId(id);
    setProduct(null);
    setProductQuery("");
    setPending(null);
    setItems([]); // products belong to the pool; start fresh
    setMessage(null);
  }

  // Product picked: an hourly hand-out defaults to the effective max hours.
  function chooseProduct(p: WalkinProduct) {
    setProduct(p);
    setMessage(null);
    if (p.lending_type === "hours") {
      const max = limitValue(p.effective_max_duration);
      const min = limitValue(p.effective_min_duration) ?? 1;
      setHandoutHours(String(max ?? Math.max(min, DEFAULT_HANDOUT_HOURS)));
    }
  }

  // Switching between immediate hand-out and reservation drops the items and
  // the open product step, so the two date sources (return date vs.
  // calendar) never mix. With items listed, ask first.
  async function changeMode(next: Mode) {
    if (next === mode) return;
    if (
      items.length > 0 &&
      !(await confirm({ message: t("Switching mode removes the items chosen so far.") }))
    ) {
      return;
    }
    setMode(next);
    setItems([]);
    setProduct(null);
    setProductQuery("");
    setPending(null);
    setResourceId(null);
    setReturnDate("");
    setHandoutHours("");
    setDateWarning(false);
    setMessage(null);
  }

  // Calendar slot chosen -> ask which unit is handed out (resource picker).
  async function addSlot(start: string, end: string) {
    setPending({ start, end });
    setResourceId(null);
    setMessage(null);
  }

  function commitItem() {
    if (!product || !period || !selectedResource) return;
    // An hourly hand-out starts at the current full hour at commit time.
    const committed = hourlyHandOut && validHours ? hourlyHandoutPeriod(hoursCount) : period;
    setItems((prev) => [
      ...prev,
      {
        product: product.id,
        title: product.title,
        start: committed.start,
        end: committed.end,
        resource: selectedResource.id,
        resourceLabel: selectedResource.inventory_number,
        resourceConflict: selectedResource.conflict,
        ...(hourlyHandOut && validHours ? { handoutHours: hoursCount } : {}),
        ...(outsideRange ? { outsideRange } : {}),
      },
    ]);
    // Back to the product list so the next item can be picked right away.
    // The return date is kept so further hand-out items reuse it.
    setPending(null);
    setProduct(null);
    setProductQuery("");
    setDateWarning(false);
  }

  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index));
    setDateWarning(false);
  }

  // Hand-out for a period that doesn't include today is allowed, but warned.
  const handOutDateMismatch = handOut && items.some((i) => !coversNow(i));

  function attemptSubmit() {
    if (handOutDateMismatch && !dateWarning) {
      setDateWarning(true);
      return;
    }
    submit();
  }

  async function submit() {
    setDateWarning(false);
    if (!borrower || !poolId || items.length === 0 || noteMissing) return;
    setBusy(true);
    setMessage(null);
    try {
      const booking = await api.createWalkin({
        borrower: borrower.id,
        pool: poolId,
        hand_out: handOut,
        note: note.trim(),
        items: items.map((i) => ({
          product: i.product,
          resource: i.resource,
          // Hourly hand-outs run from the current full hour at submit time.
          ...(handOut && i.handoutHours
            ? hourlyHandoutPeriod(i.handoutHours)
            : { start: i.start, end: i.end }),
        })),
      });
      setMessage({
        ok: true,
        text: handOut
          ? t("Created {{code}} — handed out for {{user}}.", {
              code: booking.code,
              user: borrower.username,
            })
          : t("Created {{code}} — reserved for {{user}}.", {
              code: booking.code,
              user: borrower.username,
            }),
      });
      setItems([]);
      setProduct(null);
      setBorrower(null);
      setBorrowerQuery("");
      setNote("");
      setReturnDate("");
      setHandoutHours("");
    } catch (err) {
      // Includes a 400 `note_required` (the pool's note setting changed
      // meanwhile): its detail is shown like any other error.
      setMessage({
        ok: false,
        text: err instanceof Error ? err.message : t("Could not create the lending."),
      });
    } finally {
      setBusy(false);
    }
  }

  // Each item carries its own period (return date or hours), so nothing else
  // is required here.
  const canSubmit = Boolean(borrower && poolId && items.length > 0 && !busy && !noteMissing);

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("Lending desk")}</h1>
      <ManageTabs showPoolScope />

      <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Walk-in lending")}</h2>
      <div className="mt-2">
        <SortToggle<Mode>
          value={mode}
          onChange={changeMode}
          label={t("Walk-in lending")}
          options={[
            { value: "now", label: t("Hand out now") },
            { value: "later", label: t("Booking for later") },
          ]}
        />
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {handOut
            ? t("Handed out to the person right away; you choose the return date.")
            : t("Creates a confirmed booking for the person; pickup later at the desk.")}
        </p>
      </div>
      <p className="mb-4 mt-2 text-xs text-slate-600 dark:text-slate-300">
        {t(
          "Lend out on the spot for someone at the desk. Lead time and the booking horizon are skipped; availability is still checked.",
        )}
      </p>

      {context.loading && <Loading />}
      {context.error && <ErrorBox message={context.error} />}

      {context.data && pools.length === 0 && (
        <p className="rounded-lg bg-amber-50 dark:bg-amber-950/40 p-3 text-sm text-amber-800 dark:text-amber-300">
          {t("You don't manage any pool yet.")}
        </p>
      )}

      {context.data && pools.length > 0 && (
        <div className="space-y-5">
          {/* Borrower */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("1. Borrower")}</h3>
            {borrower ? (
              <div className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-800/50 p-3">
                <div className="text-sm">
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    {borrower.username}
                  </span>
                  {borrower.full_name && (
                    <span className="text-slate-600 dark:text-slate-300"> · {borrower.full_name}</span>
                  )}
                  {borrower.is_blocked && (
                    <span className="ml-2 rounded-full bg-red-100 dark:bg-red-950/50 px-2 py-0.5 text-xs font-medium text-red-700 dark:text-red-300">
                      {t("suspended")}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setBorrower(null)}
                  className="text-sm text-slate-600 dark:text-slate-300 hover:underline"
                >
                  {t("Change")}
                </button>
              </div>
            ) : (
              <div className="relative">
                <input
                  value={borrowerQuery}
                  onChange={(e) => setBorrowerQuery(e.target.value)}
                  placeholder={t("Search by name, username or e-mail…")}
                  className={inputClass}
                />
                {results.length > 0 && (
                  <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg">
                    {results.map((candidate) => (
                      <li key={candidate.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setBorrower(candidate);
                            setResults([]);
                          }}
                          className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700"
                        >
                          <span className="font-medium text-slate-900 dark:text-slate-100">
                            {candidate.username}
                          </span>
                          {candidate.full_name && (
                            <span className="text-slate-600 dark:text-slate-300">
                              {" "}
                              · {candidate.full_name}
                            </span>
                          )}
                          {candidate.is_blocked && (
                            <span className="ml-2 text-xs text-red-600 dark:text-red-300">{t("suspended")}</span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </section>

          {/* Pool + product + calendar */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("2. Items")}</h3>
            <label className="block text-xs text-slate-600 dark:text-slate-300">
              {t("Pool")}
              <select
                value={poolId ?? ""}
                onChange={(e) => changePool(Number(e.target.value))}
                className={`mt-1 ${inputClass}`}
              >
                {pools.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.room ? ` · ${p.room}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <div className="mt-3">
              <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Product")}</p>
              {product ? (
                <div className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-800/50 p-3">
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {product.title}
                  </span>
                  <button
                    type="button"
                    onClick={() => setProduct(null)}
                    className="text-sm text-slate-600 dark:text-slate-300 hover:underline"
                  >
                    {t("Change")}
                  </button>
                </div>
              ) : (
                <>
                  <GroupedProductPicker
                    products={products}
                    query={productQuery}
                    onQueryChange={setProductQuery}
                    onPick={chooseProduct}
                    placeholder={t("Search products in this pool…")}
                    renderMeta={(p) => (
                      <>
                        {p.lending_type === "hours" ? t("hourly") : t("daily")}
                        {(limitValue(p.effective_min_duration) !== null ||
                          limitValue(p.effective_max_duration) !== null) &&
                          ` · ${durationRange(p.effective_min_duration, p.effective_max_duration, p.lending_type)}`}
                      </>
                    )}
                  />
                  {productsFetch.loading && (
                    <p className="mt-1 text-xs text-slate-400 dark:text-slate-300">{t("Loading…")}</p>
                  )}
                </>
              )}
            </div>

            {/* Effective limits of the chosen product in this pool (#109). */}
            {product && (
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
                {t("Lending duration in this pool: {{range}}", {
                  range: durationRange(
                    product.effective_min_duration,
                    product.effective_max_duration,
                    product.lending_type,
                  ),
                })}
              </p>
            )}

            {/* Hourly hand-out: from the current full hour for n hours. */}
            {hourlyHandOut && product && (
              <label className="mt-3 block text-xs text-slate-600 dark:text-slate-300">
                {t("Duration (hours)")}
                <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={handoutHours}
                  onChange={(e) => setHandoutHours(e.target.value)}
                  className={`mt-1 sm:w-32 ${inputClass}`}
                />
                {period && (
                  <span className="mt-1 block text-slate-500 dark:text-slate-400">
                    {t("Handed out from {{start}}, due back at {{end}}.", {
                      start: formatBound(period.start),
                      end: formatBound(period.end),
                    })}
                  </span>
                )}
              </label>
            )}

            {/* Daily hand-out: from today until the return date (kept for the
                next daily product). */}
            {handOut && product && !hourlyHandOut && (
              <label className="mt-3 block text-xs text-slate-600 dark:text-slate-300">
                {t("Return date")}
                <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                <input
                  type="date"
                  required
                  min={todayStr()}
                  value={returnDate}
                  onChange={(e) => setReturnDate(e.target.value)}
                  className={`mt-1 sm:w-52 ${inputClass}`}
                />
                <span className="mt-1 block text-slate-500 dark:text-slate-400">
                  {t("Handed out today, due back on this date.")}
                </span>
              </label>
            )}

            {/* Reservation only: reuse the booking calendars (lead time / horizon off). */}
            {!handOut && product && poolId != null && !pending && (
              product.lending_type === "hours" ? (
                <HourlyBookingCalendar
                  key={`${poolId}-${product.id}`}
                  fetchCalendar={(from, to) =>
                    api.getWalkinHourlyCalendar(poolId, product.id, from, to)
                  }
                  fetchDay={(date) => api.getWalkinHourly(poolId, product.id, date)}
                  onAdd={addSlot}
                  reloadKey={`walkin-${poolId}-${product.id}`}
                  addLabel={t("Choose unit…")}
                  showCartLink={false}
                  enforceLimits={false}
                />
              ) : (
                <BookingCalendar
                  key={`${poolId}-${product.id}`}
                  fetchCalendar={(from, to) =>
                    api.getWalkinCalendar(poolId, product.id, from, to)
                  }
                  onAdd={addSlot}
                  reloadKey={`walkin-${poolId}-${product.id}`}
                  addLabel={t("Choose unit…")}
                  showCartLink={false}
                />
              )
            )}

            {/* Resource picker: which physical unit is handed out. */}
            {product && period && (
              <div className="mt-4 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
                <h4 className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  {t("Which unit of {{product}}?", { product: product.title })}
                </h4>
                <p className="mb-2 text-xs text-slate-600 dark:text-slate-300">
                  {formatBound(period.start)} → {formatBound(period.end)}
                </p>
                {outsideRange && (
                  <p className="mb-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                    {t("Outside the lending-duration limit ({{range}}).", { range: outsideRange })}
                  </p>
                )}
                {resourcesFetch.loading && (
                  <p className="text-xs text-slate-400 dark:text-slate-300">{t("Loading units…")}</p>
                )}
                {!resourcesFetch.loading && resources.length === 0 && (
                  <p className="text-sm text-amber-700 dark:text-amber-300">
                    {t("No lendable units in this pool.")}
                  </p>
                )}
                <div className="space-y-1">
                  {resources.map((r) => (
                    <label
                      key={r.id}
                      className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      <input
                        type="radio"
                        name="walkin-resource"
                        checked={resourceId === r.id}
                        onChange={() => setResourceId(r.id)}
                      />
                      <span className="font-medium text-slate-900 dark:text-slate-100">
                        {r.inventory_number}
                      </span>
                      {(limitValue(r.effective_min_duration) !== limitValue(product.effective_min_duration) ||
                        limitValue(r.effective_max_duration) !== limitValue(product.effective_max_duration)) && (
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {durationRange(r.effective_min_duration, r.effective_max_duration, product.lending_type)}
                        </span>
                      )}
                      {r.conflict ? (
                        <span className="rounded-full bg-amber-100 dark:bg-amber-950/50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-300">
                          {t("time conflict")}
                        </span>
                      ) : (
                        <span className="text-xs text-green-700 dark:text-green-300">{t("free")}</span>
                      )}
                    </label>
                  ))}
                </div>
                {selectedResource?.conflict && (
                  <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                    {t(
                      "This unit is already booked in the selected period — pick another, or it can't be handed out.",
                    )}
                  </p>
                )}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={commitItem}
                    disabled={!selectedResource || selectedResource.conflict}
                    className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
                  >
                    {t("Add to lending")}
                  </button>
                  <button
                    type="button"
                    onClick={() => (handOut ? setProduct(null) : setPending(null))}
                    className="rounded-full border border-slate-300 dark:border-slate-600 px-4 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    {t("Back")}
                  </button>
                </div>
              </div>
            )}

            {items.length > 0 && (
              <ul className="mt-3 space-y-1">
                {items.map((item, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2 text-sm"
                  >
                    <span>
                      <span className="font-medium text-slate-900 dark:text-slate-100">{item.title}</span>
                      <span className="text-slate-600 dark:text-slate-300">
                        {" · "}
                        {item.resourceLabel}
                        {" · "}
                        {formatBound(item.start)} → {formatBound(item.end)}
                      </span>
                      {item.outsideRange && (
                        <span className="mt-1 block w-fit rounded-md bg-amber-50 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                          {t("Outside the lending-duration limit ({{range}}).", { range: item.outsideRange })}
                        </span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeItem(i)}
                      className="text-red-600 dark:text-red-300 hover:underline"
                    >
                      {t("Remove")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Confirm */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{t("3. Confirm")}</h3>
            <label className="mb-3 block text-xs text-slate-600 dark:text-slate-300">
              {noteRequired ? (
                <>
                  {t("Note")}
                  <span className="ml-0.5 text-red-600 dark:text-red-400">*</span>
                </>
              ) : (
                t("Note (optional)")
              )}
              <textarea
                rows={2}
                required={noteRequired}
                aria-describedby={noteMissing ? "walkin-note-hint" : undefined}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("e.g. reason for the lending, agreed return, …")}
                className={`mt-1 ${inputClass}`}
              />
              {noteMissing && (
                <span id="walkin-note-hint" className="mt-1 block text-amber-700 dark:text-amber-300">
                  {t("This pool requires a note.")}
                </span>
              )}
            </label>

            {dateWarning && (
              <div className="mt-3 rounded-lg border border-amber-300 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 p-3 text-sm text-amber-800 dark:text-amber-300">
                <p>
                  {t(
                    "Today isn't within the selected lending period for one or more items. You can hand out anyway.",
                  )}
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => submit()}
                    disabled={busy}
                    className="rounded-full bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40"
                  >
                    {busy ? t("Saving…") : t("Hand out anyway")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDateWarning(false)}
                    className="rounded-full border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    {t("Cancel action")}
                  </button>
                </div>
              </div>
            )}

            <div className="mt-3">
              <button
                type="button"
                onClick={attemptSubmit}
                disabled={!canSubmit || dateWarning}
                className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
              >
                {busy ? t("Saving…") : handOut ? t("Hand out") : t("Create booking")}
              </button>
              {message && (
                <p
                  className={`mt-2 text-sm ${
                    message.ok ? "text-green-700 dark:text-green-300" : "text-red-600 dark:text-red-300"
                  }`}
                >
                  {message.text}
                  {message.ok && (
                    <>
                      {" "}
                      <Link
                        to="/manage/list"
                        className="font-medium underline underline-offset-2"
                      >
                        {t("View bookings")}
                      </Link>
                    </>
                  )}
                </p>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
