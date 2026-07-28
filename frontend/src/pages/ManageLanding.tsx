// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Navigate } from "react-router-dom";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { Loading } from "../components/Status";

/** Entry point of the lending desk: open "To confirm" if any reservations are
 *  awaiting confirmation, otherwise the day overview. */
export function ManageLanding() {
  const { data, error } = useFetch<{ count: number }>(() => api.getPendingCount(), []);

  if (!data && !error) return <Loading />;
  const target = data && data.count > 0 ? "/manage/confirm" : "/manage/day";
  return <Navigate to={target} replace />;
}
