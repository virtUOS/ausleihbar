// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Zero-dependency fallback symbols for catalog entries without an uploaded
// image. The emoji is derived from the product type / category / title text,
// so admins don't have to pick one — it just works from the name (EN or DE).

const EMOJI_RULES: [RegExp, string][] = [
  [/podcast|studio|mikro|mic\b|microphone/i, "🎙️"],
  [/audio|sound|\bton\b|recording|aufnahme/i, "🎧"],
  [/speaker|lautsprecher|\bpa\b|boxen/i, "🔊"],
  [/video|film|camcorder/i, "🎥"],
  [/cam|kamera|photo|foto/i, "📷"],
  [/beamer|projector|projektor/i, "📽️"],
  [/tv|monitor|display|screen|bildschirm/i, "🖥️"],
  [/laptop|notebook|macbook/i, "💻"],
  [/computer|\bpc\b|workstation|rechner/i, "🖥️"],
  [/tablet|ipad/i, "📱"],
  [/phone|handy|smartphone/i, "📱"],
  [/print|drucker|scanner|scan/i, "🖨️"],
  [/light|licht|lamp|leuchte/i, "💡"],
  [/room|raum|zimmer|saal/i, "🚪"],
  [/headphone|kopfhörer/i, "🎧"],
  [/cable|kabel|adapter|\busb\b/i, "🔌"],
  [/drone|drohne/i, "🚁"],
  [/\bvr\b|headset|brille/i, "🥽"],
  [/book|buch|literatur/i, "📚"],
  [/game|spiel|konsole|console/i, "🎮"],
  [/tool|werkzeug/i, "🛠️"],
  [/battery|akku|power|strom/i, "🔋"],
  [/storage|festplatte|\bssd\b|stick|speicher/i, "💾"],
  [/watch|uhr/i, "⌚"],
  [/keyboard|tastatur|piano|klavier|synth/i, "🎹"],
  [/guitar|gitarre|instrument/i, "🎸"],
];

/**
 * Pick a fallback emoji from any descriptive text (product type, category
 * title, product title …). Returns a neutral box when nothing matches.
 */
export function symbolFor(...hints: (string | null | undefined)[]): string {
  const text = hints.filter(Boolean).join(" ");
  for (const [pattern, emoji] of EMOJI_RULES) {
    if (pattern.test(text)) return emoji;
  }
  return "📦";
}
