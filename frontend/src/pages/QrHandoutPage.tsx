// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MapPin, Wrench } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { QrScanner } from "../components/QrScanner";
import { ReturnDialog } from "../components/BookingRow";
import { parseResourceQr } from "../qrScan";
import type {
  BookingItem,
  HandoutResource,
  ManagedBooking,
  ScanResource,
} from "../types";

type Prompt =
  | { kind: "swap"; item: BookingItem; resource: HandoutResource }
  | { kind: "adhoc"; resource: HandoutResource };

type Note = { ok: boolean; text: string } | null;
type View = "scan" | "handout" | "return" | "resource";

export function QrHandoutPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [view, setView] = useState<View>("scan");
  const [booking, setBooking] = useState<ManagedBooking | null>(null);
  const [resource, setResource] = useState<ScanResource | null>(null);
  const [note, setNote] = useState<Note>(null);
  const [busy, setBusy] = useState(false);
  // Handout state
  const [done, setDone] = useState<Set<number>>(new Set());
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  // Return state
  const [returnDone, setReturnDone] = useState<Set<number>>(new Set());
  const [returnDialog, setReturnDialog] = useState<BookingItem[] | null>(null);
  // Defect state (resource view)
  const [defectEditing, setDefectEditing] = useState(false);
  const [defectNote, setDefectNote] = useState("");

  if (user && !user.is_lender && !user.is_staff) {
    return <div className="py-10 text-center text-slate-600 dark:text-slate-300">{t("Not authorized.")}</div>;
  }

  function reset() {
    setView("scan");
    setBooking(null);
    setResource(null);
    setDone(new Set());
    setReturnDone(new Set());
    setReturnDialog(null);
    setPrompt(null);
    setDefectEditing(false);
    setDefectNote("");
    setNote(null);
  }

  async function resolveScan(text: string) {
    setNote(null);
    try {
      const result = await api.resolveScan(text);
      setBooking(result.booking);
      setResource(result.resource);
      setDone(new Set());
      setReturnDone(new Set());
      setPrompt(null);
      setDefectEditing(false);
      setView(result.mode === "idle" ? "resource" : result.mode);
      if (result.mode === "handout" && result.booking) {
        setNote({
          ok: true,
          text: t("Loaded {{code}} for {{borrower}}.", {
            code: result.booking.code,
            borrower: result.booking.borrower,
          }),
        });
      }
    } catch {
      setNote({ ok: false, text: t("Unknown code or device.") });
    }
  }

  // ---- Handout ---------------------------------------------------------
  const items = (booking?.items ?? []).filter((i) => !i.returned_at);
  const markDone = (id: number) => setDone((d) => new Set(d).add(id));

  async function scanDevice(text: string) {
    if (!booking) return;
    const qr = parseResourceQr(text);
    setNote(null);
    let res: HandoutResource;
    try {
      res = await api.resolveHandoutResource(qr);
    } catch {
      setNote({ ok: false, text: t("Unknown device “{{qr}}”.", { qr }) });
      return;
    }
    const exact = items.find((i) => i.qr_code_id === res.qr_code_id);
    if (exact) {
      if (exact.handed_out_at) {
        setNote({ ok: true, text: t("{{inventory}} is already handed out.", { inventory: res.inventory_number }) });
      } else {
        markDone(exact.id);
        setNote({ ok: true, text: t("✓ {{inventory}} matched.", { inventory: res.inventory_number }) });
      }
      return;
    }
    const sameProduct = items.find(
      (i) => i.product === res.product && !i.handed_out_at && !done.has(i.id),
    );
    setPrompt(sameProduct ? { kind: "swap", item: sameProduct, resource: res } : { kind: "adhoc", resource: res });
  }

  async function confirmSwap(item: BookingItem, res: HandoutResource) {
    setBusy(true);
    try {
      const updated = await api.swapBookingItem(booking!.id, item.id, res.id);
      setBooking(updated);
      markDone(item.id);
      setNote({ ok: true, text: t("Swapped to {{inventory}}.", { inventory: res.inventory_number }) });
      setPrompt(null);
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : t("Swap failed.") });
    } finally {
      setBusy(false);
    }
  }

  async function confirmAdhoc(res: HandoutResource) {
    setBusy(true);
    try {
      const updated = await api.addBookingItem(booking!.id, res.id);
      setBooking(updated);
      const added = updated.items.find((i) => i.resource === res.id && !i.handed_out_at);
      if (added) markDone(added.id);
      setNote({ ok: true, text: t("Added {{inventory}} to the booking.", { inventory: res.inventory_number }) });
      setPrompt(null);
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : t("Could not add.") });
    } finally {
      setBusy(false);
    }
  }

  const pendingCount = [...done].filter((id) => {
    const it = booking?.items.find((i) => i.id === id);
    return it && !it.handed_out_at;
  }).length;

  async function handOut() {
    if (!booking) return;
    const ids = [...done].filter((id) => {
      const it = booking.items.find((i) => i.id === id);
      return it && !it.handed_out_at;
    });
    if (ids.length === 0) return;
    setBusy(true);
    try {
      const updated = await api.handoutBooking(booking.id, ids);
      setBooking(updated);
      setDone(new Set());
      setNote({ ok: true, text: t("Handed out {{count}} item.", { count: ids.length }) });
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : t("Handout failed.") });
    } finally {
      setBusy(false);
    }
  }

  // ---- Return ----------------------------------------------------------
  const outItems = (booking?.items ?? []).filter((i) => i.handed_out_at && !i.returned_at);

  function toggleReturn(id: number) {
    setReturnDone((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function scanForReturn(text: string) {
    const qr = parseResourceQr(text);
    const match = outItems.find((i) => i.qr_code_id === qr);
    if (!match) {
      setNote({ ok: false, text: t("“{{qr}}” isn't out on this booking.", { qr }) });
      return;
    }
    setReturnDone((prev) => new Set(prev).add(match.id));
    setNote({ ok: true, text: t("✓ {{inventory}} matched.", { inventory: match.inventory_number }) });
  }

  function startReturn() {
    const chosen = outItems.filter((i) => returnDone.has(i.id));
    if (chosen.length === 0) return;
    // Show the check dialog when any device carries return guidance.
    if (chosen.some((i) => i.return_info?.trim())) setReturnDialog(chosen);
    else completeReturn([]);
  }

  async function completeReturn(defects: { resource: number; note: string }[]) {
    const chosen = outItems.filter((i) => returnDone.has(i.id));
    setBusy(true);
    try {
      const updated = await api.returnBooking(booking!.id, chosen.map((i) => i.id));
      let unfulfilled = 0;
      for (const d of defects) {
        const r = await api.markResourceDefective(d.resource, d.note);
        unfulfilled += r.unfulfilled;
      }
      setBooking(updated);
      setReturnDone(new Set());
      setReturnDialog(null);
      setNote({ ok: true, text: t("Returned {{count}} item.", { count: chosen.length }) });
      if (unfulfilled) {
        window.alert(
          t("{{count}} later booking(s) could not be moved — those borrowers were notified.", {
            count: unfulfilled,
          }),
        );
      }
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : t("Return failed.") });
    } finally {
      setBusy(false);
    }
  }

  // ---- Defect (resource view) -----------------------------------------
  async function markDefective() {
    if (!resource) return;
    setBusy(true);
    try {
      const r = await api.markResourceDefective(resource.id, defectNote.trim());
      setResource({ ...resource, status: r.status, defect_note: r.defect_note });
      setDefectEditing(false);
      setDefectNote("");
      setNote({
        ok: true,
        text: r.unfulfilled
          ? t("Marked defective. {{count}} booking(s) could not be moved — those borrowers were notified.", { count: r.unfulfilled })
          : t("Marked defective."),
      });
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : t("Could not update.") });
    } finally {
      setBusy(false);
    }
  }

  async function markRepaired() {
    if (!resource) return;
    setBusy(true);
    try {
      const r = await api.markResourceAvailable(resource.id);
      setResource({ ...resource, status: r.status, defect_note: r.defect_note });
      setNote({ ok: true, text: t("Marked as available.") });
    } catch (err) {
      setNote({ ok: false, text: err instanceof Error ? err.message : t("Could not update.") });
    } finally {
      setBusy(false);
    }
  }

  function statusBadge(item: BookingItem) {
    if (item.handed_out_at)
      return <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-950/50 dark:text-green-300">{t("Handed out")}</span>;
    if (done.has(item.id))
      return <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-950/50 dark:text-blue-300">{t("Ready")}</span>;
    return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{t("Awaiting scan")}</span>;
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{t("QR codes")}</h1>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        {t(
          "Scan a pickup code or a device QR. The desk decides automatically: hand out, take back, or show the storage location.",
        )}
      </p>

      {note && (
        <p className={`mb-3 text-sm ${note.ok ? "text-green-700 dark:text-green-300" : "text-red-600 dark:text-red-300"}`}>
          {note.text}
        </p>
      )}

      {view === "scan" && (
        <section>
          <QrScanner autoStart onScan={resolveScan} manualPlaceholder={t("Pickup code or device QR")} />
        </section>
      )}

      {view !== "scan" && (
        <div className="mb-3">
          <button
            type="button"
            onClick={reset}
            className="text-sm text-slate-600 hover:underline dark:text-slate-300"
          >
            ← {t("Scan another")}
          </button>
        </div>
      )}

      {/* ---- Handout ---- */}
      {view === "handout" && booking && (
        <div className="space-y-5">
          <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{booking.code} · {booking.borrower}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">{t("Status: {{status}}", { status: booking.status })}</p>
            <ul className="mt-3 space-y-1">
              {items.map((item) => (
                <li key={item.id} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
                  <span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">{item.product_title}</span>
                    <span className="text-slate-500 dark:text-slate-400"> · {item.inventory_number}</span>
                  </span>
                  {statusBadge(item)}
                </li>
              ))}
            </ul>
          </section>

          {prompt ? (
            <section className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-900/50 dark:bg-amber-950/40">
              <p className="text-amber-800 dark:text-amber-300">
                {prompt.kind === "swap"
                  ? t("Scanned {{scanned}} ({{product}}) — booked unit is {{booked}}. Swap to the scanned unit?", {
                      scanned: prompt.resource.inventory_number,
                      product: prompt.resource.product_title,
                      booked: prompt.item.inventory_number,
                    })
                  : t("Scanned {{scanned}} ({{product}}) isn't part of this booking. Add it as an ad-hoc item?", {
                      scanned: prompt.resource.inventory_number,
                      product: prompt.resource.product_title,
                    })}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {prompt.kind === "swap" && (
                  <button type="button" disabled={busy} onClick={() => confirmSwap(prompt.item, prompt.resource)} className="rounded-full bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40">
                    {t("Swap unit")}
                  </button>
                )}
                <button type="button" disabled={busy} onClick={() => confirmAdhoc(prompt.resource)} className="rounded-full border border-amber-400 px-3 py-1.5 text-sm text-amber-800 hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-900/40">
                  {prompt.kind === "swap" ? t("Add as extra") : t("Add ad-hoc")}
                </button>
                <button type="button" onClick={() => setPrompt(null)} className="rounded-full border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800">
                  {t("Cancel")}
                </button>
              </div>
            </section>
          ) : (
            <section>
              <p className="mb-2 text-sm font-medium text-slate-900 dark:text-slate-100">{t("Scan devices")}</p>
              <QrScanner onScan={scanDevice} manualPlaceholder={t("Device QR id or URL")} />
            </section>
          )}

          <button type="button" onClick={handOut} disabled={pendingCount === 0 || busy} className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40">
            {busy ? t("Saving…") : t("Hand out {{count}} scanned item", { count: pendingCount })}
          </button>
        </div>
      )}

      {/* ---- Return ---- */}
      {view === "return" && booking && (
        <div className="space-y-5">
          <section className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {t("Take back")} · {booking.code} · {booking.borrower}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t("Check the devices to take back (tap or scan), then complete the return.")}
            </p>
            <ul className="mt-3 space-y-1">
              {outItems.map((item) => (
                <li key={item.id} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
                  <input type="checkbox" checked={returnDone.has(item.id)} onChange={() => toggleReturn(item.id)} className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium text-slate-900 dark:text-slate-100">{item.product_title}</span>
                    <span className="text-slate-500 dark:text-slate-400"> · {item.inventory_number}</span>
                    {item.return_info?.trim() && (
                      <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
                        {t("check on return")}
                      </span>
                    )}
                  </span>
                </li>
              ))}
              {outItems.length === 0 && (
                <li className="px-1 py-2 text-sm text-slate-500 dark:text-slate-400">{t("Nothing is out on this booking.")}</li>
              )}
            </ul>
          </section>

          {outItems.length > 0 && (
            <section>
              <p className="mb-2 text-sm font-medium text-slate-900 dark:text-slate-100">{t("Scan devices")}</p>
              <QrScanner onScan={scanForReturn} manualPlaceholder={t("Device QR id or URL")} />
            </section>
          )}

          <button type="button" onClick={startReturn} disabled={returnDone.size === 0 || busy} className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40">
            {busy ? t("Saving…") : t("Take back {{count}} item", { count: returnDone.size })}
          </button>
        </div>
      )}

      {/* ---- Resource (idle): storage + defect ---- */}
      {view === "resource" && resource && (
        <section className="max-w-lg space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <div>
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{resource.product_title}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">{resource.inventory_number} · {resource.pool_name}</p>
          </div>
          <p className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <MapPin aria-hidden className="h-4 w-4 text-slate-400" />
            {t("Storage location")}:{" "}
            <span className="font-medium">{resource.storage_location || t("not set")}</span>
          </p>

          {resource.status === "defective" ? (
            <div className="rounded-lg bg-red-50 p-3 text-sm dark:bg-red-950/40">
              <p className="font-medium text-red-800 dark:text-red-300">
                ⚠ {t("Marked defective")}{resource.defect_note ? `: ${resource.defect_note}` : ""}
              </p>
              <button type="button" disabled={busy} onClick={markRepaired} className="mt-2 text-sm text-slate-600 underline-offset-2 hover:underline disabled:opacity-40 dark:text-slate-300">
                {t("mark as available")}
              </button>
            </div>
          ) : defectEditing ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-900/50 dark:bg-red-950/40">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-red-800 dark:text-red-300">
                <Wrench aria-hidden className="h-4 w-4" />
                {t("Mark defective")}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input autoFocus value={defectNote} onChange={(e) => setDefectNote(e.target.value)} placeholder={t("What's wrong?")} className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100" />
                <button type="button" disabled={busy} onClick={markDefective} className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{t("Save")}</button>
                <button type="button" disabled={busy} onClick={() => setDefectEditing(false)} className="text-sm text-slate-500 hover:underline dark:text-slate-400">{t("cancel")}</button>
              </div>
            </div>
          ) : (
            <button type="button" onClick={() => setDefectEditing(true)} className="inline-flex items-center gap-1.5 rounded-full border border-red-200 px-3 py-1.5 text-sm font-medium text-red-700 transition-colors duration-150 hover:bg-red-50 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/40">
              <Wrench aria-hidden className="h-4 w-4" />
              {t("Mark defective")}
            </button>
          )}
        </section>
      )}

      {returnDialog && (
        <ReturnDialog
          items={returnDialog}
          busy={busy}
          onCancel={() => setReturnDialog(null)}
          onConfirm={completeReturn}
        />
      )}
    </div>
  );
}
