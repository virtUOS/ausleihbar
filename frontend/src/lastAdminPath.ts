// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** The admin page last opened in this browser, so the "Admin" area link
 *  returns there. Per-browser convenience only (localStorage, best-effort). */
const KEY = "ausleihbar.admin.lastPath";
export const DEFAULT_ADMIN_PATH = "/admin/pools";

function isAdminPath(path: string): boolean {
  return path === "/admin" || path.startsWith("/admin/");
}

export function getLastAdminPath(): string {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored && isAdminPath(stored.split("?")[0])) return stored;
  } catch {
    // storage unavailable (private mode, blocked) — fall back to the default
  }
  return DEFAULT_ADMIN_PATH;
}

export function rememberAdminPath(pathname: string, search = ""): void {
  if (!isAdminPath(pathname)) return;
  try {
    localStorage.setItem(KEY, pathname + search);
  } catch {
    // ignore: remembering the page is optional
  }
}
