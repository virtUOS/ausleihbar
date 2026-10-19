// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { formatDate } from "../dates";
import type { StrikePreview } from "../types";

export type StrikeTarget = { booking: number } | { user: number };

const PREVIEW_DEBOUNCE_MS = 400;

/** Modal to issue a strike: reason (required), optional personal note (only in
 *  the email) and a live preview of the email plus the consequence. */
export function StrikeDialog({
  target,
  borrowerName,
  open,
  onClose,
  onIssued,
}: {
  target: StrikeTarget;
  borrowerName: string;
  open: boolean;
  onClose: () => void;
  onIssued: () => void;
}) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<StrikePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);
  const busyRef = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  busyRef.current = busy;
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLFormElement>(null);
  const targetKey = JSON.stringify(target);

  // Reset when (re)opened.
  useEffect(() => {
    if (!open) return;
    setReason("");
    setNote("");
    setPreview(null);
    setError(null);
    setPreviewFailed(false);
    // A pending submit keeps its busy state; it settles on its own.
  }, [open, targetKey]);

  // Debounced preview; a cleanup flag drops responses that arrive after a
  // newer request was started (or the dialog closed).
  useEffect(() => {
    if (!open) return;
    let stale = false;
    const handle = setTimeout(() => {
      api
        .previewStrike({
          ...(JSON.parse(targetKey) as StrikeTarget),
          reason: reason.trim(),
          note: note.trim() || undefined,
        })
        .then((p) => {
          if (stale) return;
          setPreview(p);
          setPreviewFailed(false);
        })
        .catch(() => {
          if (stale) return;
          setPreview(null);
          setPreviewFailed(true);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      stale = true;
      clearTimeout(handle);
    };
  }, [open, targetKey, reason, note]);

  // Focus, trap Tab, Escape, scroll lock, restore focus (like ConfirmDialog).
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    reasonRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (!busyRef.current) onCloseRef.current();
        return;
      }
      if (e.key === "Tab") {
        const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), textarea",
        );
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.createStrike({
        ...target,
        reason: reason.trim(),
        note: note.trim() || undefined,
      });
      setBusy(false);
      onIssued();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Action failed."));
      setBusy(false);
    }
  }

  let consequence: string | null = null;
  if (preview) {
    consequence = preview.blocked_permanently
      ? t(
          "This will be active strike no. {{count}} — the account will be blocked indefinitely.",
          { count: preview.active_after },
        )
      : preview.blocked_until
        ? t(
            "This will be active strike no. {{count}} — the account will be blocked until {{date}}.",
            { count: preview.active_after, date: formatDate(preview.blocked_until) },
          )
        : t("This will be active strike no. {{count}} — no block yet.", {
            count: preview.active_after,
          });
  }

  const fieldClass =
    "mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="strike-dialog-title"
      onClick={() => {
        if (!busy) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4"
    >
      <form
        ref={dialogRef}
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="max-h-full w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900"
      >
        <h2
          id="strike-dialog-title"
          className="text-lg font-semibold text-slate-900 dark:text-slate-100"
        >
          {t("Give a strike")} — {borrowerName}
        </h2>

        <label className="mt-4 block text-sm font-medium text-slate-700 dark:text-slate-200">
          {t("Reason")}
          <textarea
            ref={reasonRef}
            value={reason}
            required
            rows={2}
            onChange={(e) => setReason(e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className="mt-3 block text-sm font-medium text-slate-700 dark:text-slate-200">
          {t("Personal message to the person (optional)")}
          <textarea
            value={note}
            rows={2}
            aria-describedby="strike-note-hint"
            onChange={(e) => setNote(e.target.value)}
            className={fieldClass}
          />
        </label>
        <p
          id="strike-note-hint"
          className="mt-0.5 text-xs text-slate-500 dark:text-slate-400"
        >
          {t("Only in the email.")}
        </p>

        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/60">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {t("Email preview")}
          </p>
          {preview ? (
            <>
              {!preview.will_send && (
                <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
                  {t("This person has no email address — no email will be sent.")}
                </p>
              )}
              <p className="mt-1 text-sm font-bold text-slate-900 dark:text-slate-100">
                {preview.subject}
              </p>
              <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-sm text-slate-700 dark:text-slate-200">
                {preview.body}
              </pre>
            </>
          ) : (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {previewFailed ? t("Preview unavailable.") : "…"}
            </p>
          )}
        </div>
        {consequence && (
          <p className="mt-3 text-sm font-medium text-slate-800 dark:text-slate-100">
            {consequence}
          </p>
        )}

        {error && (
          <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-300">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {t("Cancel")}
          </button>
          <button
            type="submit"
            disabled={busy || !reason.trim()}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-40"
          >
            {t("Give a strike")}
          </button>
        </div>
      </form>
    </div>
  );
}
