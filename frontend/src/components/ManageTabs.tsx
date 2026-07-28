// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import i18n from "../i18n";
import { api } from "../api";
import { TabMenu, type TabGroup } from "./TabMenu";
import { FunctionSearchBar } from "./FunctionSearchBar";

/**
 * Lending-desk navigation: top-level areas, each revealing its own submenu —
 * mirrors the admin menu (`AdminTabs`). The "To confirm" item shows a red badge
 * with the number of reservations awaiting confirmation.
 */
function buildGroups(t: typeof i18n.t, pending: number): TabGroup[] {
  return [
    {
      label: t("Bookings & handout"),
      items: [
        { to: "/manage/day", label: t("Day overview") },
        { to: "/manage/confirm", label: t("To confirm"), badge: pending },
        { to: "/manage/list", label: t("All bookings") },
        { to: "/manage/walk-in", label: t("Walk-in") },
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
        { to: "/manage/borrowers", label: t("Borrowers") },
      ],
    },
  ];
}

/** Switches between the lending-desk views via a grouped, two-level menu.
 *  Pass a changing `pendingVersion` to refetch the confirmation badge count. */
export function ManageTabs({ pendingVersion = 0 }: { pendingVersion?: number }) {
  const { t } = useTranslation();
  const [pending, setPending] = useState(0);

  useEffect(() => {
    let active = true;
    api
      .getPendingCount()
      .then((res) => active && setPending(res.count))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [pendingVersion]);

  return (
    <>
      <FunctionSearchBar />
      <TabMenu groups={buildGroups(t, pending)} />
    </>
  );
}
