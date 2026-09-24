// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfirm } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { api } from "../api";
import type { ImageAction } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ListToolbar } from "../components/ListToolbar";
import { ImageCropField } from "../components/ImageCropField";
import { symbolFor } from "../emoji";
import { OpeningHoursEditor } from "../components/OpeningHoursEditor";
import { BlockDaysManager } from "../components/BlockDaysManager";
import { ErrorBox, Loading } from "../components/Status";
import { EditButton, DeleteButton } from "../components/RowActions";
import { ReorderControls } from "../components/ReorderControls";
import { useReorder } from "../useReorder";
import { TranslatableField } from "@basicbar/ui";
import { poolAccent, POOL_ACCENT_KEYS } from "../poolAccent";
import type { Paginated, ResourcePool, ResourcePoolInput } from "../types";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const EMPTY: ResourcePoolInput = {
  name_de: "",
  name_en: "",
  pool_id: "",
  description_de: "",
  description_en: "",
  address_de: "",
  address_en: "",
  room_de: "",
  room_en: "",
  image: "",
  directions_de: "",
  directions_en: "",
  phone: "",
  email: "",
  email_note_de: "",
  email_note_en: "",
  notify_on_defect: true,
  notify_on_cancellation: true,
  require_booking_note: false,
  opening_hours: {},
  closed_weekdays: [5, 6],
  lead_time_hours: 0,
  max_booking_months: 24,
  default_min_days: null,
  default_max_days: null,
  default_min_hours: null,
  default_max_hours: null,
  is_active: true,
  accent_color: "",
  email_language: "de",
};

function toInput(pool: ResourcePool): ResourcePoolInput {
  // Drop the read-only id/count and the bare translated fields (edited via
  // their `*_de` / `*_en` variants), then re-add the variants coerced to "".
  const {
    id: _id,
    resource_count: _rc,
    name: _n,
    description: _d,
    address: _a,
    room: _r,
    directions: _dir,
    email_note: _en0,
    ...rest
  } = pool;
  return {
    ...rest,
    name_de: pool.name_de ?? "",
    name_en: pool.name_en ?? "",
    description_de: pool.description_de ?? "",
    description_en: pool.description_en ?? "",
    address_de: pool.address_de ?? "",
    address_en: pool.address_en ?? "",
    room_de: pool.room_de ?? "",
    room_en: pool.room_en ?? "",
    directions_de: pool.directions_de ?? "",
    directions_en: pool.directions_en ?? "",
    email_note_de: pool.email_note_de ?? "",
    email_note_en: pool.email_note_en ?? "",
  };
}

