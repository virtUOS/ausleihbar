// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Shapes of the desksharing API (`/api/desks/…`, backend app `desksharing`).

export type PlaceKind = "desk" | "meeting_room";
export type RoomKind = "office" | "meeting";
export type ReservationStatus = "active" | "cancelled" | "released";
export type ReleaseReason =
  | ""
  | "no_show"
  | "absence"
  | "holder"
  | "admin"
  | "request"
  | "block"
  | "rights";
/** Per-hour state in the department overview. */
export type HourState = "free" | "closed" | "booked" | "checked_in" | "potentially_free";

export interface Feature {
  id: number;
  pool: number;
  name: string;
}

export interface PlaceBrief {
  id: number;
  name: string;
  room: string;
  floor: string;
  kind?: PlaceKind;
  building?: string;
  /** Department (pool) id; present on reservation places. */
  pool?: number;
}

/** Plan symbol position of a place, in plan coordinates. */
export interface PlanSymbol {
  x: number;
  y: number;
  rotation: number;
}

/** A bookable place as the admin API returns it. */
export interface Place {
  id: number;
  room: number;
  kind: PlaceKind;
  name: string;
  capacity: number | null;
  features: number[];
  access_groups: number[];
  is_special: boolean;
  fixed_owner: number | null;
  /** Admin API only (assigned on purpose; ignores the holder opt-out). */
  fixed_owner_name: string | null;
  plan_symbol: PlanSymbol | null;
  qr_token: string;
  is_active: boolean;
}

/** Writable part of a place (create / edit form). */
export interface PlaceInput {
  room: number;
  kind: PlaceKind;
  name: string;
  capacity: number | null;
  features: number[];
  access_groups: number[];
  is_special: boolean;
  fixed_owner: number | null;
  is_active: boolean;
}

export interface PersonChoice {
  id: number;
  name: string;
}
export interface AccessGroupChoice {
  id: number;
  name: string;
  /** Already an access group of the department itself. */
  in_pool: boolean;
}

export interface Room {
  id: number;
  floor: number;
  name: string;
  kind: RoomKind;
}

export interface Floor {
  id: number;
  pool: number;
  building: string;
  name: string;
  position: number;
  has_template: boolean;
  template_url: string | null;
  scale_px_per_m: number | null;
  plan: PlanJson;
}

export type PlanShapeType = "room" | "wall" | "door" | "label";
export interface PlanShape {
  id: string;
  type: PlanShapeType;
  points?: [number, number][];
  text?: string;
  room_id?: number | null;
}
export interface PlanJson {
  shapes: PlanShape[];
}

/** A place that is free for a requested time (`GET /api/desks/free/`). */
export interface FreePlace {
  id: number;
  name: string;
  kind: PlaceKind;
  capacity: number | null;
  room: string;
  floor: string;
  building: string;
  features: number[];
}

/** A place that is free from now on (`GET /api/desks/free-now/`). */
export interface FreeNowPlace extends FreePlace {
  /** ISO time of the next reservation / closing; null when open-ended. */
  free_until: string | null;
}

export interface Reservation {
  id: number;
  place: PlaceBrief;
  day: string;
  start_hour: number;
  end_hour: number;
  start: string;
  end: string;
  group: string;
  status: ReservationStatus;
  comment: string;
  /** null = hidden holder ("Person (verborgen)"). */
  holder_id: number | null;
  booked_by_id: number | null;
  checked_in_at: string | null;
  late_until: string | null;
  potentially_free_at: string | null;
  release_reason: ReleaseReason;
  series_id: number | null;
}

export interface ManageReservation extends Reservation {
  holder_name: string | null;
}

/** Non-blocking booking warning, e.g. "absent". */
export type BookWarning = string;

/** 409 body of a booking conflict (`ApiError.data`). */
export interface BookConflict {
  code: string;
  detail: string;
  alternatives: PlaceBrief[];
}

/** `GET /api/desks/hours/`: open interval of a day and blocked grid hours. */
export interface DayHours {
  open: [number, number] | null;
  closed: number[];
  /** Current Berlin hour when the day is today (earlier hours are past). */
  min_hour: number | null;
  /** Last bookable day (booking horizon); null = unlimited. */
  max_day: string | null;
  /** Weekdays without business hours (0 = Monday). */
  closed_weekdays: number[];
}

/** Compact description of a reservation inside a request. */
export interface RequestBrief {
  id: number | null;
  place: PlaceBrief;
  day: string;
  start_hour: number;
  end_hour: number;
}
export interface DeskRequest {
  id: number;
  type: "swap" | "release";
  status: string;
  created_at: string;
  own?: RequestBrief;
  other?: RequestBrief;
  other_holder_name?: string | null;
  show_name?: boolean;
  requester_name?: string | null;
}
export interface MyRequests {
  incoming: DeskRequest[];
  outgoing: DeskRequest[];
}
export interface BookResult {
  reservations: Reservation[];
  warnings: BookWarning[];
}

