// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "./auth";

type Role = "admin" | "lender";
export type Area = "lending" | "admin";

/** Display order of the areas (same as the header: lending desk, then admin). */
export const AREAS: Area[] = ["lending", "admin"];

interface RawFn {
  to: string;
  /** Menu area the function belongs to (ManageTabs = lending, AdminTabs = admin). */
  area: Area;
  /** English i18n key — reuses the existing tab labels. */
  label: string;
  /** English i18n key for the one-line description. */
  desc: string;
  /** English i18n key for the group heading (existing tab-group labels). */
  group: string;
  roles: Role[];
  /** Extra search synonyms (German + English), matched case-insensitively. */
  keywords: string[];
}

// Entries are listed in menu order (area, then group, then item): the
// functions page and the search prefix derive their order from it.
// A single registry powering both the function search and the glossary page
// (issue #28). Labels/groups reuse existing keys so their translations apply.
const RAW: RawFn[] = [
  // Lending desk
  { to: "/manage/day", area: "lending", label: "Day overview", desc: "Today's pickups and returns at a glance.", group: "Bookings & handout", roles: ["lender"], keywords: ["heute", "tag", "übersicht", "today"] },
  { to: "/manage/day#to_confirm", area: "lending", label: "To confirm", desc: "Approve reservations awaiting confirmation.", group: "Bookings & handout", roles: ["lender"], keywords: ["bestätigen", "freigeben", "pending", "offen", "reservierung"] },
  { to: "/manage/walk-in", area: "lending", label: "Walk-in", desc: "Lend out on the spot, with immediate hand-out.", group: "Bookings & handout", roles: ["lender"], keywords: ["direktausleihe", "sofortausgabe", "spontan", "direkt", "walk-in", "sofort", "theke"] },
  { to: "/manage/list", area: "lending", label: "All bookings", desc: "Search and manage every booking.", group: "Bookings & handout", roles: ["lender"], keywords: ["buchungen", "reservierungen", "suche", "liste"] },
  { to: "/qr", area: "lending", label: "QR codes", desc: "Scan a pickup code or device QR — hand out, take back, or locate a device.", group: "Bookings & handout", roles: ["lender"], keywords: ["ausgabe", "qr", "scannen", "abholung", "rückgabe", "kamera", "codes"] },
  // Inventory
  { to: "/manage/items", area: "lending", label: "Items", desc: "Products and their items: status, return dates, maintenance.", group: "Inventory", roles: ["lender"], keywords: ["ressourcen", "geräte", "bestand", "inventar", "inventory", "räume", "produkte", "katalog", "gegenstände", "gegenstand"] },
  { to: "/manage/defects", area: "lending", label: "Defects", desc: "Devices marked defective — repair or retire them.", group: "Inventory", roles: ["lender"], keywords: ["defekt", "kaputt", "reparatur", "mangel"] },
  { to: "/manage/sets", area: "lending", label: "Sets", desc: "Bundles of products often lent together.", group: "Inventory", roles: ["lender"], keywords: ["sets", "bundle", "paket"] },
  { to: "/manage/qr-labels", area: "lending", label: "QR labels", desc: "Print QR stickers for devices.", group: "Inventory", roles: ["lender"], keywords: ["qr", "etiketten", "labels", "aufkleber", "drucken"] },
  { to: "/manage/defect-tickets", area: "lending", label: "Connect GitLab", desc: "Open a GitLab issue when a device is marked defective.", group: "Inventory", roles: ["lender"], keywords: ["gitlab", "tickets", "defekt", "integration"] },
  // Analytics
  { to: "/manage/stats", area: "lending", label: "Statistics", desc: "Usage, capacity and configured limits.", group: "Analytics", roles: ["lender"], keywords: ["statistik", "auswertung", "zahlen", "kapazität"] },
  // Catalog (admin)
  { to: "/admin/sections", area: "admin", label: "Sections", desc: "Top-level catalog grouping (Sparten).", group: "Catalog", roles: ["admin"], keywords: ["sparten", "bereiche", "gliederung"] },
  { to: "/admin/categories", area: "admin", label: "Categories", desc: "The shop navigation: categories and subcategories of products.", group: "Catalog", roles: ["admin"], keywords: ["kategorien", "unterkategorien", "navigation", "baum", "gliederung"] },
  { to: "/admin/product-types", area: "admin", label: "Product types", desc: "Group products into types with dynamic attributes.", group: "Catalog", roles: ["admin"], keywords: ["produkttypen", "typen", "attribute", "vorlagen"] },
  // Locations & settings (admin)
  { to: "/admin/pools", area: "admin", label: "Resource pools", desc: "Locations, opening hours and booking rules.", group: "Locations & settings", roles: ["admin"], keywords: ["pools", "standorte", "orte", "öffnungszeiten", "servicezeiten"] },
  { to: "/admin", area: "admin", label: "Block days", desc: "Closures and public holidays.", group: "Locations & settings", roles: ["admin"], keywords: ["sperrtage", "feiertage", "schließung", "closure", "urlaub"] },
  { to: "/admin/cart", area: "admin", label: "Cart", desc: "How long a cart holds a resource.", group: "Locations & settings", roles: ["admin"], keywords: ["warenkorb", "hold", "reservierung"] },
  { to: "/admin/notifications", area: "admin", label: "Notifications", desc: "Custom text for the borrower emails.", group: "Locations & settings", roles: ["admin"], keywords: ["benachrichtigungen", "mails", "emails", "vorlagen", "texte"] },
  { to: "/admin/pages", area: "admin", label: "Pages", desc: "Content pages and footer links.", group: "Locations & settings", roles: ["admin"], keywords: ["seiten", "impressum", "datenschutz", "cms"] },
  { to: "/admin/data", area: "admin", label: "Import / export", desc: "Back up or move the catalog data set.", group: "Locations & settings", roles: ["admin"], keywords: ["import", "export", "backup", "daten", "zip"] },
  { to: "/admin/trash", area: "admin", label: "Trash", desc: "Restore or permanently delete items moved to the trash.", group: "Locations & settings", roles: ["admin"], keywords: ["papierkorb", "gelöscht", "wiederherstellen", "trash"] },
  // People & access (admin)
  { to: "/admin/users", area: "admin", label: "Users", desc: "Roles and pool memberships.", group: "People & access", roles: ["admin"], keywords: ["nutzer", "benutzer", "rollen", "personen"] },
  { to: "/admin/access-groups", area: "admin", label: "Access groups", desc: "Who may see and book each pool.", group: "People & access", roles: ["admin"], keywords: ["zugriffsgruppen", "gruppen", "zugriff", "berechtigung", "claim"] },
  { to: "/admin/strike-rules", area: "admin", label: "Strike rules", desc: "Thresholds and expiry for strikes.", group: "People & access", roles: ["admin"], keywords: ["strike", "sperre", "verwarnung", "regeln", "blockieren"] },
  { to: "/admin/retention", area: "admin", label: "Data retention", desc: "Automatic anonymization of inactive accounts (GDPR).", group: "People & access", roles: ["admin"], keywords: ["aufbewahrung", "dsgvo", "anonymisieren", "löschen", "retention"] },
];

export interface AppFn {
  to: string;
  area: Area;
  label: string;
  description: string;
  group: string;
  keywords: string[];
}

/** Localized, role-filtered app functions (admins see everything). */
export function useAppFunctions(): AppFn[] {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isStaff = !!user?.is_staff;
  const isLender = !!user?.is_lender;
  return useMemo(
    () =>
      RAW.filter(
        (f) =>
          (f.roles.includes("admin") && isStaff) ||
          (f.roles.includes("lender") && (isLender || isStaff)),
      ).map((f) => ({
        to: f.to,
        area: f.area,
        label: t(f.label),
        description: t(f.desc),
        group: t(f.group),
        keywords: f.keywords,
      })),
    [t, isStaff, isLender],
  );
}

/** Filter by a free-text query (every term must match label/description/keywords). */
export function filterFunctions(fns: AppFn[], query: string): AppFn[] {
  const q = query.trim().toLowerCase();
  if (!q) return fns;
  const terms = q.split(/\s+/);
  return fns.filter((f) => {
    const hay = `${f.label} ${f.description} ${f.keywords.join(" ")}`.toLowerCase();
    return terms.every((term) => hay.includes(term));
  });
}
