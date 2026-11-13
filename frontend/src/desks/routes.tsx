// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Navigate, Route } from "react-router-dom";
import { BookPage } from "./BookPage";
import { DesksLayout } from "./DesksLayout";
import { FreeNowPage } from "./FreeNowPage";
import { MyReservationsPage } from "./MyReservationsPage";
import { OverviewPage } from "./OverviewPage";
import { SeriesPage } from "./SeriesPage";
import { NotificationSettingsPage } from "./NotificationSettingsPage";

/** Routes of the desksharing area, mounted by `App` inside `RequireAuth`.
 *  Only pages that exist are routed; later tasks add theirs here (and their
 *  menu entry in `DeskTabs` + `appFunctions.ts`):
 *    F2 (rest): /desks/q/:token (QR scan), /desks/a/:token (mail action)
 *    F3: /desks/series/:id
 *    F4: /desks/overview
 *    F5+: /desks/manage/{settings,places,plans/:floorId,absences,stats}
 *  Mails already link to /desks, /desks/mine and /desks/a/<token>; until the
 *  action page exists, unknown /desks/* paths land on the start page. */
export const deskRoutes = (
  <Route path="/desks" element={<DesksLayout />}>
    <Route index element={<FreeNowPage />} />
    <Route path="book" element={<BookPage />} />
    <Route path="overview" element={<OverviewPage />} />
    <Route path="mine" element={<MyReservationsPage />} />
    <Route path="series/:id" element={<SeriesPage />} />
    <Route path="settings/notifications" element={<NotificationSettingsPage />} />
    <Route path="*" element={<Navigate to="/desks" replace />} />
  </Route>
);
