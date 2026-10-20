// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** Screenshots for the project website (`website/bilder/`), not a test.
 *
 *  Run via `scripts/docs-shots.sh` (brings up the isolated docs stack on
 *  :5183/:8011, seeds it with `seed_docs_demo --reset` and calls
 *  `npm run docs:shots`). The `docs-shots` project exists only with
 *  DOCS_SHOTS set, so a plain `npx playwright test` never picks this file up.
 *
 *  Env:
 *  - DOCS_SEED=<file>   seed summary JSON (last line of `seed_docs_demo`; required)
 *  - DOCS_SHOTS_ONLY=a,b  take only these shots (the others are skipped)
 *  - DOCS_SHOTS_DIR=<dir> output directory (default: ../website/bilder)
 *
 *  Signs in without Keycloak: `docs_session <user>` (guarded to the docs
 *  database) prints a session key that becomes the session cookie. Light
 *  theme, `de-DE`; desktop 1440×900 @1.5 (most shots clipped to the centred
 *  content column), phone 390×844 @2. Dialogs are opened but never
 *  submitted; the next run reseeds anyway. */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const OUT = path.resolve(process.env.DOCS_SHOTS_DIR ?? path.join(REPO, "website/bilder"));
const ONLY = (process.env.DOCS_SHOTS_ONLY ?? "").split(",").map((n) => n.trim()).filter(Boolean);
const LOCALE = "de-DE";
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const PHONE_UA =
  "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36";
/** The app's content column is `max-w-3xl` (768 px) centred; desktop shots
 *  keep a margin around it instead of the empty sides of the 1440 viewport. */
const COLUMN_WIDTH = 896;
const COMPOSE = ["compose", "-f", "docker-compose.yml", "-f", "docker-compose.docs.yml", "--profile", "docs"];

interface SeedSummary {
  users: Record<string, number>;
  pools: Record<string, number>;
  categories: Record<string, number>;
  products: Record<string, number>;
  resources: Record<string, { id: number; qr: string }>;
  sets: Record<string, number>;
  bookings: Record<string, string>;
}

function readSeed(): SeedSummary {
  const file = process.env.DOCS_SEED;
  if (!file) throw new Error("DOCS_SEED=<seed summary JSON file> is required (see scripts/docs-shots.sh).");
  return JSON.parse(fs.readFileSync(file, "utf8")) as SeedSummary;
}

test.use({ viewport: DESKTOP, deviceScaleFactor: 1.5, locale: LOCALE, colorScheme: "light" });

// ---------------------------------------------------------------- helpers

function docsManage(...args: string[]): string {
  return execFileSync("docker", [...COMPOSE, "exec", "-T", "docs-backend", "python", "manage.py", ...args], {
    cwd: REPO,
  })
    .toString()
    .trim();
}

let cookieName: string | null = null;

/** A browser context signed in as `username` (docs DB session cookie). */
async function asUser(browser: Browser, username: string, phone = false): Promise<BrowserContext> {
  cookieName ??= docsManage("docs_session", "--cookie-name");
  const context = await browser.newContext(
    phone
      ? {
          viewport: PHONE,
          deviceScaleFactor: 2,
          isMobile: true,
          hasTouch: true,
          userAgent: PHONE_UA,
          locale: LOCALE,
          colorScheme: "light",
        }
      : { viewport: DESKTOP, deviceScaleFactor: 1.5, locale: LOCALE, colorScheme: "light" },
  );
  context.setDefaultTimeout(15_000);
  await context.addCookies([
    { name: cookieName, value: docsManage("docs_session", username), domain: "localhost", path: "/" },
  ]);
  await context.addInitScript(() => {
    try {
      // UI language (i18next detector) — the API follows Accept-Language.
      localStorage.setItem("i18nextLng", "de");
    } catch {
      /* ignore */
    }
  });
  return context;
}

/** Settled page: fonts loaded, no running finite animations, a short pause
 *  for layout transitions. */
