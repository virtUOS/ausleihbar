#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Every user-facing message of the desksharing backend (error `detail`s,
// validation messages, permission messages) is a stable English string that
// the frontend translates with `i18n.t(message)` (see `extractApiError` in
// src/api.ts) — so each needs an entry in the German catalog. Without
// parameters: an f-string message could never match a catalog key.
//
// Scans backend/desksharing/*.py (not tests, migrations or management
// commands) for string literals in statements that produce such messages:
// `raise …`, `detail=…`, `{"detail": …}`, `message = …` and `errors[…] = …`.
// Adjacent literals are joined (implicit concatenation); dict keys and
// machine codes (snake_case identifiers) are skipped.
// Run: node frontend/scripts/check-desk-details.mjs (DEBUG=1 lists every message)

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.join(here, "../../backend/desksharing");
const de = JSON.parse(readFileSync(path.join(here, "../src/locales/de/translation.json"), "utf8"));

// Internal errors that never reach a user.
const IGNORED = new Set(["Unknown desksharing event {event!r}"]);

/** Split Python source into logical statements of tokens: string literals
 *  ({str, f}) and other text. Comments are dropped. */
function statements(src) {
  const out = [];
  let tokens = [];
  let depth = 0;
  let text = "";
  const flushText = () => {
    if (text) tokens.push({ text });
    text = "";
  };
  for (let i = 0; i < src.length; ) {
    const c = src[i];
    if (c === "#") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }
    const m = /^([rRbBfFuU]{0,2})("""|'''|"|')/.exec(src.slice(i, i + 5));
    // A literal starts here unless we are inside an identifier.
    if (m && !/[A-Za-z0-9_]/.test(src[i - 1] ?? "")) {
      flushText();
      const prefix = m[1].toLowerCase();
      const quote = m[2];
      let j = i + m[0].length;
      let value = "";
      while (j < src.length && !src.startsWith(quote, j)) {
        if (src[j] === "\\" && !prefix.includes("r")) {
          const n = src[j + 1];
          value += n === "n" ? "\n" : n === "\n" ? "" : n;
          j += 2;
          continue;
        }
        value += src[j];
        j++;
      }
      tokens.push({ str: value, f: prefix.includes("f") });
      i = j + quote.length;
      continue;
    }
    if ("([{".includes(c)) depth++;
    if (")]}".includes(c)) depth--;
    if (c === "\n" && depth === 0 && !text.endsWith("\\")) {
      flushText();
      if (tokens.length) out.push(tokens);
      tokens = [];
      i++;
      continue;
    }
    text += c;
    i++;
  }
  flushText();
  if (tokens.length) out.push(tokens);
  return out;
}

const USER_FACING = [/^\s*raise\b/, /\bdetail\s*=/, /["']detail["']\s*:/, /^\s*message\s*=/, /^\s*errors\[/];

function messages(stmt) {
  const joined = stmt.map((t) => (t.str !== undefined ? JSON.stringify(t.str) : t.text)).join("");
  // Decorators (`@action(detail=True, …)`) are not messages.
  if (/^\s*@/.test(joined) || !USER_FACING.some((re) => re.test(joined))) return [];
  const found = [];
  for (let k = 0; k < stmt.length; k++) {
    if (stmt[k].str === undefined) continue;
    // Join adjacent literals (only whitespace between them).
    let value = "";
    let f = false;
    let end = k;
    while (end < stmt.length) {
      const tok = stmt[end];
      if (tok.str !== undefined) {
        value += tok.str;
        f ||= tok.f;
        end++;
      } else if (/^\s*$/.test(tok.text)) end++;
      else break;
    }
    const next = stmt[end]?.text ?? "";
    k = end - 1;
    if (/^\s*:/.test(next)) continue; // a dict key
    if (/^[a-z][a-z0-9_]*$/.test(value)) continue; // a machine code
    if (!/[A-Za-z]/.test(value)) continue;
    found.push({ value, f });
  }
  return found;
}

const errors = [];
let count = 0;
for (const name of readdirSync(backendDir).sort()) {
  if (!name.endsWith(".py")) continue;
  const src = readFileSync(path.join(backendDir, name), "utf8");
  for (const stmt of statements(src)) {
    for (const { value, f } of messages(stmt)) {
      if (IGNORED.has(value)) continue;
      if (process.env.DEBUG) console.log(name, JSON.stringify(value));
      count++;
      if (f) errors.push(`${name}: f-string message cannot be translated: ${JSON.stringify(value)}`);
      else if (!(value in de)) errors.push(`${name}: missing German translation: ${JSON.stringify(value)}`);
    }
  }
}

if (errors.length) {
  console.error(`check-desk-details: ${errors.length} problem(s):`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}
console.log(`check-desk-details: OK (${count} backend messages translated).`);
