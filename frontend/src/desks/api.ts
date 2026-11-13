// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Client for the desksharing API (`/api/desks/…`). Shares the request helpers
// (CSRF, error mapping, language header) with the main client.
import { getBlob, getJson, mutate, postFile } from "../api";
import type {
  Absence,
  BookRequest,
  BookResult,
  DayHours,
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
    mutate<Absence>("/api/desks/absences/", "POST", data),
  deleteAbsence: (id: number) => mutate<void>(`/api/desks/absences/${id}/`, "DELETE"),
  profile: () => getJson<{ hide_name: boolean }>("/api/desks/profile/"),
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
  floors: () => getAll<Floor>("/api/desks/manage/floors/"),
  rooms: () => getAll<Room>("/api/desks/manage/rooms/"),
  places: () => getAll<Place>("/api/desks/manage/places/"),
  saveFloorPlan: (floorId: number, plan: PlanJson) =>
    mutate<{ plan: PlanJson }>(`/api/desks/manage/floors/${floorId}/plan/`, "PUT", { plan }),
  floor: (floorId: number) => getJson<Floor>(`/api/desks/manage/floors/${floorId}/`),
  updateFloor: (floorId: number, data: Partial<Pick<Floor, "scale_px_per_m" | "name" | "building" | "position">>) =>
    mutate<Floor>(`/api/desks/manage/floors/${floorId}/`, "PATCH", data),
  /** The floor's drawing template as a blob (admins only; use as object URL). */
  floorTemplate: (floorId: number) => getBlob(`/api/desks/manage/floors/${floorId}/template/`),
  uploadFloorTemplate: (floorId: number, file: File) =>
    postFile<Floor>(`/api/desks/manage/floors/${floorId}/template/`, "file", file),
  updatePlace: (placeId: number, data: Partial<Omit<Place, "id" | "qr_token">>) =>
    mutate<Place>(`/api/desks/manage/places/${placeId}/`, "PATCH", data),
  manageReservations: (pool: number, day: string) =>
    getJson<ManageReservation[]>(`/api/desks/manage/reservations/${qs({ pool, day })}`),
  stats: (pool: number, start: string, end: string) =>
    getJson<DeskStats>(`/api/desks/manage/stats/${qs({ pool, start, end })}`),
};