async function settle(page: Page, ms = 600) {
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  await page.waitForTimeout(ms);
  await page
    .evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => {
            const timing = a.effect?.getComputedTiming();
            return timing && timing.endTime !== Infinity && a.playState === "running";
          })
          .map((a) => a.finished.catch(() => undefined)),
      ).then(() => undefined),
    )
    .catch(() => undefined);
  await page.waitForTimeout(150);
}

/** Caret, toasts and the Vite dev overlay never belong in a picture. */
const HIDE_TRANSIENT = `
  *, *::before, *::after { caret-color: transparent !important; }
  div[aria-live="polite"].fixed { display: none !important; }
  vite-error-overlay { display: none !important; }
`;

/** Wait until no loading indicator is left in the main area. */
async function loaded(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page
    .waitForFunction(() => !/(Lädt|Laden)…/.test(document.querySelector("main")?.textContent ?? ""), null, {
      timeout: 10_000,
    })
    .catch(() => undefined);
}

interface ShotOptions {
  /** Shoot the region of this element (plus `pad` around it). */
  element?: Locator;
  /** Extend the region downwards to the bottom of this element. */
  until?: Locator;
  /** End the region at the top of this element instead. */
  before?: Locator;
  pad?: number;
  /** Region spans the content column horizontally (element shots). */
  column?: boolean;
  /** Full viewport instead of the content column. */
  full?: boolean;
  /** Content column from the current scroll position, this high (default: viewport). */
  height?: number;
}

/** Public placeholder host shown instead of the docs stack's localhost URLs. */
const PUBLIC_ORIGIN = "https://ausleihbar.example.org";

async function shot(page: Page, name: string, opts: ShotOptions = {}) {
  await loaded(page);
  await page.mouse.move(0, 0);
  await page.addStyleTag({ content: HIDE_TRANSIENT });
  await page.evaluate((origin) => {
    (document.activeElement as HTMLElement | null)?.blur?.();
    // Mail previews and links print the docs stack's URL; show a public one.
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeValue?.includes("localhost:")) {
        node.nodeValue = node.nodeValue.replace(/https?:\/\/localhost:\d+/g, origin);
      }
    }
  }, PUBLIC_ORIGIN);
  await settle(page);
  const viewport = page.viewportSize()!;
  const columnX = (viewport.width - COLUMN_WIDTH) / 2;
  const scrollY = await page.evaluate(() => window.scrollY);
  let clip: { x: number; y: number; width: number; height: number } | undefined;
  let fullPage = false;
  if (opts.element) {
    const pad = opts.pad ?? 16;
    const box = await docBox(opts.element);
    let bottom = opts.before ? (await docBox(opts.before)).y - 8 : box.y + box.height + pad;
    if (opts.until) {
      const u = await docBox(opts.until);
      bottom = Math.max(bottom, u.y + u.height + pad);
    }
    const top = Math.max(0, box.y - pad);
    const x = opts.column && viewport.width > COLUMN_WIDTH ? columnX : Math.max(0, box.x - pad);
    const width = opts.column && viewport.width > COLUMN_WIDTH ? COLUMN_WIDTH : Math.min(viewport.width - x, box.width + 2 * pad);
    if (top >= scrollY && bottom <= scrollY + viewport.height) {
      // Already in view (open menus close on scroll): clip the viewport.
      clip = { x, y: top - scrollY, width, height: bottom - top };
    } else {
      // Taller than the viewport: a full-page capture renders sticky bars at
      // the current scroll position, so scroll to the top first.
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(150);
      clip = { x, y: top, width, height: bottom - top };
      fullPage = true;
    }
  } else if (!opts.full && viewport.width > COLUMN_WIDTH) {
    let height = Math.min(opts.height ?? viewport.height, viewport.height);
    // Never cut through the footer: stop above it when it is only half in view.
    const footer = await page.evaluate(() => {
      const r = document.querySelector("footer")?.getBoundingClientRect();
      return r ? { top: r.top, bottom: r.bottom } : null;
    });
    if (footer && footer.top < height && footer.bottom > height) height = Math.floor(footer.top);
    clip = { x: columnX, y: 0, width: COLUMN_WIDTH, height };
  }
  const png = await page.screenshot({ animations: "disabled", clip, fullPage });
  const file = path.join(OUT, `${name}.png`);
  fs.writeFileSync(file, png);
  console.log(`  ${name}.png  ${Math.round(png.length / 1024)} KB`);
}

