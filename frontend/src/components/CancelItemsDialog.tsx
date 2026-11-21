// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useModal } from "./useModal";
import { formatPeriod } from "../manage";
import type { BookingItem } from "../types";

/** A lender may cancel an item that is active and was never handed out or
 *  returned; self-service uses only before their period starts (#220). The
 *  backend re-checks. */
export function isCancellableItem(item: BookingItem): boolean {
  if (item.dropped || item.handed_out_at || item.returned_at) return false;
  if (item.self_service && (!item.start || new Date(item.start).getTime() <= Date.now())) return false;
  return true;
}

/** Pick single items of a booking to cancel; the person gets one email (#220). */
export function CancelItemsDialog({
  code,
  items,
  busy,
  onCancel,
  onConfirm,
}: {
  code: string;
  items: BookingItem[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: (itemIds: number[], message: string) => void;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState("");
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  useModal(true, panelRef, () => {
    if (!busy) onCancel();
  });

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4 print:hidden"
    >
      <div
        ref={panelRef}
        className="max-h-[85vh] w-full max-w-md overflow-auto rounded-xl bg-white p-4 shadow-xl dark:bg-slate-800"
      >
        <h3 id={titleId} className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {t("Cancel items of {{code}}", { code })}
        </h3>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {t("The person gets one email about the cancelled items.")}
        </p>
        <div className="mt-3 space-y-2">
          {items.map((item) => (
            <label
              key={item.id}
              className="flex cursor-pointer items-start gap-2 rounded-lg border border-slate-200 p-2.5 text-sm text-slate-700 dark:border-slate-700 dark:text-slate-200"
            >
              <input
                type="checkbox"
                checked={selected.has(item.id)}
                disabled={busy}
                onChange={() => toggle(item.id)}
                className="mt-0.5 h-4 w-4 shrink-0"
              />
              <span className="min-w-0 break-words">
                {item.product_title} · {item.inventory_number} ·{" "}
                {formatPeriod(item.start, item.end, item.lending_type)}
              </span>
            </label>
          ))}
        </div>
        <label className="mt-3 block text-xs text-slate-600 dark:text-slate-300">
          {t("Message to the person (optional)")}
          <textarea
            rows={3}
            maxLength={2000}
            value={message}
            disabled={busy}
            onChange={(e) => setMessage(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          />
        </label>
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="rounded-full border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {t("Cancel")}
          </button>
          <button
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => onConfirm([...selected], message.trim())}
            className="rounded-full bg-red-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors duration-150 hover:bg-red-700 disabled:opacity-40"
          >
            {t("Cancel selected")}
          </button>
        </div>
      </div>
    </div>
  );
}
