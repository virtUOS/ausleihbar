// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

/** Door displays moved to the admin area ("Verbindungen"); old links keep working. */
export function DisplaysRedirect() {
  const { user } = useAuth();
  return <Navigate to={user?.is_staff ? "/admin/displays" : "/desks"} replace />;
}
