// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import type { Building, Feature, Floor, Place, Room } from "../types";

/** What the places administration loads (app admins: everything; department
 *  admins: the floors, rooms and places of their departments). */
export interface PlacesAdminData {
  floors: Floor[];
  rooms: Room[];
  places: Place[];
  features: Feature[];
  /** The campus-wide building list. */
  buildings: Building[];
}

/** Props shared by the administration sections of one department. */
export interface AdminSectionProps {
  pool: number;
  /** App admin: sets up floors and rooms and edits the equipment; department
   *  admins edit their rooms and places and add places to their rooms. */
  appAdmin: boolean;
  data: PlacesAdminData;
  /** Re-fetch after a change. */
  onChanged: () => void;
}

/** The floors of the department `pool` (holding its rooms or places); app
 *  admins see every floor (floors are campus-wide). */
export function departmentFloors(data: PlacesAdminData, pool: number, appAdmin: boolean): PlacesAdminData["floors"] {
  if (appAdmin) return data.floors;
  const roomFloor = new Map(data.rooms.map((r) => [r.id, r.floor]));
  const ids = new Set([
    ...data.rooms.filter((r) => r.pool === pool).map((r) => r.floor),
    ...data.places.filter((p) => p.pool === pool).map((p) => roomFloor.get(p.room)),
  ]);
  return data.floors.filter((f) => ids.has(f.id));
}
