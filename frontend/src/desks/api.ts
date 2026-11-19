// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Client for the desksharing API (`/api/desks/…`). Shares the request helpers
// (CSRF, error mapping, language header) with the main client.
import { getBlob, getJson, mutate, postFile, uploadGalleryImage } from "../api";
import type { GalleryOps } from "../components/ProductImagesField";
import type {
  FavoritePlace,
  AccessGroupChoice,
  Absence,
  BookRequest,
  BookResult,
  BookDaysRequest,
  BookDaysResult,
  BookingWindow,
  DaysAvailability,
  PlaceDay,
  Building,
  LocationFloor,
  DayHours,
  ActionContext,
  DeskAction,
  MyRequests,
  DeskSettings,
  DeskStats,
  DepartmentDay,
  Feature,
  FeatureImage,
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
  PlanSymbol,
  Reservation,
  Room,
  ScanResult,
  Series,
  SeriesConflict,
  SeriesRequest,
  SeriesResult,
  AssignRequest,
  PlaceGroupsRequest,
  BatchResult,
  DeskAdminSetting,
  RoomBatchRequest,
  PlaceBatchRequest,
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

/** Writable fields of equipment (descriptions: app admins only). */
export type FeatureInput = Pick<Feature, "name_de" | "name_en"> &
  Partial<Pick<Feature, "description_de" | "description_en">>;

export const desksApi = {
  // Booking and own reservations
  freeNow: (pool: number, kind?: PlaceKind, features?: number[]) =>
    getJson<FreeNowPlace[]>(
      `/api/desks/free-now/${qs({ pool, kind, features: features?.join(",") })}`,
    ),
  book: (data: BookRequest) => mutate<BookResult>("/api/desks/reservations/", "POST", data),
  /** Book several days x places at once (all or nothing). */
  bookDays: (data: BookDaysRequest) =>
    mutate<BookDaysResult>("/api/desks/reservations/days/", "POST", data),
  /** The booking window and the person's (or `holder`'s) advance quota. */
  window: (pool: number, holder?: number | null) =>
    getJson<BookingWindow>(`/api/desks/window/${qs({ pool, holder })}`),
  /** Per day of `from..to`: closed, and the hours of one place taken by others. */
  placeDays: (placeId: number, from: string, to: string, holder?: number | null) =>
    getJson<PlaceDay[]>(`/api/desks/places/${placeId}/days/${qs({ from, to, holder })}`),
  /** Bookable places of a kind over several days (open, non-past days only). */
  availability: (p: {
    pool: number;
    kind: PlaceKind;
    days: string[];
    start_hour: number;
    end_hour: number;
    features?: number[];
    holder?: number | null;
  }) =>
    getJson<DaysAvailability[]>(
      `/api/desks/availability/${qs({ ...p, days: p.days.join(","), features: p.features?.join(",") })}`,
    ),
  myReservations: () => getJson<Reservation[]>("/api/desks/reservations/mine/"),
  cancelReservation: (id: number, reason?: string) =>
    mutate<void>(`/api/desks/reservations/${id}/`, "DELETE", reason ? { reason } : {}),
  poolFeatures: (pool: number) => getJson<Feature[]>(`/api/desks/features/${qs({ pool })}`),
  poolFloors: (pool: number) =>
    getJson<{ floors: LocationFloor[]; last_floor_id: number | null }>(`/api/desks/floors/${qs({ pool })}`),
  hours: (pool: number, day: string) =>
    getJson<DayHours>(`/api/desks/hours/${qs({ pool, day })}`),
  /** Days closed by blocks (public holidays, closures) in `from..to` (max
   *  400 days). With `pool`: system and department blocks; without: only
   *  system-wide ones. */
  closedDays: (from: string, to: string, pool?: number | null) =>
    getJson<{ days: string[] }>(`/api/desks/closed-days/${qs({ pool, from, to })}`),
  later: (id: number, until: string) =>
    mutate<Reservation>(`/api/desks/reservations/${id}/later/`, "POST", { until }),
  /** Free places of the same kind for the same hours that the holder may
   *  book (works for hidden holders too; the holder's id never leaves the API). */
  moveTargets: (id: number) => getJson<FreePlace[]>(`/api/desks/reservations/${id}/move-targets/`),
  move: (id: number, placeId: number) =>
    mutate<Reservation>(`/api/desks/reservations/${id}/move/`, "POST", { place_id: placeId }),
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
  /** Answer every open request of a batch; each date succeeds or fails on its own. */
  answerReleaseBatch: (batch: string, accept: boolean) =>
    mutate<{ done: number[]; failed: number[] }>("/api/desks/release-requests/answer-batch/", "POST", {
      batch,
      accept,
    }),
  withdrawRelease: (id: number) => mutate<unknown>(`/api/desks/release-requests/${id}/withdraw/`, "POST"),
  withdrawReleaseBatch: (batch: string) =>
    mutate<{ withdrawn: number }>("/api/desks/release-requests/withdraw-batch/", "POST", { batch }),
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
  roomPopularity: (pool: number) =>
    getJson<{ order: number[] }>(`/api/desks/room-popularity/${qs({ pool })}`),
  overview: (pool: number, day?: string) =>
    getJson<DepartmentDay>(`/api/desks/overview/${qs({ pool, day })}`),
  absences: () => getJson<Absence[]>("/api/desks/absences/"),
  createAbsence: (data: Pick<Absence, "start_date" | "end_date">) =>
    mutate<Absence & { released_count: number }>("/api/desks/absences/", "POST", data),
  deleteAbsence: (id: number) =>
    mutate<{ kept_bookings: number }>(`/api/desks/absences/${id}/`, "DELETE"),
  profile: () => getJson<{ hide_name: boolean }>("/api/desks/profile/"),
  favorites: () => getJson<{ place_ids: number[]; places: FavoritePlace[] }>("/api/desks/favorites/"),
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
  buildings: () => getAll<Building>("/api/desks/manage/buildings/"),
  createBuilding: (data: Pick<Building, "code" | "description" | "address">) =>
    mutate<Building>("/api/desks/manage/buildings/", "POST", data),
  updateBuilding: (id: number, data: Partial<Pick<Building, "code" | "description" | "address">>) =>
    mutate<Building>(`/api/desks/manage/buildings/${id}/`, "PATCH", data),
  deleteBuilding: (id: number) => mutate<void>(`/api/desks/manage/buildings/${id}/`, "DELETE"),
  // `all` includes deactivated rows (soft-deleted floors, rooms, places).
  floors: (all = false) => getAll<Floor>(`/api/desks/manage/floors/${all ? "?include_inactive=1" : ""}`),
  rooms: (all = false) => getAll<Room>(`/api/desks/manage/rooms/${all ? "?include_inactive=1" : ""}`),
  places: (all = false) => getAll<Place>(`/api/desks/manage/places/${all ? "?include_inactive=1" : ""}`),
  /** Saves the plan shapes (`plan`, app admins only) and/or place symbols
   *  (`symbols`: place id → symbol or null; department admins only their own
   *  places) in one all-or-nothing request. */
  saveFloorPlan: (
    floorId: number,
    data: { plan?: PlanJson; symbols?: Record<number, PlanSymbol | null> },
  ) => mutate<{ plan: PlanJson }>(`/api/desks/manage/floors/${floorId}/plan/`, "PUT", data),
  floor: (floorId: number) => getJson<Floor>(`/api/desks/manage/floors/${floorId}/`),
  updateFloor: (floorId: number, data: Partial<Pick<Floor, "scale_px_per_m" | "name_de" | "name_en" | "building" | "position" | "is_active">>) =>
    mutate<Floor>(`/api/desks/manage/floors/${floorId}/`, "PATCH", data),
  /** The floor's drawing template as a blob (admins only; use as object URL). */
  floorTemplate: (floorId: number) => getBlob(`/api/desks/manage/floors/${floorId}/template/`),
  uploadFloorTemplate: (floorId: number, file: File) =>
    postFile<Floor>(`/api/desks/manage/floors/${floorId}/template/`, "file", file),
  createFloor: (data: Pick<Floor, "name_de" | "name_en" | "building" | "position">) =>
    mutate<Floor>("/api/desks/manage/floors/", "POST", data),
  deleteFloor: (id: number) => mutate<void>(`/api/desks/manage/floors/${id}/`, "DELETE"),
  /** App admins only; `pool` is the room's (optional) default department. */
  createRoom: (data: Pick<Room, "floor" | "pool" | "name_de" | "name_en" | "kind">) =>
    mutate<Room>("/api/desks/manage/rooms/", "POST", data),
  updateRoom: (id: number, data: Partial<Pick<Room, "floor" | "name_de" | "name_en" | "kind" | "is_active" | "access_groups">>) =>
    mutate<Room>(`/api/desks/manage/rooms/${id}/`, "PATCH", data),
  /** One room, also a deactivated one (404 once it is removed for good). */
  room: (id: number) => getJson<Room>(`/api/desks/manage/rooms/${id}/`),
  deleteRoom: (id: number) => mutate<void>(`/api/desks/manage/rooms/${id}/`, "DELETE"),
  createFeature: (data: FeatureInput) =>
    mutate<Feature>("/api/desks/manage/features/", "POST", data),
  updateFeature: (id: number, data: Partial<FeatureInput>) =>
    mutate<Feature>(`/api/desks/manage/features/${id}/`, "PATCH", data),
  /** Gallery endpoints of one saved piece of equipment, for `applyGalleryPlan`. */
  featureGalleryOps: (featureId: number): GalleryOps => ({
    upload: (file) =>
      uploadGalleryImage(`/api/desks/manage/features/${featureId}/images/`, file),
    remove: (imageId) =>
      mutate<void>(`/api/desks/manage/features/${featureId}/images/${imageId}/`, "DELETE"),
    reorder: (ids) =>
      mutate<FeatureImage[]>(`/api/desks/manage/features/${featureId}/images/reorder/`, "POST", {
        order: ids,
      }),
  }),
  /** Create several rooms of a floor from a name range (or preview with `dry_run`). */
  batchRooms: (data: RoomBatchRequest) =>
    mutate<BatchResult>("/api/desks/manage/rooms/batch/", "POST", data),
  /** Create `count` places in each room (or preview with `dry_run`). */
  batchPlaces: (data: PlaceBatchRequest) =>
    mutate<BatchResult>("/api/desks/manage/places/batch/", "POST", data),
  /** The next free place names of a room, following the campus naming pattern. */
  nameSuggestions: (room: number, count: number) =>
    getJson<{ names: string[] }>(`/api/desks/manage/places/name-suggestions/${qs({ room, count })}`),
  /** Assign rooms/places to a department and/or set their access/admin groups. */
  assign: (data: AssignRequest) =>
    mutate<{ places_changed: number }>("/api/desks/manage/assign/", "POST", data),
  /** Add / remove access groups of rooms and places in bulk. */
  applyPlaceGroups: (data: PlaceGroupsRequest) =>
    mutate<{ places_changed: number }>("/api/desks/manage/place-groups/", "POST", data),
  adminSetting: () => getJson<DeskAdminSetting>("/api/desks/manage/admin-setting/"),
  saveAdminSetting: (data: DeskAdminSetting) =>
    mutate<DeskAdminSetting>("/api/desks/manage/admin-setting/", "PUT", data),
  deleteFeature: (id: number) => mutate<void>(`/api/desks/manage/features/${id}/`, "DELETE"),
  createPlace: (data: PlaceInput) => mutate<Place>("/api/desks/manage/places/", "POST", data),
  updatePlace: (placeId: number, data: Partial<PlaceInput> & Partial<Pick<Place, "plan_symbol">>) =>
    mutate<Place>(`/api/desks/manage/places/${placeId}/`, "PATCH", data),
  /** One place, also a retired one (404 once it is removed for good). */
  place: (id: number) => getJson<Place>(`/api/desks/manage/places/${id}/`),
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
  createManageAbsence: (data: Pick<Absence, "user" | "start_date" | "end_date">) =>
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
