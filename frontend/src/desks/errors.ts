// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { TFunction } from "i18next";
import { ApiError } from "../api";

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
  // getJson errors carry no body: the status alone decides for the context GET.
  if (e.status === 403)
    return t("This link belongs to another account. Please sign in with the account that received the mail.");
  if (e.status === 400) return t("This link is invalid.");
  if (e.status === 404) return t("The reservation no longer exists.");
  if (e.status === 410) return t("This link has expired because the reservation is over.");
  if (e.status === 409) return t("This is no longer possible.");
  return t("The request failed.");
}
