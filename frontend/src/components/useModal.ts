// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not(:disabled), input:not(:disabled):not([type="hidden"]), ' +
  'select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

// Open modals, innermost last: only the topmost one reacts to Escape/Tab, so a
// confirm dialog opened from another dialog doesn't close both at once.
const openModals: symbol[] = [];

/**
 * Shared keyboard/focus behaviour of a modal dialog while `open`: focuses
 * `initialFocusRef` (else the first focusable element in `panelRef`), traps
 * Tab inside the panel, calls `onClose` on Escape, locks page scroll and
 * restores focus to the previously focused element on close. The caller
 * renders the markup (`role="dialog"`, `aria-modal`, `aria-labelledby`).
 */
export function useModal(
  open: boolean,
  panelRef: RefObject<HTMLElement>,
  onClose: () => void,
  initialFocusRef?: RefObject<HTMLElement>,
) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const token = Symbol("modal");
    openModals.push(token);
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    (initialFocusRef?.current ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel)?.focus();

    function onKey(e: KeyboardEvent) {
      if (openModals[openModals.length - 1] !== token) return;
      if (e.key === "Escape") {
        e.preventDefault();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const focusables = panel.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (!panel.contains(active)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      openModals.splice(openModals.indexOf(token), 1);
      document.body.style.overflow = prevOverflow;
      previouslyFocused?.focus?.();
    };
    // The refs are stable; re-running on their identity would refocus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
}
