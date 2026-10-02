// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { MoreVertical } from "lucide-react";

export type KebabItem = {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  onClick: () => void;
  danger?: boolean;
  /** Shown but not activatable (e.g. while a request is in flight). */
  disabled?: boolean;
};

/** Gap (px) between trigger and menu, and minimum distance to the viewport edge. */
const GAP = 4;
const EDGE = 8;

/** A ⋮ menu button (WAI-ARIA "menu button" pattern). The trigger opens a
 *  `role="menu"` of `menuitem`s with roving focus: the first item (or the last,
 *  when opened with ArrowUp) is focused on open, ArrowUp/ArrowDown/Home/End move
 *  between items, Escape, Tab, click-outside and activating an item close it.
 *  Escape and activation return focus to the trigger.
 *
 *  The menu is portalled to `document.body` and positioned `fixed` from the
 *  trigger's bounding box (right-aligned below it, flipped above when there is
 *  no room, clamped into the viewport; re-placed on resize, closed on scroll).
 *  That way it is never clipped by an `overflow-hidden` ancestor such as a
 *  rounded card or a scrolling table wrapper. React events still bubble through the portal to
 *  the React parents, so trigger and items stop click propagation — the menu
 *  can live inside a clickable table row without triggering the row. */
export function KebabMenu({ items, label }: { items: KebabItem[]; label?: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const [initialFocus, setInitialFocus] = useState<"first" | "last">("first");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const triggerId = useId();
  const menuId = useId();

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    setPos(null);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const place = useCallback(() => {
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger || !menu) return;
    const r = trigger.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    const w = menu.offsetWidth;
    const h = menu.offsetHeight;
    const left = Math.max(EDGE, Math.min(r.right - w, vw - w - EDGE));
    let top = r.bottom + GAP;
    if (top + h > vh - EDGE && r.top - GAP - h >= EDGE) top = r.top - GAP - h;
    setPos({ top, left });
  }, []);

  // Measure and place before paint (the menu renders invisible until placed).
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place, items.length]);

  const placed = open && pos !== null;
  useEffect(() => {
    if (!placed) return;
    const els = itemRefs.current.slice(0, items.length);
    const target = initialFocus === "last" ? els[els.length - 1] : els[0];
    target?.focus({ preventScroll: true });
    // Only on open — not on every re-placement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placed]);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      close(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close(true);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    // Scrolling anything but the menu itself closes it (a fixed menu would
    // otherwise drift away from its trigger, e.g. over the sticky header).
    // Focus only goes back to the trigger if it was inside the menu, so a
    // scroll never steals focus from elsewhere.
    function onScroll(e: Event) {
      const menu = menuRef.current;
      if (menu && e.target instanceof Node && menu.contains(e.target)) return;
      const focusInMenu = !!menu && menu.contains(document.activeElement);
      setOpen(false);
      setPos(null);
      if (focusInMenu) triggerRef.current?.focus({ preventScroll: true });
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, close, place]);

  function openMenu(focus: "first" | "last") {
    setInitialFocus(focus);
    setOpen(true);
  }

  function onMenuKeyDown(e: React.KeyboardEvent) {
    const els = itemRefs.current.slice(0, items.length).filter(Boolean) as HTMLButtonElement[];
    const i = els.indexOf(document.activeElement as HTMLButtonElement);
    let next: number | null = null;
    if (e.key === "ArrowDown") next = (i + 1) % els.length;
    else if (e.key === "ArrowUp") next = (i - 1 + els.length) % els.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = els.length - 1;
    else if (e.key === "Tab") {
      // Leave the menu: move focus back to the trigger (no preventDefault), so
      // the browser's Tab continues from there instead of the end of <body>.
      close(true);
      return;
    }
    if (next !== null) {
      e.preventDefault();
      els[next]?.focus();
    }
  }

  return (
    <div className="relative inline-block text-left">
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label ?? t("Actions")}
        onClick={(e) => {
          e.stopPropagation();
          if (open) close(false);
          else openMenu("first");
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            openMenu(e.key === "ArrowUp" ? "last" : "first");
          }
        }}
        className="rounded-full p-1.5 text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        <MoreVertical aria-hidden className="h-4 w-4" />
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-labelledby={triggerId}
            onKeyDown={onMenuKeyDown}
            style={{ top: pos?.top ?? 0, left: pos?.left ?? 0 }}
            className={`fixed z-40 w-52 max-w-[calc(100vw-16px)] rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900 ${
              pos ? "" : "invisible"
            }`}
          >
            {items.map((item, i) => {
              const ItemIcon = item.icon;
              return (
                <button
                  key={i}
                  ref={(el) => {
                    itemRefs.current[i] = el;
                  }}
                  type="button"
                  role="menuitem"
                  tabIndex={-1}
                  aria-disabled={item.disabled || undefined}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (item.disabled) return;
                    close(true);
                    item.onClick();
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-slate-100 focus:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 aria-disabled:cursor-not-allowed aria-disabled:opacity-40 dark:hover:bg-slate-800 dark:focus:bg-slate-800 ${
                    item.danger
                      ? "text-red-600 dark:text-red-300"
                      : "text-slate-700 dark:text-slate-200"
                  }`}
                >
                  {ItemIcon && (
                    <span aria-hidden className="flex shrink-0">
                      <ItemIcon className="h-4 w-4" />
                    </span>
                  )}
                  <span className="min-w-0 break-words">{item.label}</span>
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </div>
  );
}
