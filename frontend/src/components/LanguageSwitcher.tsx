// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Globe } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SUPPORTED_LANGUAGES } from "../i18n";

/** Current language + a change handler that also persists the choice for
 *  signed-in users (their notification emails follow the UI language). */
export function useLanguage() {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  const resolved = i18n.resolvedLanguage ?? i18n.language;
  const current = SUPPORTED_LANGUAGES.some((l) => l.code === resolved)
    ? resolved
    : "en";

  function change(lang: string) {
    i18n.changeLanguage(lang);
    if (user?.authenticated) {
      // Best-effort: keep the server-side preference (used for emails) in sync.
      api.setLanguage(lang).catch(() => {});
    }
  }

  return { current, change };
}

/** Language options as menu rows — used inside the account menu and the
 *  guest popover so both look identical. */
export function LanguageOptions({ onPicked }: { onPicked?: () => void }) {
  const { current, change } = useLanguage();
  return (
    <>
      {SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          role="menuitemradio"
          aria-checked={lang.code === current}
          onClick={() => {
            change(lang.code);
            onPicked?.();
          }}
          className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          {lang.label}
          {lang.code === current && (
            <Check aria-hidden className="h-4 w-4 text-brand-600" />
          )}
        </button>
      ))}
    </>
  );
}

/** Standalone language picker for signed-out visitors: a globe button with a
 *  small popover listing the full language names. */
export function LanguageMenu() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("Language")}
        className="flex h-9 w-9 items-center justify-center rounded-full sm:h-10 sm:w-10 text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        <Globe aria-hidden className="h-5 w-5" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-2 w-44 animate-fade-up overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg shadow-slate-900/5 dark:border-slate-700 dark:bg-slate-800"
        >
          <LanguageOptions onPicked={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}
