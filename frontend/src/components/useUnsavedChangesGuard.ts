// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useContext, useEffect } from "react";
import { UNSAFE_NavigationContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfirm } from "./ConfirmDialog";

type NavFn = (...args: unknown[]) => void;

/** Asks before leaving a page with unsaved changes: in-app navigation (links,
 *  menus, `navigate()`) gets the themed confirm dialog, closing or reloading
 *  the tab the browser's own `beforeunload` prompt.
 *
 *  The app uses a `BrowserRouter`, where `useBlocker` is unavailable (it needs
 *  a data router), so while `dirty` the router's `push`/`replace` are wrapped.
 *  Browser back/forward is not intercepted. */
export function useUnsavedChangesGuard(dirty: boolean) {
  const { navigator } = useContext(UNSAFE_NavigationContext);
  const confirm = useConfirm();
  const { t } = useTranslation();

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Legacy browsers need a return value to show the prompt.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);

    const nav = navigator as unknown as { push: NavFn; replace: NavFn };
    const push = nav.push;
    const replace = nav.replace;
    let asking = false;
    const restore = () => {
      nav.push = push;
      nav.replace = replace;
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
    const guard =
      (orig: NavFn): NavFn =>
      (...args) => {
        if (asking) return;
        asking = true;
        void confirm({
          title: t("Unsaved changes"),
          message: t("Leave this page? Your unsaved changes will be lost."),
          confirmLabel: t("Leave page"),
          cancelLabel: t("Stay"),
          danger: true,
        }).then((ok) => {
          asking = false;
          if (!ok) return;
          restore();
          orig(...args);
        });
      };
    nav.push = guard(push);
    nav.replace = guard(replace);
    return restore;
  }, [dirty, navigator, confirm, t]);
}
