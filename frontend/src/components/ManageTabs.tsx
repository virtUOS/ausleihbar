// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";

import i18n from "../i18n";
import { TabMenu, type TabGroup } from "./TabMenu";
import { FunctionSearchBar } from "./FunctionSearchBar";
import { PoolScopeSwitch } from "./PoolScopeSwitch";

/**
 * Lending-desk navigation: top-level areas, each revealing its own submenu —
 * mirrors the admin menu (`AdminTabs`).
 */
function buildGroups(t: typeof i18n.t): TabGroup[] {
  return [
    {
      label: t("Bookings & handout"),
      items: [
        { to: "/manage/day", label: t("Day overview") },
        { to: "/manage/walk-in", label: t("Walk-in") },
        { to: "/manage/list", label: t("All bookings") },
      ],
    },
    {
      // Inventory and catalog merged into one area: the split between physical
      // stock and catalog entries was more confusing than helpful.
      label: t("Inventory"),
      items: [
        { to: "/manage/inventory", label: t("Resources") },
        { to: "/manage/defects", label: t("Defects") },
        { to: "/manage/products", label: t("Products") },
        { to: "/manage/sets", label: t("Sets") },
        { to: "/manage/qr-labels", label: t("QR labels") },
      ],
    },
    {
      label: t("Analytics"),
      items: [
        { to: "/manage/stats", label: t("Statistics") },
      ],
    },
  ];
}

/** Switches between the lending-desk views via a grouped, two-level menu.
 *  Admins assigned as lenders also get the "My pools | All pools" switch here;
 *  changing it remounts the page (see `App`), which refetches the page data
 *  with the new scope. */
export function ManageTabs({
  showPoolScope = false,
}: {
  /** Show the pool-scope switch — only on pages whose data depends on it. */
  showPoolScope?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <>
      {showPoolScope && <PoolScopeSwitch />}
      <FunctionSearchBar />
      <TabMenu groups={buildGroups(t)} />
    </>
  );
}
