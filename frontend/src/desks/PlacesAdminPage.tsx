// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useDesks } from "./DesksLayout";
import { PlacesWorkspace } from "./admin/PlacesWorkspace";

/** Administration of places ("Plätze"): one workspace per building and floor.
 *  Floors are campus-wide: app admins set up everything; department admins
 *  work on the floors of their department. */
export function PlacesAdminPage() {
  const { pool, isAdmin } = useDesks();
  const { user } = useAuth();
  if (!isAdmin) return <Navigate to="/desks" replace />;
  return <PlacesWorkspace pool={pool} appAdmin={!!user?.is_staff} />;
}
