// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Client for the desksharing API (`/api/desks/…`). Shares the request helpers
// (CSRF, error mapping, language header) with the main client.
import { getBlob, getJson, mutate, postFile } from "../api";
import type {
  AccessGroupChoice,
  Absence,
  BookRequest,
  BookResult,
  DayHours,
  ActionContext,
  DeskAction,
  MyRequests,
  DeskSettings,
  DeskStats,
  DepartmentDay,
  Feature,
  FreeNowPlace,
  FreePlace,
  Floor,
  ManageReservation,
  NotificationPreferences,
  Place,
  PersonChoice,
  PlaceInput,
  PlaceKind,
  PlanJson,
  Reservation,
  Room,
  ScanResult,
  Series,
  SeriesConflict,
  SeriesRequest,
  SeriesResult,
} from "./types";

const qs = (params: Record<string, string | number | undefined | null>): string => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
};

/** All rows of a paginated admin list (`{count, next, results}`): asks for
 *  big pages and follows `next` (an absolute URL) by its path. */
async function getAll<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  let next: string | null = `${path}${path.includes("?") ? "&" : "?"}page_size=2000`;
  while (next) {
    const page: { next: string | null; results: T[] } = await getJson(next);
    rows.push(...page.results);
    next = page.next ? new URL(page.next).pathname + new URL(page.next).search : null;
  }
  return rows;
}

