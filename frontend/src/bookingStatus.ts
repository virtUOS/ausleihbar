// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import i18n from "./i18n";
import type { Booking } from "./types";

/**
 * Borrower-facing vocabulary for the booking lifecycle (issue #12).
 *
 * The backend statuses (`pending`, `confirmed`, `handed_out`, `returned`,
 * `cancelled`) are technical; borrowers saw the raw words and couldn't tell
 * what e.g. "pending" meant. These helpers give every status one clear label
 * and a one-line explanation, used consistently wherever a borrower sees a
 * booking's state. Resolved at call time so they follow the active language.
 */

/** How a booking is used (#129): a loan (any lent position — mixed bookings
 *  keep the loan wording), on-site use with a desk hand-out, or self-service
 *  on-site use. Dropped positions don't count. */
export type BookingUseKind = "loan" | "onsite_desk" | "onsite_self";

export function bookingUseKind(booking: Pick<Booking, "items">): BookingUseKind {
  const items = booking.items.filter((i) => !i.dropped);
  if (!items.length || items.some((i) => i.use_type !== "onsite")) return "loan";
  return items.some((i) => !i.self_service) ? "onsite_desk" : "onsite_self";
}

/** Short, human label for the status badge. */
export function bookingStatusLabel(status: string, kind: BookingUseKind = "loan"): string {
  if (kind !== "loan") {
    if (status === "handed_out") return i18n.t("In use");
    if (status === "returned") return i18n.t("Used");
  }
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

/** Visual tone of a reservation card (#37): pending = not valid yet (pale),
 *  active = confirmed or out (full pool colour), done = finished (grey). */
export type BookingTone = "pending" | "active" | "done";

export function bookingTone(status: string): BookingTone {
  if (status === "pending") return "pending";
  if (status === "confirmed" || status === "handed_out") return "active";
  return "done";
}

/** One-line explanation of what the status means for the borrower. */
export function bookingStatusHint(status: string, kind: BookingUseKind = "loan"): string {
  if (kind !== "loan") {
    switch (status) {
      case "pending":
        return i18n.t(
          "The staff still has to confirm this — only then can you use the items.",
        );
      case "confirmed":
        return kind === "onsite_self"
          ? i18n.t("Confirmed by the staff. You can use the items on site during the booked time.")
          : i18n.t("Confirmed by the staff. Check in at the lending desk when your time slot starts.");
      case "handed_out":
        return i18n.t(
          "You're using the items right now — return them at the lending desk by the end of the period.",
        );
      case "returned":
        return i18n.t("Used — all done.");
    }
  }
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

/** Whether the borrower may still cancel (mirrors `BookingViewSet.destroy`):
 *  an open reservation with nothing out (#125) and no self-service on-site
 *  item already started or closed as used (#116). */
export function borrowerCanCancel(booking: Booking, now: Date = new Date()): boolean {
  if (booking.status !== "pending" && booking.status !== "confirmed") return false;
  if (booking.items.some((i) => i.handed_out_at && !i.returned_at)) return false;
  return !booking.items.some(
    (i) =>
      i.self_service &&
      (!!i.handed_out_at || (!!i.start && new Date(i.start).getTime() <= now.getTime())),
  );
}
