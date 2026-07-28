// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Helpers to interpret scanned/typed QR payloads for the handout flow. */

/** Extract a booking code (e.g. R-00042) from a scanned pickup QR or typed text. */
export function parseBookingCode(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/R-\d+/i);
  return match ? match[0].toUpperCase() : trimmed;
}

/**
 * Extract a device `qr_code_id` from a scanned sticker. Device stickers encode
 * a URL `<shop>/r/<qr_id>`; a typed/raw id is accepted as-is.
 */
export function parseResourceQr(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/\/r\/([^/?#\s]+)/);
  return match ? decodeURIComponent(match[1]) : trimmed;
}
