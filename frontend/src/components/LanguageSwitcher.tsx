// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { SUPPORTED_LANGUAGES } from "../i18n";

/** Returns a handler that persists a language choice for signed-in users
 *  (their notification emails follow the UI language). The picker UI itself
 *  (`LanguageOptions` / `PreferencesMenu`) comes from `@basicbar/ui` and
 *  already switches i18n; this only syncs the server-side preference. */
export function usePersistLanguage() {
  const { user } = useAuth();
  return (lang: string) => {
    if (user?.authenticated) {
      // Best-effort: keep the server-side preference (used for emails) in sync.
      api.setLanguage(lang).catch(() => {});
    }
  };
}

/** On login, persist the currently-shown shop language for a signed-in user who
 *  has none saved yet, so their notification emails match what they see (#25). */
export function useEmailLanguageSync() {
  const { user } = useAuth();
  const { i18n } = useTranslation();
  useEffect(() => {
    if (!user?.authenticated || user.language) return;
    const lang = i18n.resolvedLanguage ?? i18n.language;
    if (SUPPORTED_LANGUAGES.some((l) => l.code === lang)) {
      api.setLanguage(lang).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.authenticated, user?.language]);
}
