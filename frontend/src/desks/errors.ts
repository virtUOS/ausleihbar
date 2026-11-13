// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import { ApiError, getJson } from "../api";

/** Localized message for a failed token-page request (scan / mail action):
 *  never shows the raw (English) server text. */
export function tokenErrorMessage(e: unknown, t: TFunction): string {
  if (!(e instanceof ApiError)) return t("The request failed.");
  const code = (e.data as { code?: string } | undefined)?.code;
  if (e.status === 401) return t("Your session has expired. Please sign in again.");
  if (e.status >= 500) return t("The server has a problem. Please try again later.");
  switch (code) {
    case "wrong_user":
      return t("This link belongs to another account. Please sign in with the account that received the mail.");
    case "already_released":
      return t("The reservation was already released.");
    case "invalid_token":
    case "invalid_action":
      return t("This link is invalid.");
    case "until_required":
      return t("Please choose until when.");
    case "invalid_until":
      return t("Please choose a time within your reservation.");
    case "not_allowed":
      return t("This reservation can no longer be postponed (it is checked in, released or over).");
    case "not_found":
      return t("The reservation no longer exists.");
  }
  // A 403 without a code (DRF answers a lapsed session this way): see resolveTokenError.
  if (e.status === 403) return t("You do not have permission for this.");
  if (e.status === 400) return t("This link is invalid.");
  if (e.status === 404) return t("The reservation no longer exists.");
  if (e.status === 410) return t("This link has expired because the reservation is over.");
  if (e.status === 409) return t("This is no longer possible.");
  return t("The request failed.");
}

export interface TokenError {
  message: string;
  /** The session lapsed: offer a login button. */
  login: boolean;
}

/** Like `tokenErrorMessage`, but tells an expired session (DRF's 403 for
 *  anonymous requests) from a real refusal by asking `/api/whoami/`. */
export async function resolveTokenError(e: unknown, t: TFunction): Promise<TokenError> {
  const code = e instanceof ApiError ? (e.data as { code?: string } | undefined)?.code : undefined;
  if (e instanceof ApiError && (e.status === 401 || (e.status === 403 && !code))) {
    let authenticated = true;
    try {
      authenticated = (await getJson<{ authenticated: boolean }>("/api/whoami/")).authenticated;
    } catch {
      /* keep the generic message */
    }
    if (!authenticated) {
      return { message: t("Your session has expired. Please sign in again."), login: true };
    }
  }
  return { message: tokenErrorMessage(e, t), login: false };
}
