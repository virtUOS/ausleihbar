// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Helpers to interpret scanned/typed QR payloads. */

/**
 * Extract a device `qr_code_id` from a scanned sticker. Device stickers encode
 * a URL `<shop>/r/<qr_id>`; a typed/raw id is accepted as-is.
 */
export function parseResourceQr(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/\/r\/([^/?#\s]+)/);
  return match ? decodeURIComponent(match[1]) : trimmed;
}

/**
 * The token of a desksharing place sticker (`<shop>/desks/q/<token>`), or null
 * for anything else. Those stickers are meant for the phone's camera app; the
 * lending desk's scanner hands them over to the desk check-in page.
 */
export function parseDeskQrToken(text: string): string | null {
  const match = text.trim().match(/\/desks\/q\/([^/?#\s]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