export const desksApi = {
  // Booking and own reservations
  freeNow: (pool: number, kind?: PlaceKind, features?: number[]) =>
    getJson<FreeNowPlace[]>(
      `/api/desks/free-now/${qs({ pool, kind, features: features?.join(",") })}`,
    ),
  free: (p: {
    pool: number;
    kind: PlaceKind;
    day: string;
    start_hour: number;
    end_hour: number;
    features?: number[];
    /** Assistants: compute the list for this person's rights. */
    holder?: number | null;
  }) => getJson<FreePlace[]>(`/api/desks/free/${qs({ ...p, features: p.features?.join(",") })}`),
  book: (data: BookRequest) => mutate<BookResult>("/api/desks/reservations/", "POST", data),
  myReservations: () => getJson<Reservation[]>("/api/desks/reservations/mine/"),
  cancelReservation: (id: number, reason?: string) =>
    mutate<void>(`/api/desks/reservations/${id}/`, "DELETE", reason ? { reason } : {}),
  poolFeatures: (pool: number) => getJson<Feature[]>(`/api/desks/features/${qs({ pool })}`),
  hours: (pool: number, day: string) =>
    getJson<DayHours>(`/api/desks/hours/${qs({ pool, day })}`),
  later: (id: number, until: string) =>
    mutate<Reservation>(`/api/desks/reservations/${id}/later/`, "POST", { until }),
  /** Free places of the same kind for the same hours that the holder may
   *  book (works for hidden holders too; the holder's id never leaves the API). */
  moveTargets: (id: number) => getJson<FreePlace[]>(`/api/desks/reservations/${id}/move-targets/`),
  move: (id: number, placeId: number) =>
    mutate<Reservation>(`/api/desks/reservations/${id}/move/`, "POST", { place_id: placeId }),
  neighbours: (id: number) =>
    getJson<(string | null)[]>(`/api/desks/reservations/${id}/neighbours/`),
  myRequests: () => getJson<MyRequests>("/api/desks/requests/mine/"),
  requestSwap: (mineId: number, theirsId: number) =>
    mutate<unknown>("/api/desks/swap-requests/", "POST", { mine_id: mineId, theirs_id: theirsId }),
  answerSwap: (id: number, accept: boolean) =>
    mutate<unknown>(`/api/desks/swap-requests/${id}/answer/`, "POST", { accept }),
  requestRelease: (reservationId: number, showName: boolean) =>
    mutate<unknown>("/api/desks/release-requests/", "POST", {
      reservation_id: reservationId,
      show_name: showName,
    }),
  answerRelease: (id: number, accept: boolean) =>
    mutate<unknown>(`/api/desks/release-requests/${id}/answer/`, "POST", { accept }),
  checkIn: (id: number) => mutate<Reservation>(`/api/desks/reservations/${id}/check-in/`, "POST"),
  scan: (token: string) => mutate<ScanResult>("/api/desks/scan/", "POST", { token }),
  checkInPlace: (placeId: number) =>
    mutate<ScanResult>(`/api/desks/places/${placeId}/check-in/`, "POST"),
  actionContext: (token: string) =>
    getJson<ActionContext>(`/api/desks/actions/context/${qs({ token })}`),
  action: (token: string, action: DeskAction, until?: string) =>
    mutate<{ action: DeskAction; done: boolean }>("/api/desks/actions/", "POST", {
      token,
      action,
      ...(until ? { until } : {}),
    }),

  // Series
  mySeries: () => getJson<Series[]>("/api/desks/series/mine/"),
  createSeries: (data: SeriesRequest) =>
    mutate<SeriesResult>("/api/desks/series/", "POST", data),
  cancelSeries: (id: number, reason?: string) =>
    mutate<void>(`/api/desks/series/${id}/`, "DELETE", reason ? { reason } : {}),
  seriesConflicts: (id: number) =>
    getJson<SeriesConflict[]>(`/api/desks/series/${id}/conflicts/`),
  resolveSeries: (id: number, day: string, placeId: number) =>
    mutate<Reservation>(`/api/desks/series/${id}/resolve/`, "POST", { day, place_id: placeId }),
  extendSeries: (id: number) => mutate<SeriesResult>(`/api/desks/series/${id}/extend/`, "POST"),

  // Overview, absences, preferences
  overview: (pool: number, day?: string) =>
    getJson<DepartmentDay>(`/api/desks/overview/${qs({ pool, day })}`),
  absences: () => getJson<Absence[]>("/api/desks/absences/"),
  createAbsence: (data: Pick<Absence, "start_date" | "end_date" | "kind">) =>
    mutate<Absence & { released_count: number }>("/api/desks/absences/", "POST", data),
  deleteAbsence: (id: number) =>
    mutate<{ kept_bookings: number }>(`/api/desks/absences/${id}/`, "DELETE"),
  profile: () => getJson<{ hide_name: boolean }>("/api/desks/profile/"),
  favorites: () => getJson<{ place_ids: number[] }>("/api/desks/favorites/"),
  setFavorite: (placeId: number, on: boolean) =>
    mutate<{ place_id: number; favorite: boolean }>(`/api/desks/favorites/${placeId}/`, on ? "PUT" : "DELETE"),
  setHideName: (hide_name: boolean) =>
    mutate<{ hide_name: boolean }>("/api/desks/profile/", "PUT", { hide_name }),
  notificationPreferences: () =>
    getJson<NotificationPreferences>("/api/desks/notification-preferences/"),
  setNotificationPreferences: (changes: NotificationPreferences) =>
    mutate<NotificationPreferences>("/api/desks/notification-preferences/", "PUT", changes),

  // Department administration
  settings: (pool: number) => getJson<DeskSettings>(`/api/desks/manage/settings/${pool}/`),
  updateSettings: (pool: number, data: Partial<DeskSettings>) =>
    mutate<DeskSettings>(`/api/desks/manage/settings/${pool}/`, "PUT", data),
  features: () => getAll<Feature>("/api/desks/manage/features/"),
  // `all` includes deactivated rows (soft-deleted floors, rooms, places).
  floors: (all = false) => getAll<Floor>(`/api/desks/manage/floors/${all ? "?include_inactive=1" : ""}`),
  rooms: (all = false) => getAll<Room>(`/api/desks/manage/rooms/${all ? "?include_inactive=1" : ""}`),
  places: (all = false) => getAll<Place>(`/api/desks/manage/places/${all ? "?include_inactive=1" : ""}`),
  saveFloorPlan: (floorId: number, plan: PlanJson) =>
    mutate<{ plan: PlanJson }>(`/api/desks/manage/floors/${floorId}/plan/`, "PUT", { plan }),
  floor: (floorId: number) => getJson<Floor>(`/api/desks/manage/floors/${floorId}/`),
  updateFloor: (floorId: number, data: Partial<Pick<Floor, "scale_px_per_m" | "name_de" | "name_en" | "building" | "position" | "is_active">>) =>
    mutate<Floor>(`/api/desks/manage/floors/${floorId}/`, "PATCH", data),
  /** The floor's drawing template as a blob (admins only; use as object URL). */
  floorTemplate: (floorId: number) => getBlob(`/api/desks/manage/floors/${floorId}/template/`),
  uploadFloorTemplate: (floorId: number, file: File) =>
    postFile<Floor>(`/api/desks/manage/floors/${floorId}/template/`, "file", file),
  createFloor: (data: Pick<Floor, "pool" | "name_de" | "name_en" | "building" | "position">) =>
    mutate<Floor>("/api/desks/manage/floors/", "POST", data),
  deleteFloor: (id: number) => mutate<void>(`/api/desks/manage/floors/${id}/`, "DELETE"),
  createRoom: (data: Pick<Room, "floor" | "name_de" | "name_en" | "kind">) =>
    mutate<Room>("/api/desks/manage/rooms/", "POST", data),
  updateRoom: (id: number, data: Partial<Pick<Room, "floor" | "name_de" | "name_en" | "kind" | "is_active">>) =>
    mutate<Room>(`/api/desks/manage/rooms/${id}/`, "PATCH", data),
  deleteRoom: (id: number) => mutate<void>(`/api/desks/manage/rooms/${id}/`, "DELETE"),
  createFeature: (data: Pick<Feature, "pool" | "name_de" | "name_en">) =>
    mutate<Feature>("/api/desks/manage/features/", "POST", data),
  updateFeature: (id: number, data: Partial<Pick<Feature, "name_de" | "name_en">>) =>
    mutate<Feature>(`/api/desks/manage/features/${id}/`, "PATCH", data),
  deleteFeature: (id: number) => mutate<void>(`/api/desks/manage/features/${id}/`, "DELETE"),
  createPlace: (data: PlaceInput) => mutate<Place>("/api/desks/manage/places/", "POST", data),
  updatePlace: (placeId: number, data: Partial<PlaceInput> & Partial<Pick<Place, "plan_symbol">>) =>
    mutate<Place>(`/api/desks/manage/places/${placeId}/`, "PATCH", data),
  deletePlace: (id: number) => mutate<void>(`/api/desks/manage/places/${id}/`, "DELETE"),
  regeneratePlaceQr: (id: number) =>
    mutate<Place>(`/api/desks/manage/places/${id}/regenerate-qr/`, "POST"),
  /** The place's QR sticker as a PNG blob (admins only; use as object URL). */
  placeQr: (id: number) => getBlob(`/api/desks/manage/places/${id}/qr/`),
  accessGroups: (pool: number) =>
    getJson<AccessGroupChoice[]>(`/api/desks/manage/access-groups/${qs({ pool })}`),
  /** Members of a department by name (min. 3 characters). */
  people: (pool: number, q: string) =>
    getJson<PersonChoice[]>(`/api/desks/manage/people/${qs({ pool, q })}`),
  manageAbsences: (pool: number) =>
    getJson<Absence[]>(`/api/desks/manage/absences/${qs({ pool })}`),
  createManageAbsence: (data: Pick<Absence, "user" | "start_date" | "end_date" | "kind">) =>
    mutate<Absence>("/api/desks/manage/absences/", "POST", data),
  deleteManageAbsence: (id: number) =>
    mutate<{ kept_bookings: number }>(`/api/desks/manage/absences/${id}/`, "DELETE"),
  statsCsv: (pool: number, start: string, end: string) =>
    getBlob(`/api/desks/manage/stats.csv${qs({ pool, start, end })}`),
  manageReservations: (pool: number, day: string) =>
    getJson<ManageReservation[]>(`/api/desks/manage/reservations/${qs({ pool, day })}`),
  stats: (pool: number, start: string, end: string) =>
    getJson<DeskStats>(`/api/desks/manage/stats/${qs({ pool, start, end })}`),
};