export function AdminPoolsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const { user } = useAuth();
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState<ResourcePool | "new" | null>(null);
  const [reordering, setReordering] = useState(false);
  const [query, setQuery] = useState("");
  // Load the full list (reordering needs every row); filter/search client-side.
  const pools = useFetch<Paginated<ResourcePool>>(
    () => api.listPools({ pageSize: 2000 }),
    [version],
  );
  const rows = pools.data?.results ?? [];
  const reorder = useReorder(rows, api.reorderPools);

  if (user && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  const refetch = () => setVersion((v) => v + 1);
  const filtered = query.trim()
    ? rows.filter(
        (p) =>
          p.name.toLowerCase().includes(query.trim().toLowerCase()) ||
          p.pool_id.toLowerCase().includes(query.trim().toLowerCase()),
      )
    : rows;
  const displayRows = reordering ? reorder.order : filtered;

  async function remove(pool: ResourcePool) {
    if (
      !(await confirm({
        message: t("Move pool “{{name}}” to the trash?", { name: pool.name }),
        confirmLabel: t("Move to trash"),
        danger: true,
      }))
    )
      return;
    try {
      await api.deletePool(pool.id);
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
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Resource pools")}</h2>
        {editing === null && (
          <div className="flex gap-2">
            {rows.length > 1 && (
              <button
                type="button"
                onClick={() => setReordering((r) => !r)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                  reordering
                    ? "bg-slate-900 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                {reordering ? t("Done") : t("Reorder")}
              </button>
            )}
            {!reordering && (
              <button
                type="button"
                onClick={() => setEditing("new")}
                className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("+ New pool")}
              </button>
            )}
          </div>
        )}
      </div>

      {reordering && (
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
          {t(
            "Drag rows to reorder, or use the ↑ / ↓ buttons. New pools are always added at the end. Changes are saved automatically.",
          )}
        </p>
      )}

      {editing !== null && (
        <PoolForm
          initial={editing === "new" ? EMPTY : toInput(editing)}
          poolId={editing === "new" ? null : editing.id}
          accessGroups={editing === "new" ? [] : editing.access_groups ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refetch();
          }}
        />
      )}

      {editing === null && !reordering && rows.length > 0 && (
        <ListToolbar
          search={query}
          onSearch={setQuery}
          count={filtered.length}
          hidePager
          placeholder={t("Search pools…")}
        />
      )}

      {pools.loading && <Loading />}
      {pools.error && <ErrorBox message={pools.error} />}

      {pools.data && editing === null && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50 dark:text-slate-300">
              <tr>
                <th className="px-3 py-2">{t("Accent")}</th>
                <th className="px-3 py-2">{t("Name")}</th>
                <th className="px-3 py-2">{t("Active")}</th>
                <th className="px-3 py-2 text-right">
                  {reordering ? t("Order") : ""}
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((pool, i) => (
                <tr
                  key={pool.id}
                  draggable={reordering}
                  onDragStart={reordering ? () => reorder.onDragStart(pool.id) : undefined}
                  onDragEnter={reordering ? () => reorder.onDragEnter(pool.id) : undefined}
                  onDragOver={reordering ? (e) => e.preventDefault() : undefined}
                  onDrop={reordering ? reorder.onDrop : undefined}
                  className={`border-t border-slate-100 dark:border-slate-800 ${
                    reordering ? "cursor-grab bg-white dark:bg-slate-900" : ""
                  }`}
                >
                  <td className="px-3 py-2">
                    <span
                      aria-hidden
                      title={t(ACCENT_LABELS[pool.accent_color || "neutral"])}
                      className={`inline-block h-4 w-4 rounded-full ${poolAccent(pool.accent_color).dot}`}
                    />
                    <span className="sr-only">{t(ACCENT_LABELS[pool.accent_color || "neutral"])}</span>
                  </td>
                  <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{pool.name}</td>
                  <td className="px-3 py-2">
                    {pool.is_active ? (
                      <span className="text-green-700 dark:text-green-400">●</span>
                    ) : (
                      <span className="text-slate-300 dark:text-slate-300">●</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {reordering ? (
                      <div className="flex justify-end">
                        <ReorderControls
                          label={pool.name}
                          isFirst={i === 0}
                          isLast={i === displayRows.length - 1}
                          onUp={() => reorder.move(pool.id, -1)}
                          onDown={() => reorder.move(pool.id, 1)}
                        />
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-0.5">
                        <EditButton onClick={() => setEditing(pool)} />
                        <DeleteButton onClick={() => remove(pool)} />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {displayRows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-600 dark:text-slate-300">
                    {t("No pools yet.")}
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

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-xs text-slate-600 dark:text-slate-300">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

/** Human-readable label per palette key (#16), shown as the swatch tooltip. */
const ACCENT_LABELS: Record<string, string> = {
  neutral: "Neutral",
  amber: "Amber",
  sky: "Sky blue",
  emerald: "Emerald",
  violet: "Violet",
  rose: "Rose",
  teal: "Teal",
  orange: "Orange",
};

function PoolForm({
  initial,
  poolId,
  accessGroups,
  onClose,
  onSaved,
}: {
  initial: ResourcePoolInput;
  poolId: number | null;
  accessGroups: { id: number; name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ResourcePoolInput>(initial);
  const [imageAction, setImageAction] = useState<ImageAction>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof ResourcePoolInput>(key: K, value: ResourcePoolInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function numberOrNull(v: string): number | null {
    return v === "" ? null : Number(v);
  }

  function toggleWeekday(day: number) {
    const set_ = new Set(form.closed_weekdays);
    set_.has(day) ? set_.delete(day) : set_.add(day);
    set("closed_weekdays", [...set_].sort((a, b) => a - b));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved =
        poolId === null
          ? await api.createPool(form)
          : await api.updatePool(poolId, form);
      await api.applyImage("pools", saved.id, imageAction);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    <form
      onSubmit={submit}
      className="mb-5 space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {poolId === null ? t("New pool") : t("Edit {{name}}", { name: initial.name_de })}
      </h3>

      <div className="grid grid-cols-2 gap-3">
        <TranslatableField
          label={t("Name")}
          required
          values={{ de: form.name_de, en: form.name_en }}
          onChange={(lang, v) => setForm((f) => ({ ...f, [`name_${lang}`]: v }))}
          inputClass={inputClass}
        />
        <Field label={t("Pool ID (short code)")}>
          <input
            required
            value={form.pool_id}
            onChange={(e) => set("pool_id", e.target.value)}
            className={inputClass}
          />
        </Field>
        <TranslatableField
          label={t("Room")}
          hint={t("e.g. Room 1.01")}
          values={{ de: form.room_de, en: form.room_en }}
          onChange={(lang, v) => setForm((f) => ({ ...f, [`room_${lang}`]: v }))}
          inputClass={inputClass}
        />
        <Field label={t("Lead time (hours before pickup)")}>
          <input
            type="number"
            min={0}
            value={form.lead_time_hours}
            onChange={(e) => set("lead_time_hours", Number(e.target.value || 0))}
            className={inputClass}
          />
        </Field>
        <Field label={t("Max booking horizon (months ahead)")}>
          <input
            type="number"
            min={1}
            value={form.max_booking_months}
            onChange={(e) => set("max_booking_months", Number(e.target.value || 0))}
            className={inputClass}
          />
        </Field>
        <Field label={t("Phone")}>
          <input
            value={form.phone}
            onChange={(e) => set("phone", e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label={t("Email")}>
          <input
            type="email"
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            className={inputClass}
          />
        </Field>
        <label className="flex items-center gap-2 self-end pb-1.5 text-sm text-slate-700 dark:text-slate-200">
          <input
            type="checkbox"
            checked={form.notify_on_defect}
            onChange={(e) => set("notify_on_defect", e.target.checked)}
          />
          {t("Email this contact when a device is marked defective")}
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={form.notify_on_cancellation}
          onChange={(e) => set("notify_on_cancellation", e.target.checked)}
        />
        {t("Email this contact when a borrower cancels a booking")}
      </label>

      <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={form.require_booking_note}
          onChange={(e) => set("require_booking_note", e.target.checked)}
        />
        <span>
          {t("Require a message from the borrower when ordering from this pool")}
          <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-300">
            {t("The \"Message to the staff\" field becomes mandatory if any pool in an order requires it.")}
          </span>
        </span>
      </label>

      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/50">
        <p className="mb-1 text-xs font-semibold text-slate-600 dark:text-slate-300">{t("Visibility")}</p>
        {accessGroups.length > 0 ? (
          <p className="text-sm text-slate-700 dark:text-slate-200">
            {t("Visible to members of:")}{" "}
            {accessGroups.map((g, i) => (
              <span key={g.id}>
                {i > 0 && ", "}
                <span className="font-medium">{g.name}</span>
              </span>
            ))}
            {" "}
            <span className="text-slate-600 dark:text-slate-300">
              {t("(plus this pool's lenders and admins)")}
            </span>
          </p>
        ) : (
          <p className="text-sm text-slate-700 dark:text-slate-200">
            {t("Visible to everyone signed in — no access group assigned.")}
          </p>
        )}
        <Link
          to="/admin/access-groups"
          className="mt-1 inline-block text-xs font-medium text-brand-700 hover:underline dark:text-brand-300"
        >
          {t("Manage access groups →")}
        </Link>
      </div>

      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Accent colour")}</p>
        <div className="flex flex-wrap gap-2">
          {POOL_ACCENT_KEYS.map((key) => {
            const selected = (form.accent_color || "neutral") === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => set("accent_color", key)}
                aria-pressed={selected}
                title={t(ACCENT_LABELS[key])}
                className={`h-7 w-7 shrink-0 rounded-full ${poolAccent(key).dot} transition-shadow ${
                  selected
                    ? "ring-2 ring-slate-900 ring-offset-2 dark:ring-slate-100 dark:ring-offset-slate-900"
                    : "ring-1 ring-slate-200 dark:ring-slate-700"
                }`}
              >
                <span className="sr-only">{t(ACCENT_LABELS[key])}</span>
              </button>
            );
          })}
        </div>
      </div>

      <Field label={t("Email language for this pool")}>
        <select
          value={form.email_language}
          onChange={(e) => set("email_language", e.target.value)}
          className={inputClass}
        >
          <option value="de">{t("German")}</option>
          <option value="en">{t("English")}</option>
        </select>
      </Field>

      <TranslatableField
        label={t("Address")}
        multiline
        rows={3}
        values={{ de: form.address_de, en: form.address_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`address_${lang}`]: v }))}
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
      <TranslatableField
        label={t("Directions")}
        multiline
        values={{ de: form.directions_de, en: form.directions_en }}
        onChange={(lang, v) =>
          setForm((f) => ({ ...f, [`directions_${lang}`]: v }))
        }
        inputClass={inputClass}
      />
      <TranslatableField
        label={t("Note in borrower emails")}
        multiline
        rows={2}
        hint={t(
          "Optional. Added to this pool's section in borrower emails, e.g. \"This pool is only available to students of subject XY.\"",
        )}
        values={{ de: form.email_note_de, en: form.email_note_en }}
        onChange={(lang, v) => setForm((f) => ({ ...f, [`email_note_${lang}`]: v }))}
        inputClass={inputClass}
      />
      <Field label={t("Image")}>
        <ImageCropField
          currentUrl={form.image}
          aspect={16 / 9}
          fallback={symbolFor(form.name_de ?? "", form.room_de ?? "")}
          onChange={setImageAction}
        />
      </Field>

      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Closed weekdays")}</p>
        <div className="flex flex-wrap gap-3">
          {WEEKDAYS.map((label, day) => (
            <label key={day} className="flex items-center gap-1 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox"
                checked={form.closed_weekdays.includes(day)}
                onChange={() => toggleWeekday(day)}
              />
              {t(label)}
            </label>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs text-slate-600 dark:text-slate-300">{t("Service times")}</p>
        <OpeningHoursEditor
          value={form.opening_hours}
          onChange={(v) => set("opening_hours", v)}
          closedWeekdays={form.closed_weekdays}
        />
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Field label={t("Min days")}>
          <input
            type="number"
            min={0}
            value={form.default_min_days ?? ""}
            onChange={(e) => set("default_min_days", numberOrNull(e.target.value))}
            className={inputClass}
          />
        </Field>
        <Field label={t("Max days")}>
          <input
            type="number"
            min={0}
            value={form.default_max_days ?? ""}
            onChange={(e) => set("default_max_days", numberOrNull(e.target.value))}
            className={inputClass}
          />
        </Field>
        <Field label={t("Min hours")}>
          <input
            type="number"
            min={0}
            value={form.default_min_hours ?? ""}
            onChange={(e) => set("default_min_hours", numberOrNull(e.target.value))}
            className={inputClass}
          />
        </Field>
        <Field label={t("Max hours")}>
          <input
            type="number"
            min={0}
            value={form.default_max_hours ?? ""}
            onChange={(e) => set("default_max_hours", numberOrNull(e.target.value))}
            className={inputClass}
          />
        </Field>
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(e) => set("is_active", e.target.checked)}
        />
        {t("Active (bookable / shown)")}
      </label>

      {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}

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
    {poolId !== null && (
      <section className="mb-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <h3 className="mb-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
          {t("Block days for this pool")}
        </h3>
        <p className="mb-3 text-xs text-slate-600 dark:text-slate-300">
          {t("Days this pool is closed for bookings (e.g. holidays, maintenance).")}
        </p>
        <BlockDaysManager poolId={poolId} />
      </section>
    )}
    </>
  );
}
