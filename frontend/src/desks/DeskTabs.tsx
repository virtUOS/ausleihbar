// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import { TabMenu, type TabGroup } from "../components/TabMenu";

/** Navigation of the desksharing area. Later tasks add their views here
 *  (book, overview, series, department administration) and in appFunctions. */
function buildGroups(t: typeof i18n.t, isAdmin: boolean, isAssistant: boolean): TabGroup[] {
  const groups: TabGroup[] = [
    {
      label: t("Desks"),
      items: [
        { to: "/desks", label: t("Free now"), end: true },
        { to: "/desks/book", label: t("Book") },
        { to: "/desks/overview", label: t("Overview") },
        { to: "/desks/mine", label: t("My reservations") },
        { to: "/desks/settings/notifications", label: t("Notifications") },
      ],
    },
  ];
  // Department administration: assistants only see the absences page.
  if (isAdmin || isAssistant) {
    const items = [];
    if (isAdmin) {
      items.push(
        { to: "/desks/manage/places", label: t("Places"), alsoMatch: ["/desks/manage/plans"] },
        { to: "/desks/manage/settings", label: t("Settings") },
      );
    }
    items.push({ to: "/desks/manage/absences", label: t("Absences") });
    if (isAdmin) items.push({ to: "/desks/manage/stats", label: t("Statistics") });
    groups.push({ label: t("Desk administration"), items });
  }
  return groups;
}

export function DeskTabs({
  isAdmin = false,
  isAssistant = false,
}: {
  isAdmin?: boolean;
  isAssistant?: boolean;
}) {
  const { t } = useTranslation();
  return <TabMenu groups={buildGroups(t, isAdmin, isAssistant)} />;
}