export interface BookRequest {
  place_ids: number[];
  day: string;
  last_day?: string | null;
  start_hour: number;
  end_hour: number;
  comment?: string;
  holder_id?: number | null;
}

export interface Series {
  id: number;
  place: PlaceBrief;
  /** 0 = Monday … 6 = Sunday. */
  weekdays: number[];
  start_hour: number;
  end_hour: number;
  valid_from: string;
  valid_until: string;
  comment: string;
  holder_id: number | null;
  booked_by_id: number | null;
  cancelled_at: string | null;
}

export interface SeriesConflict {
  day: string;
  code: string;
  alternatives: PlaceBrief[];
}
export interface SeriesResult {
  series: Series;
  created: Reservation[];
  conflicts: SeriesConflict[];
}

export interface SeriesRequest {
  place_id: number;
  weekdays: number[];
  start_hour: number;
  end_hour: number;
  valid_from: string;
  valid_until: string;
  comment?: string;
  holder_id?: number | null;
}

export type ScanAction = "checked_in" | "booked" | "not_allowed" | "taken";
export interface ScanResult {
  action: ScanAction;
  /** For `not_allowed`: no_rights | inactive | closed | outside_hours | unknown_token | horizon. */
  reason: string;
  reservation: Reservation | null;
  next_free_until: string | null;
}

export type DeskAction = "later" | "release";

/** Status of one place in the department overview. */
export interface PlaceStatus {
  state: HourState | string;
  until?: string | null;
  [key: string]: unknown;
}

export interface OverviewHour {
  hour: number;
  state: HourState;
  reservation_id: number | null;
  /** null = no holder; "Person (verborgen)" is a label, not null. */
  holder: string | null;
  mine: boolean;
}
export interface OverviewPlace {
  id: number;
  name: string;
  kind: PlaceKind;
  room_id: number;
  capacity: number | null;
  is_special: boolean;
  plan_symbol: PlanSymbol | null;
  features: number[];
  fixed: boolean;
  hours: OverviewHour[];
  now: PlaceStatus | null;
}
export interface OverviewFloor {
  id: number;
  name: string;
  building: string;
  plan: PlanJson;
  rooms: { id: number; name: string; kind: RoomKind }[];
  places: OverviewPlace[];
}
export interface MeetingRoomDay {
  id: number;
  name: string;
  room: string;
  floor: string;
  capacity: number | null;
  reservations: {
    id: number;
    start_hour: number;
    end_hour: number;
    state: HourState;
    holder: string | null;
    comment: string;
    mine: boolean;
  }[];
}
export interface DepartmentDay {
  pool: number;
  day: string;
  open_hours: [number, number] | null;
  closed_hours: number[];
  floors: OverviewFloor[];
  meeting_rooms: MeetingRoomDay[];
}

export type AbsenceKind = "vacation" | "absent";
export interface Absence {
  id: number;
  user: number;
  user_name: string;
  start_date: string;
  end_date: string;
  kind: AbsenceKind;
  created_at: string;
}

/** Business hours per weekday ("0" = Monday): [start, end] or null (closed). */
export type BusinessHours = Record<string, [number, number] | null>;
export interface DeskSettings {
  pool: number;
  enabled: boolean;
  assistant_group: number | null;
  business_hours: BusinessHours;
  desk_grace_normal_min: number;
  desk_grace_short_min: number;
  desk_scarcity_free_below: number;
  room_grace_normal_min: number;
  room_grace_short_min: number;
  room_scarcity_free_below: number;
  retention_days: number;
}

/** Usage figures of a group of places (statistics). */
export interface Figures {
  [key: string]: number;
}
/** Occupancy percent by weekday ("0" = Monday) and hour. */
export type Heatmap = Record<string, Record<string, number>>;
export interface StatFigures {
  booked_h: number;
  checked_in_h: number;
  no_show_count: number;
  no_show_h: number;
  released_h: number;
  rebooked_after_release_h: number;
  assigned_h: number;
  heatmap: Heatmap;
}
export interface DeskStats {
  quota: Record<PlaceKind, StatFigures>;
  special: ({ place: { id: number; name: string; kind: PlaceKind } } & StatFigures)[];
}

export type NotificationEvent =
  | "daily_summary"
  | "grace_nudge"
  | "released_no_show"
  | "released_other"
  | "booked_for_you"
  | "admin_changed"
  | "swap_request"
  | "swap_answer"
  | "release_request"
  | "release_answer"
  | "series_extension_due";
export type NotificationChannel = "mail" | "off";
export type NotificationPreferences = Record<string, NotificationChannel>;
