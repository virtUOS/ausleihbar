// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { Feature, Floor, Place, Room } from "../types";

/** What the places administration loads (all departments of the admin). */
export interface PlacesAdminData {
  floors: Floor[];
  rooms: Room[];
  places: Place[];
  features: Feature[];
}

/** Props shared by the administration sections of one department. */
export interface AdminSectionProps {
  pool: number;
  data: PlacesAdminData;
  /** Re-fetch after a change. */
  onChanged: () => void;
}
