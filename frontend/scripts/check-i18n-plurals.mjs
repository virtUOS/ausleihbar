#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Regression guard for the trash-bin plural-key bug: a count-based key
// ("… {{count}} …") had a German `_other` entry but no English `_one`/`_other`
// pair. Because the app initializes i18next with `keySeparator: false` and
// English is the app's *key* language (not auto-derived), i18next needs
// explicit `_one`/`_other` resources for English too — the bare key alone
// does not pluralize. This script scans both locale catalogs and fails if:
//   - the `en` catalog has a `_other` entry without a matching `_one` entry
//     (or vice versa) — English always needs both explicit forms, and
//   - the `de` catalog has a `_other` entry without a singular counterpart
//     (either a bare key or a `_one` key — both are used in this codebase).
// Run: node frontend/scripts/check-i18n-plurals.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const enPath = path.join(here, "../src/locales/en/translation.json");
const dePath = path.join(here, "../src/locales/de/translation.json");

function load(p) {
  return JSON.parse(readFileSync(p, "utf8"));
}

const en = load(enPath);
const de = load(dePath);

const errors = [];

function baseKey(key, suffix) {
  return key.slice(0, -suffix.length);
}

// English: every `_one` needs a `_other` and vice versa (no bare-key fallback).
const enOneBases = new Set(
  Object.keys(en).filter((k) => k.endsWith("_one")).map((k) => baseKey(k, "_one")),
);
const enOtherBases = new Set(
  Object.keys(en).filter((k) => k.endsWith("_other")).map((k) => baseKey(k, "_other")),
);
for (const base of enOneBases) {
  if (!enOtherBases.has(base)) {
    errors.push(`en: "${base}_one" has no matching "${base}_other"`);
  }
}
for (const base of enOtherBases) {
  if (!enOneBases.has(base)) {
    errors.push(`en: "${base}_other" has no matching "${base}_one"`);
  }
}

// German: every `_other` needs a singular form — either a bare key or `_one`
// (both patterns are used across this catalog).
const deOtherBases = new Set(
  Object.keys(de).filter((k) => k.endsWith("_other")).map((k) => baseKey(k, "_other")),
);
for (const base of deOtherBases) {
  const hasBare = Object.prototype.hasOwnProperty.call(de, base);
  const hasOne = Object.prototype.hasOwnProperty.call(de, `${base}_one`);
  if (!hasBare && !hasOne) {
    errors.push(`de: "${base}_other" has no matching singular ("${base}" or "${base}_one")`);
  }
}

if (errors.length) {
  console.error(`i18n plural-key check failed (${errors.length}):`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

console.log(
  `i18n plural-key check OK (en: ${enOtherBases.size} pluralized key(s), de: ${deOtherBases.size} pluralized key(s)).`,
);
