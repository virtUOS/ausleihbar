// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Loading } from "../components/Status";

/** Door displays moved to the admin area ("Verbindungen"); old links keep working. */
export function DisplaysRedirect() {
  const { user, loading } = useAuth();
  // Wait for the session: redirecting before it loads would send admins to /desks.
  if (loading) return <Loading />;
  return <Navigate to={user?.is_staff ? "/admin/displays" : "/desks"} replace />;
}
