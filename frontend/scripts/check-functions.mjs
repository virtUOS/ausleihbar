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

// The "Alle Funktionen" page takes its order from the registry, so menu
// entries must appear there in menu order (lending desk first, then admin).
const order = paths(read("appFunctions.ts"));
// An entry may appear in both menus (e.g. the items page, #135); its first
// occurrence fixes its place.
const menu = [
  ...new Set([
    ...paths(read("components/ManageTabs.tsx")),
    ...paths(read("components/AdminTabs.tsx")),
  ]),
];
const positions = menu.map((to) => order.indexOf(to));
const outOfOrder = menu.filter((to, i) => i > 0 && positions[i] < positions[i - 1]);
if (outOfOrder.length) {
  console.error(
    "Registry order differs from the menus (move these in appFunctions.ts):\n  " +
      outOfOrder.join("\n  "),
  );
  process.exit(1);
}
console.log("check:functions OK");
