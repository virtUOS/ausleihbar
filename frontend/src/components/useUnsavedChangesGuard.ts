// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useContext, useEffect } from "react";
import { UNSAFE_NavigationContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useConfirm } from "./ConfirmDialog";

type NavFn = (...args: unknown[]) => void;

/** One `popstate` listener for the whole app, registered when this module is
 *  evaluated — before `BrowserRouter` subscribes. Some engines run listeners
 *  on the window in registration order even across capture/bubble, so a
 *  listener added later (by the hook) could only react after the router had
 *  already navigated. Kept on `window` so a hot reload reuses the first one.
 *  Requires a static import (the module must load before the router mounts);
 *  a lazily loaded page using this hook would lose the back/forward guard. */
const popGuard: { fn: ((e: PopStateEvent) => void) | null; installed?: boolean } = ((
  window as unknown as { __unsavedPopGuard?: typeof popGuard }
).__unsavedPopGuard ??= { fn: null });
if (!popGuard.installed) {
  popGuard.installed = true;
  window.addEventListener("popstate", (e) => popGuard.fn?.(e), { capture: true });
}

/** Asks before leaving a page with unsaved changes: in-app navigation and
 *  browser back/forward get the themed confirm dialog, closing or reloading
 *  the tab the browser's own `beforeunload` prompt.
 *
 *  How (and its limits): the app uses a `BrowserRouter`, where `useBlocker` is
 *  unavailable (it needs a data router). So while `dirty`
 *  - `push`/`replace` of the router's navigator (`UNSAFE_NavigationContext`,
 *    semi-private React Router API — re-check on upgrades) are wrapped: this
 *    covers links, NavLinks and every `navigate(to)`;
 *  - `popstate` is caught by an app-wide listener registered before the
 *    router's (see `popGuard`), so the router never sees it; the
 *    current URL is pushed again and the user is asked; on "leave" the guard
 *    steps aside for exactly one `history.go(-1)`. That lands where the user
 *    was heading in both directions, because the re-push sits right after the
 *    entry the browser already moved to: after Back the stack is
 *    `[…, target, page]`, after Forward `[…, page, target, page]`. The
 *    re-push drops the history beyond it (after Back the page's old forward
 *    entries, after Forward the entries beyond the forward target).
 *  After a confirmed navigation the guard stays installed, so a page that
 *  does not unmount (same route) is still protected. */
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

    const nav = navigator as unknown as { push: NavFn; replace: NavFn };
    const push = nav.push;
    const replace = nav.replace;
    let asking = false;
    /** Lets the next navigation (one push/replace or one popstate) through. */
    let bypass = false;
    const ask = () =>
      confirm({
        title: t("Unsaved changes"),
        message: t("Leave this page? Your unsaved changes will be lost."),
        confirmLabel: t("Leave page"),
        cancelLabel: t("Stay"),
        danger: true,
      });

    const guard =
      (orig: NavFn): NavFn =>
      (...args) => {
        if (bypass) return orig(...args);
        if (asking) return;
        asking = true;
        void ask().then((ok) => {
          asking = false;
          if (!ok) return;
          bypass = true;
          try {
            orig(...args);
          } finally {
            bypass = false;
          }
        });
      };

    const here = { url: window.location.href, state: window.history.state as unknown };
    const onPopState = (e: PopStateEvent) => {
      if (bypass) {
        bypass = false;
        return;
      }
      // Keep the router from seeing it and restore the page's URL.
      e.stopImmediatePropagation();
      window.history.pushState(here.state, "", here.url);
      if (asking) return;
      asking = true;
      void ask().then((ok) => {
        asking = false;
        if (!ok) return;
        bypass = true;
        window.history.go(-1);
      });
    };

    nav.push = guard(push);
    nav.replace = guard(replace);
    window.addEventListener("beforeunload", onBeforeUnload);
    popGuard.fn = onPopState;
    return () => {
      nav.push = push;
      nav.replace = replace;
      window.removeEventListener("beforeunload", onBeforeUnload);
      if (popGuard.fn === onPopState) popGuard.fn = null;
    };
  }, [dirty, navigator, confirm, t]);
}