/** Bounding box in document coordinates (independent of the scroll position). */
async function docBox(locator: Locator) {
  await locator.first().waitFor();
  return locator.first().evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left + window.scrollX, y: r.top + window.scrollY, width: r.width, height: r.height };
  });
}

/** The booking calendar card on a product or set page. */
const bookingCard = (page: Page) =>
  page.getByText("Verfügbarkeit & Buchung", { exact: true }).locator("xpath=ancestor::section[1]");

/** Open a kebab menu. It closes on scroll, so scroll it into view first
 *  (Playwright's own scroll-into-view during the click would close it). */
async function openMenu(page: Page, trigger: Locator, scroll = true) {
  if (scroll) await scrollTo(page, trigger, 300);
  await page.waitForTimeout(300);
  await trigger.click();
  await page.getByRole("menu").waitFor();
}

/** Scroll so that `locator` sits `offset` px below the top of the viewport. */
async function scrollTo(page: Page, locator: Locator, offset = 24) {
  const box = await docBox(locator);
  await page.evaluate((y) => window.scrollTo(0, y), Math.max(0, box.y - offset));
}

const isoDay = (offset: number) => {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() + offset);
  return d;
};
const isWeekend = (d: Date) => d.getDay() === 0 || d.getDay() === 6;
/** The first weekday at least `offset` days ahead. */
function workday(offset: number): Date {
  let d = isoDay(offset);
  while (isWeekend(d)) d = new Date(d.getTime() + 86_400_000);
  return d;
}
/** German long date as the calendars use it in aria-labels ("27. Oktober 2026"). */
const longDate = (d: Date) =>
  `${d.getDate()}. ${d.toLocaleDateString("de-DE", { month: "long" })} ${d.getFullYear()}`;

/** Click a calendar day (switching months forward if needed). */
async function pickDay(scope: Locator, d: Date) {
  const day = scope.locator(`button[aria-label*="${longDate(d)}"]`);
  for (let i = 0; i < 3 && !(await day.count()); i++) {
    await scope.getByRole("button", { name: "Nächster Monat" }).click();
  }
  await day.first().click();
}

// ---------------------------------------------------------------- the run

