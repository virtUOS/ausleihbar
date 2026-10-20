// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { defineConfig, devices } from "@playwright/test";

// Website screenshots (`npm run docs:shots`, driven by scripts/docs-shots.sh):
// not a test suite. The project only exists when DOCS_SHOTS is set, so a
// plain `npx playwright test` never picks the file up. It runs against the
// isolated docs stack (frontend :5183, API :8011), never the dev stack.
const DOCS_SHOTS = /docs-screenshots\.spec\.ts$/;

export default defineConfig({
  testDir: "./e2e",
  reporter: "list",
  use: {
    baseURL: "http://localhost:5183",
  },
  projects: process.env.DOCS_SHOTS
    ? [
        {
          name: "docs-shots",
          testMatch: DOCS_SHOTS,
          use: {
            ...devices["Desktop Chrome"],
            locale: "de-DE",
            colorScheme: "light" as const,
            // Native date inputs follow the browser UI language, not `locale`.
            launchOptions: { args: ["--lang=de-DE"] },
          },
        },
      ]
    : [],
});
