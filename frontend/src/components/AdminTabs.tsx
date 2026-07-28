// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

import i18n from "../i18n";
import { TabMenu, type TabGroup } from "./TabMenu";
import { FunctionSearchBar } from "./FunctionSearchBar";

/**
 * Admin navigation: top-level areas, each revealing its own submenu. Items run
 * from the structural level down to the individual element within each area.
 */
function buildGroups(t: typeof i18n.t): TabGroup[] {
  return [
    {
      label: t("Catalog"),
      items: [
        { to: "/admin/sections", label: t("Sections") },
        { to: "/admin/categories", label: t("Categories") },
        { to: "/admin/product-types", label: t("Product types") },
      ],
    },
    {
      label: t("Locations & settings"),
      items: [
        { to: "/admin/pools", label: t("Resource pools") },
        { to: "/admin", label: t("Block days"), end: true },
        { to: "/admin/cart", label: t("Cart") },
        { to: "/admin/notifications", label: t("Notifications") },
        { to: "/admin/pages", label: t("Pages") },
        { to: "/admin/data", label: t("Import / export") },
      ],
    },
    {
      label: t("People & access"),
      items: [
        { to: "/admin/users", label: t("Users") },
        { to: "/admin/access-groups", label: t("Access groups") },
        { to: "/admin/strike-rules", label: t("Strike rules") },
        { to: "/admin/retention", label: t("Data retention") },
      ],
    },
  ];
}

/** Switches between the admin views via a grouped, two-level menu. */
export function AdminTabs() {
  const { t } = useTranslation();
  return (
    <>
      <FunctionSearchBar />
      <TabMenu groups={buildGroups(t)} />
    </>
  );
}