test("website screenshots", async ({ browser }) => {
  test.setTimeout(15 * 60_000);
  fs.mkdirSync(OUT, { recursive: true });
  const seed = readSeed();
  const failures: string[] = [];
  const contexts: BrowserContext[] = [];

  /** One shot: skipped unless selected via DOCS_SHOTS_ONLY; a failure is
   *  reported at the end instead of stopping the whole run. */
  const take = async (names: string | string[], page: Page, fn: () => Promise<void>) => {
    const list = Array.isArray(names) ? names : [names];
    if (ONLY.length && !list.some((n) => ONLY.includes(n))) return;
    try {
      await fn();
    } catch (err) {
      const message = err instanceof Error ? err.message.split("\n").slice(0, 3).join(" ") : String(err);
      failures.push(`${list.join("/")}: ${message}`);
      console.log(`  ✗ ${list.join("/")} failed: ${message}`);
    } finally {
      await page.keyboard.press("Escape").catch(() => undefined);
    }
  };
  const want = (name: string) => !ONLY.length || ONLY.includes(name);
  const open = async (user: string, phone = false) => {
    const context = await asUser(browser, user, phone);
    contexts.push(context);
    return context.newPage();
  };
  const go = async (page: Page, url: string, text: string | RegExp) => {
    await page.goto(url);
    await page.getByText(text).filter({ visible: true }).first().waitFor({ timeout: 20_000 });
    await loaded(page);
  };
  const b = seed.bookings;

  try {
    // ------------------------------------------------ borrower (Alex)
    const alex = await open("alex");

    await take("start", alex, async () => {
      await go(alex, "/", "Moin, Alex!");
      await alex.getByText("Gerade beliebt").waitFor();
      await shot(alex, "start");
    });

    await take("kategorie", alex, async () => {
      await go(alex, `/categories/${seed.categories["foto-video"]}`, "Sony Alpha 7 IV");
      await shot(alex, "kategorie");
    });

    await take("suche", alex, async () => {
      await go(alex, "/search?q=Kamera", "Sony Alpha 7 IV");
      await shot(alex, "suche");
    });

    await take(["produkt", "produkt-kalender"], alex, async () => {
      await go(alex, `/products/${seed.products["sony-alpha-7-iv"]}`, "Vollformat-Systemkamera");
      await alex.getByText("Verfügbarkeit & Buchung").waitFor();
      if (want("produkt")) await shot(alex, "produkt");
      const card = bookingCard(alex);
      const start = workday(3);
      await pickDay(card, start);
      await pickDay(card, new Date(start.getTime() + 2 * 86_400_000));
      if (want("produkt-kalender"))
        await shot(alex, "produkt-kalender", { element: alex.getByText("Verfügbarkeit", { exact: true }).locator(".."), until: card });
    });

    await take("produkt-stunden", alex, async () => {
      await go(alex, `/products/${seed.products["gopro-hero12-black"]}`, "Action-Kamera");
      const card = bookingCard(alex);
      await card.waitFor();
      await pickDay(card, workday(1));
      await alex.getByText(/^Stunden am /).waitFor();
      const slots = card.locator("button[title*='frei']");
      await slots.first().waitFor();
      const free = card.locator("button[title*='frei']:not([disabled])");
      const n = await free.count();
      await free.nth(Math.min(n - 1, n - 3)).click();
      await free.nth(n - 1).click();
      await shot(alex, "produkt-stunden", { element: card, pad: 24 });
    });

    await take("set", alex, async () => {
      await go(alex, `/sets/${seed.sets["interview-set"]}`, "Interview-Set");
      await shot(alex, "set");
    });

    await take("warenkorb", alex, async () => {
      await go(alex, "/cart", "Shure SM7B");
      await shot(alex, "warenkorb");
    });

    await take("meine-buchungen", alex, async () => {
      await go(alex, "/bookings", "Überfällig");
      await shot(alex, "meine-buchungen");
    });

    await take("buchung-detail", alex, async () => {
      await go(alex, `/bookings/${b.alex_pickup_today}`, b.alex_pickup_today);
      await shot(alex, "buchung-detail", { height: 720 });
    });

    // ------------------------------------------------ phone (Alex)
    const phone = await open("alex", true);
    await take("handy-start", phone, async () => {
      await go(phone, "/", "Moin, Alex!");
      await shot(phone, "handy-start");
    });
    await take("handy-produkt", phone, async () => {
      await go(phone, `/products/${seed.products["sony-alpha-7-iv"]}`, "Vollformat-Systemkamera");
      await shot(phone, "handy-produkt");
    });

    // ------------------------------------------------ blocked borrower (Robin)
    const robin = await open("robin");
    await take("gesperrt", robin, async () => {
      await go(robin, "/", "Moin, Robin!");
      await robin.getByText(/gesperrt/).first().waitFor();
      await shot(robin, "gesperrt", { height: 560 });
    });

    // ------------------------------------------------ lending desk (Kim)
    const kim = await open("kim");
    /** The "Booking actions" kebab of the booking `code` in a lending list. */
    const bookingMenu = (code: string) =>
      kim
        .locator("main div")
        .filter({ has: kim.getByText(code, { exact: true }) })
        .filter({ has: kim.getByRole("button", { name: "Buchungsaktionen" }) })
        .last()
        .getByRole("button", { name: "Buchungsaktionen" });

    await take("theke-tagesuebersicht", kim, async () => {
      await go(kim, "/manage/day", "Zu bestätigen");
      await shot(kim, "theke-tagesuebersicht");
    });

    await take("theke-ausgabe", kim, async () => {
      await go(kim, "/manage/day", "Abholungen");
      const section = kim.getByText(/^Abholungen \(/);
      await scrollTo(kim, section, 96); // below the sticky header
      // The second pickup's menu, so the first one still shows "Aushändigen".
      await openMenu(kim, bookingMenu(b.jona_pickup_today), false);
      await shot(kim, "theke-ausgabe", {
        element: section,
        before: kim.getByText(/^Fällige Rückgaben \(/),
        until: kim.getByRole("menu"),
        column: true,
      });
    });

    await take("theke-strike", kim, async () => {
      // The dialog with its mail preview is taller than 900 px.
      await kim.setViewportSize({ width: DESKTOP.width, height: 1300 });
      await go(kim, "/manage/day", "Überfällig");
      await openMenu(kim, bookingMenu(b.strike_target));
      await kim.getByRole("menuitem", { name: "Strike vergeben" }).click();
      const dialog = kim.getByRole("dialog");
      await dialog.waitFor();
      await dialog.getByLabel("Grund").fill("Reservierung nicht abgeholt und nicht abgesagt");
      await dialog.getByText("E-Mail-Vorschau").waitFor();
      await kim.waitForTimeout(1200); // preview request is debounced
      // The dialog panel with a margin of the dimmed page around it.
      const panel = dialog.locator("form");
      await shot(kim, "theke-strike", { element: panel, column: true, pad: 48 });
      await dialog.getByRole("button", { name: "Abbrechen" }).click();
      await kim.setViewportSize(DESKTOP);
    });

    await take("theke-qr", kim, async () => {
      await go(kim, "/qr", "QR-Codes");
      const stop = kim.getByRole("button", { name: "Kamera stoppen" });
      if (await stop.isVisible()) await stop.click();
      await kim.getByPlaceholder("Abhol-Code oder Gegenstands-QR").fill(b.alex_pickup_today);
      await kim.getByRole("button", { name: "Eingeben" }).click();
      await kim.getByText(/geladen\./).first().waitFor();
      const device = kim.getByPlaceholder("Gegenstands-QR-ID oder URL");
      await device.fill(seed.resources["MED-0015"].qr);
      await device.press("Enter");
      await kim.getByText(/zugeordnet/).first().waitFor();
      await shot(kim, "theke-qr", { height: 640 });
    });

    await take("theke-direktausleihe", kim, async () => {
      await go(kim, "/manage/walk-in", "Direktausleihe");
      const who = kim.getByPlaceholder(/Nach Name/);
      await who.fill("Alex");
      await kim.getByRole("button", { name: /Alex Beispiel/ }).first().click();
      await kim.getByRole("button", { name: /Canon EOS R6 Mark II/ }).first().click();
      await kim.getByText("3. Zeitraum").waitFor();
      const ret = workday(3);
      const iso = `${ret.getFullYear()}-${String(ret.getMonth() + 1).padStart(2, "0")}-${String(ret.getDate()).padStart(2, "0")}`;
      await kim.locator("main input[type=date]").first().fill(iso);
      await kim.waitForTimeout(1200); // availability check
      await shot(kim, "theke-direktausleihe", { element: kim.locator("main"), column: true, pad: 0 });
    });

    await take("theke-buchungen", kim, async () => {
      await go(kim, "/manage/list", "Alle Buchungen");
      await shot(kim, "theke-buchungen");
    });

    await take("theke-gegenstaende", kim, async () => {
      await go(kim, "/manage/items", "Sony Alpha 7 IV");
      await kim.getByText("Sony Alpha 7 IV").first().click(); // expands its items
      await kim.getByText("MED-0003").first().waitFor();
      await shot(kim, "theke-gegenstaende", { element: kim.locator("main"), column: true, pad: 0 });
    });

    await take("theke-defekte", kim, async () => {
      await go(kim, "/manage/defects", "MED-0003");
      await shot(kim, "theke-defekte", { height: 640 });
    });

    await take("theke-qr-etiketten", kim, async () => {
      await go(kim, "/manage/qr-labels", "QR-Etiketten");
      await shot(kim, "theke-qr-etiketten");
    });

    await take("theke-statistik", kim, async () => {
      await go(kim, "/manage/stats", "Auswertung");
      await shot(kim, "theke-statistik");
    });

    await take("produktformular", kim, async () => {
      await go(kim, "/manage/items", "Sony Alpha 7 IV");
      const row = kim.locator("main li").filter({ hasText: "Sony Alpha 7 IV" }).first();
      await row.getByRole("button", { name: "Aktionen" }).click();
      await kim.getByRole("menuitem", { name: "Produkt bearbeiten" }).click();
      await kim.getByText("Produktdetails").first().waitFor();
      await shot(kim, "produktformular");
    });

    await take("set-formular", kim, async () => {
      await go(kim, "/manage/sets", "Interview-Set");
      await kim.getByText("Interview-Set").first().click();
      await kim.getByText(/Interview-Set bearbeiten/).waitFor();
      await shot(kim, "set-formular");
    });

    // ------------------------------------------------ admin (Sam)
    const sam = await open("sam");

    await take("admin-menue", sam, async () => {
      await go(sam, "/admin", "Administration");
      await sam.getByRole("button", { name: "Bereich wechseln" }).click();
      await sam.getByRole("menu").waitFor();
      await shot(sam, "admin-menue", { height: 420 });
    });

    await take("admin-sperrtage", sam, async () => {
      await go(sam, "/admin", "Inventur");
      await shot(sam, "admin-sperrtage");
    });

    await take("admin-pools", sam, async () => {
      await go(sam, "/admin/pools", "Makerspace");
      await sam.getByText("Makerspace").first().click();
      await sam.getByText(/Makerspace bearbeiten/).waitFor();
      // The access section: which groups may see and book the pool.
      const access = sam.locator("section").filter({ has: sam.locator("#pool-access-heading") }).last();
      await scrollTo(sam, access, 120);
      await shot(sam, "admin-pools", { element: access, column: true, pad: 24 });
    });

    await take("admin-kategorien", sam, async () => {
      await go(sam, "/admin/categories", "Kameras");
      await shot(sam, "admin-kategorien");
    });

    await take("admin-produkttypen", sam, async () => {
      await go(sam, "/admin/product-types", "Kamera");
      await sam.getByText("Kamera", { exact: true }).first().click();
      await sam.getByText(/Kamera bearbeiten/).waitFor();
      await shot(sam, "admin-produkttypen");
    });

    await take("admin-benachrichtigungen", sam, async () => {
      await go(sam, "/admin/notifications", "Benachrichtigungen");
      await shot(sam, "admin-benachrichtigungen");
    });

    await take("admin-nutzer", sam, async () => {
      await go(sam, "/admin/users", "Alex Beispiel");
      await shot(sam, "admin-nutzer");
    });

    await take("admin-zugriffsgruppen", sam, async () => {
      await go(sam, "/admin/access-groups", "Lehrende");
      await shot(sam, "admin-zugriffsgruppen");
    });

    await take("admin-funktionen", sam, async () => {
      await go(sam, "/functions", /^Funktionen$/);
      await shot(sam, "admin-funktionen");
    });
  } finally {
    for (const context of contexts) await context.close();
  }
  if (failures.length) throw new Error(`Screenshots failed:\n${failures.join("\n")}`);
});
