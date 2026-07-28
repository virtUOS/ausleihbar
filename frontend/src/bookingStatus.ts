// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import i18n from "./i18n";

/**
 * Borrower-facing vocabulary for the booking lifecycle (issue #12).
 *
 * The backend statuses (`pending`, `confirmed`, `handed_out`, `returned`,
 * `cancelled`) are technical; borrowers saw the raw words and couldn't tell
 * what e.g. "pending" meant. These helpers give every status one clear label
 * and a one-line explanation, used consistently wherever a borrower sees a
 * booking's state. Resolved at call time so they follow the active language.
 */

/** Short, human label for the status badge. */
export function bookingStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return i18n.t("Awaiting confirmation");
    case "confirmed":
      return i18n.t("Confirmed");
    case "handed_out":
      return i18n.t("Picked up");
    case "returned":
      return i18n.t("Returned");
    case "cancelled":
      return i18n.t("Cancelled");
    default:
      return status.replace("_", " ");
  }
}

/** One-line explanation of what the status means for the borrower. */
export function bookingStatusHint(status: string): string {
  switch (status) {
    case "pending":
      return i18n.t(
        "The staff still has to confirm this — you can't pick it up yet.",
      );
    case "confirmed":
      return i18n.t(
        "Confirmed by the staff. Pick it up during your time slot.",
      );
    case "handed_out":
      return i18n.t(
        "You have these items right now — return them by the end of the period.",
      );
    case "returned":
      return i18n.t("Returned — all done.");
    case "cancelled":
      return i18n.t("This booking was cancelled.");
    default:
      return "";
  }
}
