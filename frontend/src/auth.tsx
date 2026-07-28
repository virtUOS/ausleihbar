// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import type { WhoAmI } from "./types";
import { setDefaultContentLang, setTranslationEnabled } from "@basicbar/ui";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";

interface AuthState {
  user: WhoAmI | null;
  loading: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

// Where to send the user once they are signed in. Survives the full-page OIDC
// round-trip via sessionStorage (per-tab, restored when the browser returns to
// this origin); consumed on the first authenticated load, so it never lingers
// (issue #18 — a shared deep link like /products/203 should still land there
// after sign-in instead of dropping the visitor on the landing page).
const REDIRECT_KEY = "postLoginRedirect";

/** Remember an in-app destination to return to after sign-in. The landing page
 *  ("/" and its ?sso markers) is never a destination, so calling this from the
 *  landing leaves an already-stored deep link intact. */
export function rememberRedirect(path: string): void {
  if (path && path !== "/" && !path.startsWith("/?")) {
    sessionStorage.setItem(REDIRECT_KEY, path);
  }
}

function takeRedirect(): string | null {
  const target = sessionStorage.getItem(REDIRECT_KEY);
  if (target) sessionStorage.removeItem(REDIRECT_KEY);
  return target;
}

const currentPath = () => window.location.pathname + window.location.search;

/** Attempt the silent SSO login at most once per tab, and never when we just
 *  came back from a silent attempt or a logout (marked via the ?sso= param). */
function shouldTrySilentLogin(): boolean {
  if (new URLSearchParams(window.location.search).has("sso")) return false;
  return !sessionStorage.getItem("ssoTried");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<WhoAmI | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/whoami/`, { credentials: "include" })
      .then((response) => response.json())
      .then((data: WhoAmI) => {
        setUser(data);
        // Remember the deployment's canonical content language for the editor.
        setDefaultContentLang(data.content_default_language);
        setTranslationEnabled(data.content_translation_enabled);
        // Silent SSO: if not signed in, try a one-shot prompt=none login. If the
        // IdP already has a session the visitor is logged in automatically; if
        // not, the backend bounces back to "/?sso=failed" and we show the
        // landing. Guards (a once-per-tab flag + the ?sso marker, also set on
        // logout) prevent redirect loops and re-login right after logging out.
        if (!data.authenticated && shouldTrySilentLogin()) {
          sessionStorage.setItem("ssoTried", "1");
          // Preserve a deep link so silent SSO returns the user to it, not "/".
          rememberRedirect(currentPath());
          window.location.assign(`${API_BASE_URL}/oidc/silent/`);
          return; // keep `loading` true while the browser navigates away
        }
        // Signed in (incl. just back from the OIDC round-trip): if a deep link
        // was remembered, go there instead of staying on "/" (issue #18).
        if (data.authenticated) {
          const target = takeRedirect();
          if (target && target !== currentPath()) navigate(target, { replace: true });
        }
        setLoading(false);
      })
      .catch(() => {
        setUser({ authenticated: false });
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Login/logout are full-page redirects: the OIDC flow happens server-side.
  // Remember the current page so we return to it after signing in (a no-op on
  // the landing page, which preserves any deep link stored earlier).
  const login = () => {
    rememberRedirect(currentPath());
    window.location.assign(`${API_BASE_URL}/oidc/authenticate/`);
  };
  const logout = () => {
    // Mark silent SSO as already attempted so we don't auto-log-in again the
    // moment the browser lands back on the welcome page after logging out.
    sessionStorage.setItem("ssoTried", "1");
    window.location.assign(`${API_BASE_URL}/oidc/logout-redirect/`);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
