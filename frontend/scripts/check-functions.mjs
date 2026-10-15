#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Every menu entry (`to:` in AdminTabs/ManageTabs) must be listed in the
// function registry (appFunctions.ts), so the search and the "Alle Funktionen"
// page never lag behind the menus. Run: npm run check:functions

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const src = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src");
const read = (p) => readFileSync(path.join(src, p), "utf8");
const paths = (text) => [...text.matchAll(/\bto:\s*"([^"]+)"/g)].map((m) => m[1]);

const registry = new Set(paths(read("appFunctions.ts")));
const missing = [
  ...paths(read("components/AdminTabs.tsx")),
  ...paths(read("components/ManageTabs.tsx")),
].filter((to) => !registry.has(to));

if (missing.length) {
  console.error("Menu entries missing from appFunctions.ts:\n  " + missing.join("\n  "));
  process.exit(1);
}
console.log("check:functions OK");
