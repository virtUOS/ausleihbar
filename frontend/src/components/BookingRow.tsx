// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfirm } from "./ConfirmDialog";
import { Mail, MessageSquarePlus, TriangleAlert, Wrench } from "lucide-react";
import { api } from "../api";
import { DeleteButton } from "./RowActions";
import type { BookingItem, ManagedBooking } from "../types";
import { formatPeriod, todayIso } from "../manage";

/** Per-device defect toggle (available ⇄ defective). Marking defective asks
 *  for a short note describing the fault. Other statuses are shown read-only —
 *  blocked/retired are managed elsewhere. */
function DefectToggle({ item, onChanged }: { item: BookingItem; onChanged: () => void }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const defective = item.resource_status === "defective";

  if (item.resource_status !== "available" && item.resource_status !== "defective") {
    return <span className="shrink-0 text-xs text-slate-400 dark:text-slate-300">{item.resource_status}</span>;
  }

  async function markDefective() {
    setBusy(true);
    try {
      const res = await api.markResourceDefective(item.resource, note.trim());
      setEditing(false);
      setNote("");
      if (res.unfulfilled) {
        window.alert(
          t(
            "{{rebooked}} booking(s) moved; {{unfulfilled}} could not be moved — those borrowers were notified.",
            { rebooked: res.rebooked, unfulfilled: res.unfulfilled },
          ),
        );
      }
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function markRepaired() {
    setBusy(true);
    try {
      await api.markResourceAvailable(item.resource);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  if (defective) {
    return (
      <span className="flex shrink-0 items-center gap-1.5">
        <span
          className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300"
          title={item.defect_note || undefined}
        >
          ⚠ {t("defective")}{item.defect_note ? `: ${item.defect_note}` : ""}
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={markRepaired}
          className="text-xs text-slate-500 underline-offset-2 hover:underline disabled:opacity-40 dark:text-slate-300"
        >
          {t("mark repaired")}
        </button>
      </span>
    );
  }

  if (editing) {
    return (
      <div className="mt-1 w-full rounded-md border border-red-200 bg-red-50 p-2.5 dark:border-red-900/50 dark:bg-red-950/40">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-red-800 dark:text-red-300">
          <Wrench aria-hidden className="h-4 w-4" />
          {t("Mark defective")}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") markDefective();
              if (e.key === "Escape") setEditing(false);
            }}
            placeholder={t("What's wrong?")}
            className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-slate-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-slate-500"
          />
          <button
            type="button"
            disabled={busy}
            onClick={markDefective}
            className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors duration-150 hover:bg-red-700 disabled:opacity-40"
          >
            {t("Save")}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setEditing(false)}
            className="text-sm text-slate-500 hover:underline dark:text-slate-300"
          >
            {t("cancel")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-red-200 px-3 py-1.5 text-sm font-medium text-red-700 transition-colors duration-150 hover:bg-red-50 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/40"
    >
      <Wrench aria-hidden className="h-4 w-4" />
      {t("Mark defective")}
    </button>
  );
}

type ReturnChoice = { defect: boolean; note: string };

/** Return-check dialog. Opens when at least one item being returned has return
 *  information on its product. Per device the lender confirms it's fine or flags
 *  a defect (with a note); the whole return can also be cancelled. */
export function ReturnDialog({
  items,
  busy,
  onCancel,
  onConfirm,
}: {
  items: BookingItem[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: (defects: { resource: number; note: string }[]) => void;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<Record<number, ReturnChoice>>(() =>
    Object.fromEntries(items.map((i) => [i.id, { defect: false, note: "" }])),
  );

  function setChoice(id: number, patch: Partial<ReturnChoice>) {
    setState((s) => ({ ...s, [id]: { ...s[id], ...patch } }));
  }

  function confirm() {
    const defects = items
      .filter((i) => state[i.id]?.defect)
      .map((i) => ({ resource: i.resource, note: state[i.id].note.trim() }));
    onConfirm(defects);
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4 print:hidden">
      <div className="max-h-[85vh] w-full max-w-md overflow-auto rounded-xl bg-white p-4 shadow-xl dark:bg-slate-800">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t("Check the return")}</h3>
        <div className="mt-3 space-y-3">
          {items.map((item) => {
            const choice = state[item.id];
            return (
              <div key={item.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  {item.product_title}{" "}
                  <span className="font-normal text-slate-400 dark:text-slate-300">· {item.inventory_number}</span>
                </p>
                {item.return_info?.trim() && (
                  <p className="mt-2 whitespace-pre-line rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
                    {item.return_info}
                  </p>
                )}
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => setChoice(item.id, { defect: false })}
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      !choice.defect
                        ? "bg-green-600 text-white"
                        : "border border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                    }`}
                  >
                    {t("All good")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setChoice(item.id, { defect: true })}
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      choice.defect
                        ? "bg-red-600 text-white"
                        : "border border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                    }`}
                  >
                    {t("Report defect")}
                  </button>
                </div>
                {choice.defect && (
                  <input
                    autoFocus
                    value={choice.note}
                    onChange={(e) => setChoice(item.id, { note: e.target.value })}
                    placeholder={t("What's wrong?")}
                    className="mt-2 w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  />
                )}
              </div>
            );
          })}
        </div>
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="rounded-full border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {t("Cancel return")}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={confirm}
            className="rounded-full bg-brand-400 px-4 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
          >
            {t("Complete return")}
          </button>
        </div>
      </div>
    </div>
  );
}

type Mode = "to_confirm" | "pickups" | "returns" | "overdue" | "browse";

const localDate = (iso: string | null): string | null =>
  iso ? new Date(iso).toLocaleDateString("en-CA") : null;

/** Last booked day = the inclusive end (exclusive upper minus a tick). */
function lastDay(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  d.setMilliseconds(d.getMilliseconds() - 1);
  return d.toLocaleDateString("en-CA");
}

interface PeriodGroup {
  key: string;
  start: string | null;
  end: string | null;
  items: BookingItem[];
}

function groupByPeriod(items: BookingItem[]): PeriodGroup[] {
  const map = new Map<string, PeriodGroup>();
  for (const item of items) {
    const key = `${item.start}|${item.end}`;
    if (!map.has(key)) map.set(key, { key, start: item.start, end: item.end, items: [] });
    map.get(key)!.items.push(item);
  }
  return [...map.values()];
}

/** A booking in the lending desk. Items are grouped by appointment (period);
 *  the appointment matching the selected day gets the Hand out / Return action,
 *  the others are greyed out. */
export function BookingRow({
  booking,
  mode,
  date,
  onActed,
}: {
  booking: ManagedBooking;
  mode: Mode;
  date?: string;
  onActed: () => void;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const [returnItems, setReturnItems] = useState<BookingItem[] | null>(null);
  // Optional one-off note added to this confirmation email (issue #29): hidden
  // until the lender explicitly chooses to add one.
  const [addMessage, setAddMessage] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState("");
  const overdue = mode === "overdue";

  async function act(run: () => Promise<unknown>) {
    setBusy(true);
    try {
      await run();
      onActed();
    } finally {
      setBusy(false);
    }
  }

  // Returning: if any device has return information, open the check dialog
  // (confirm / report defect / cancel); otherwise return straight away.
  function startReturn(out: BookingItem[]) {
    if (out.some((i) => i.return_info?.trim())) {
      setReturnItems(out);
    } else {
      act(() => api.returnBooking(booking.id, out.map((i) => i.id)));
    }
  }

  async function completeReturn(defects: { resource: number; note: string }[]) {
    const out = returnItems!;
    setBusy(true);
    try {
      await api.returnBooking(booking.id, out.map((i) => i.id));
      let unfulfilled = 0;
      for (const d of defects) {
        const res = await api.markResourceDefective(d.resource, d.note);
        unfulfilled += res.unfulfilled;
      }
      if (unfulfilled) {
        window.alert(
          t("{{count}} later booking(s) could not be moved — those borrowers were notified.", {
            count: unfulfilled,
          }),
        );
      }
      setReturnItems(null);
      onActed();
    } finally {
      setBusy(false);
    }
  }

  const hasItemsOut = booking.items.some(
    (i) => i.handed_out_at && !i.returned_at,
  );
  const canCancel =
    !hasItemsOut &&
    booking.status !== "cancelled" &&
    booking.status !== "returned";

  async function cancel() {
    if (
      await confirm({
        message: t("Cancel booking {{code}}?", { code: booking.code }),
        danger: true,
      })
    ) {
      act(() => api.cancelManagedBooking(booking.id));
    }
  }

  function strike() {
    const reason = window.prompt(
      t("Give {{borrower}} a strike — reason (required):", {
        borrower: booking.borrower_name || booking.borrower,
      }),
    );
    if (reason && reason.trim()) {
      act(async () => {
        await api.createStrike({ booking: booking.id, reason: reason.trim() });
        window.alert(t("Strike issued."));
      });
    }
  }

  const header = (
    <div className="flex items-start justify-between gap-2">
      <p className="flex flex-wrap items-center gap-2 font-medium text-slate-900 dark:text-slate-100">
        <Link
          to={`/manage/users/${booking.borrower_id}`}
          className="text-slate-900 hover:underline dark:text-slate-100"
          title={t("Open borrower profile")}
        >
          {booking.borrower_name || booking.borrower}
        </Link>
        <span className="text-xs font-normal text-slate-400 dark:text-slate-300">{booking.code}</span>
        {overdue ? (
          <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-medium text-white">
            {t("overdue")}
          </span>
        ) : (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal text-slate-500 dark:bg-slate-800 dark:text-slate-300">
            {booking.status}
          </span>
        )}
      </p>
      <div className="flex shrink-0 items-center gap-2">
        {mode === "overdue" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => act(() => api.remindBooking(booking.id))}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <Mail aria-hidden className="h-4 w-4" />
            {t("Remind")}
          </button>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={strike}
          title={t("Give this borrower a strike")}
          className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-800 transition-colors duration-150 hover:bg-amber-100 disabled:opacity-40 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300 dark:hover:bg-amber-950/60"
        >
          <TriangleAlert aria-hidden className="h-4 w-4" />
          {t("Strike")}
        </button>
        {canCancel && (
          <DeleteButton
            onClick={cancel}
            disabled={busy}
            label={t("Cancel booking")}
            className="shrink-0"
          />
        )}
      </div>
    </div>
  );

  const reminderInfo = booking.reminders?.length ? (
    <p
      className="mt-1 text-xs text-amber-700 dark:text-amber-300"
      title={booking.reminders
        .map((r) => new Date(r.sent_at).toLocaleString())
        .join("\n")}
    >
      🔔 {t("Reminded {{count}}× · last {{date}}", {
        count: booking.reminders.length,
        date: new Date(booking.reminders[0].sent_at).toLocaleString(),
      })}
    </p>
  ) : null;

  if (mode === "to_confirm" || (mode === "browse" && booking.status === "pending")) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900">
        {header}
        {reminderInfo}
        <div className="mt-1 space-y-1">
          {booking.items.map((item) => (
            <p key={item.id} className="text-slate-600 dark:text-slate-300">
              {item.product_title} · {item.inventory_number} ·{" "}
              {formatPeriod(item.start, item.end, item.lending_type)}
            </p>
          ))}
        </div>
        {booking.note && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{t("Message: {{note}}", { note: booking.note })}</p>
        )}
        {addMessage ? (
          <label className="mt-2 block text-xs text-slate-600 dark:text-slate-300">
            {t("Message to the borrower (optional)")}
            <textarea
              autoFocus
              rows={2}
              value={confirmMessage}
              onChange={(e) => setConfirmMessage(e.target.value)}
              placeholder={t("e.g. suggest a pickup time — added to the confirmation email")}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
            />
          </label>
        ) : (
          <button
            type="button"
            onClick={() => setAddMessage(true)}
            className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <MessageSquarePlus aria-hidden className="h-4 w-4" />
            {t("Add a message")}
          </button>
        )}
        <div className="mt-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => act(() => api.confirmBooking(booking.id, confirmMessage.trim()))}
            className="rounded-full bg-brand-400 px-3 py-1.5 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
          >
            {t("Confirm")}
          </button>
        </div>
      </div>
    );
  }

  const today = todayIso();
  const groups = groupByPeriod(booking.items);

  return (
    <div
      className={`rounded-lg border p-3 text-sm ${
        overdue ? "border-red-300 bg-red-50 dark:border-red-900/50 dark:bg-red-950/40" : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
      }`}
    >
      {header}
      {reminderInfo}
      {booking.note && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Message: {booking.note}</p>
      )}
      <div className="mt-2 space-y-2">
        {groups.map((group) => {
          const startDay = localDate(group.start);
          const endDay = lastDay(group.end);
          const awaiting = group.items.filter((i) => !i.handed_out_at && !i.returned_at);
          const out = group.items.filter((i) => i.handed_out_at && !i.returned_at);

          let action: {
            label: string;
            run: () => Promise<unknown>;
            returnOut?: BookingItem[];
          } | null = null;
          if (mode === "pickups" && startDay === date && awaiting.length) {
            const ids = awaiting.map((i) => i.id);
            action = { label: t("Hand out"), run: () => api.handoutBooking(booking.id, ids) };
          } else if (mode === "returns" && endDay === date && out.length) {
            const ids = out.map((i) => i.id);
            action = {
              label: t("Return"),
              run: () => api.returnBooking(booking.id, ids),
              returnOut: out,
            };
          } else if (mode === "overdue" && awaiting.length && startDay && startDay < today) {
            const ids = awaiting.map((i) => i.id);
            action = { label: t("Hand out"), run: () => api.handoutBooking(booking.id, ids) };
          } else if (mode === "overdue" && out.length && endDay && endDay < today) {
            const ids = out.map((i) => i.id);
            action = {
              label: t("Return"),
              run: () => api.returnBooking(booking.id, ids),
              returnOut: out,
            };
          } else if (
            mode === "browse" &&
            awaiting.length &&
            (booking.status === "confirmed" || booking.status === "handed_out")
          ) {
            const ids = awaiting.map((i) => i.id);
            action = { label: t("Hand out"), run: () => api.handoutBooking(booking.id, ids) };
          } else if (mode === "browse" && out.length) {
            const ids = out.map((i) => i.id);
            action = {
              label: t("Return"),
              run: () => api.returnBooking(booking.id, ids),
              returnOut: out,
            };
          }
          const active = action !== null;

          return (
            <div
              key={group.key}
              className={`rounded-md border p-2 ${
                active ? "border-slate-300 dark:border-slate-600" : "border-slate-100 opacity-50 dark:border-slate-800"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-slate-600 dark:text-slate-300">
                  {formatPeriod(group.start, group.end, group.items[0]?.lending_type)}
                </span>
                {action && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      action.returnOut
                        ? startReturn(action.returnOut)
                        : act(action.run)
                    }
                    className="shrink-0 rounded-full bg-brand-400 px-3 py-1 text-xs font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
                  >
                    {action.label}
                  </button>
                )}
              </div>
              <div className="mt-1 space-y-1">
                {group.items.map((item) => (
                  <div key={item.id} className="flex flex-wrap items-center gap-2 text-slate-700 dark:text-slate-200">
                    <span className="truncate">
                      {item.product_title} · {item.inventory_number}
                      {item.returned_at
                        ? ` · ${t("returned")}`
                        : item.handed_out_at
                          ? ` · ${t("out")}`
                          : ""}
                    </span>
                    {active && <DefectToggle item={item} onChanged={onActed} />}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {returnItems && (
        <ReturnDialog
          items={returnItems}
          busy={busy}
          onCancel={() => setReturnItems(null)}
          onConfirm={completeReturn}
        />
      )}
    </div>
  );
}
