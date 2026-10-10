// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** `value` as an absolute http(s) URL, or null. Use before rendering a
 *  user-entered value as a link: React still renders `javascript:` hrefs. */
export function safeHttpUrl(value: unknown): string | null {
  try {
    const url = new URL(String(value));
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}
