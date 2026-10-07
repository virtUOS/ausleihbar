// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
/** Whether `html` has neither text nor an image. Parsed in an inert
 *  `DOMParser` document — never via `innerHTML` on the live document, where
 *  `<img onerror=…>` in an unsanitized plain-text field would execute. */
function isEmptyMarkup(html: string): boolean {
  const body = new DOMParser().parseFromString(html, "text/html").body;
  return !body.textContent?.trim() && !body.querySelector("img");
}

/**
 * Whether two form snapshots hold the same values (for `dirty`). Rich-text
 * HTML that is empty counts as "": the editor turns a cleared field into
 * `<p></p>`, which must not read as a change against a stored "".
 * Compared via `JSON.stringify`, so both snapshots must be built the same way
 * (same key order; `undefined` keys are dropped).
 */
export function sameFormValue(a: unknown, b: unknown): boolean {
  const normalise = (_key: string, v: unknown) =>
    typeof v === "string" && v.startsWith("<") && isEmptyMarkup(v) ? "" : v;
  return JSON.stringify(a, normalise) === JSON.stringify(b, normalise);
}

/**
 * Save (+ optional Cancel) row for longer forms (#101). Rendered as the last
 * child of the `<form>`, it sticks to the bottom of the viewport while the form
 * is taller than the screen, so the actions stay reachable. Save is a real
 * `type="submit"` button (Enter keeps submitting the form).
 *
 * By default the bar assumes a `p-4` card and bleeds to its edges; pass
 * `flush` for a form without a card. `surface` must match the card's
 * background: `"canvas"` for cards without their own fill (page white /
 * dark `slate-950`), `"card"` for `dark:bg-slate-900` cards.
 */
export function FormActionBar({
  saving = false,
  disabled = false,
  saveLabel,
  savingLabel,
  onCancel,
  cancelLabel,
  dirty = false,
  surface = "canvas",
  flush = false,
  size = "md",
  children,
}: {
  saving?: boolean;
  disabled?: boolean;
  saveLabel?: string;
  savingLabel?: string;
  /** Shows a Cancel button when given. */
  onCancel?: () => void;
  cancelLabel?: string;
  /** Shows an "Unsaved changes" hint (text, announced politely). */
  dirty?: boolean;
  surface?: "canvas" | "card";
  /** The form has no padded card: don't bleed into its padding. */
  flush?: boolean;
  size?: "md" | "sm";
  /** Extra status next to the buttons, e.g. a "Saved." message. */
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const bg =
    surface === "card" ? "bg-white dark:bg-slate-900" : "bg-white dark:bg-slate-950";
  const edge = flush ? "" : "-mx-4 -mb-4 rounded-b-xl px-4";
  const pad = size === "sm" ? "py-1.5" : "py-2";

  return (
    <div
      className={`form-action-bar sticky bottom-0 z-10 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-slate-200 py-3 dark:border-slate-800 ${bg} ${edge}`}
    >
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving || disabled}
          className={`rounded-full bg-brand-400 px-4 ${pad} text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40`}
        >
          {saving ? (savingLabel ?? t("Saving…")) : (saveLabel ?? t("Save"))}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className={`rounded-full border border-slate-300 px-4 ${pad} text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
          >
            {cancelLabel ?? t("Cancel")}
          </button>
        )}
      </div>
      {children}
      {/* Always mounted so screen readers announce the hint when it appears;
          visually hidden (out of the flex flow) while there is nothing to say,
          so it never leaves an empty row on narrow screens. */}
      <span
        role="status"
        className={dirty ? "text-xs font-medium text-amber-800 dark:text-amber-300 sm:ml-auto" : "sr-only"}
      >
        {dirty && (
          <>
            <span aria-hidden="true" className="mr-1.5 inline-block h-2 w-2 rounded-full bg-amber-500 align-middle" />
            {t("Unsaved changes")}
          </>
        )}
      </span>
    </div>
  );
}
