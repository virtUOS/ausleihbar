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
import { PlacesAdminPage } from "./PlacesAdminPage";
import { FloorPlanEditorPage } from "./FloorPlanEditorPage";
import { DeskSettingsPage } from "./DeskSettingsPage";
import { AbsencesPage } from "./AbsencesPage";
import { DeskStatsPage } from "./DeskStatsPage";
import { PlaceQrLabelsPage } from "./PlaceQrLabelsPage";
import { CheckInPage } from "./CheckInPage";
import { ActionPage } from "./ActionPage";

/** Routes of the desksharing area, mounted by `App` inside `RequireAuth`.
 *  Only pages that exist are routed; later tasks add theirs here (and their
 *  menu entry in `DeskTabs` + `appFunctions.ts`):
 *    F3: /desks/series/:id
 *    F4: /desks/overview
 *    F5: /desks/manage/places, /desks/manage/plans/:floorId
 *    F6: /desks/manage/{settings,absences,stats,qr}
 *  /desks/q/:token (QR check-in) and /desks/a/:token (mail action) are
 *  token pages without a menu entry; unknown /desks/* paths land on the start page. */
export const deskRoutes = (
  <Route path="/desks" element={<DesksLayout />}>
    <Route index element={<FreeNowPage />} />
    <Route path="book" element={<BookPage />} />
    <Route path="overview" element={<OverviewPage />} />
    <Route path="mine" element={<MyReservationsPage />} />
    <Route path="q/:token" element={<CheckInPage />} />
    <Route path="a/:token" element={<ActionPage />} />
    <Route path="series/:id" element={<SeriesPage />} />
    <Route path="settings/notifications" element={<NotificationSettingsPage />} />
    <Route path="manage/places" element={<PlacesAdminPage />} />
    <Route path="manage/settings" element={<DeskSettingsPage />} />
    <Route path="manage/absences" element={<AbsencesPage />} />
    <Route path="manage/stats" element={<DeskStatsPage />} />
    <Route path="manage/qr" element={<PlaceQrLabelsPage />} />
    <Route path="manage/plans/:floorId" element={<FloorPlanEditorPage />} />
    <Route path="*" element={<Navigate to="/desks" replace />} />
  </Route>
);
