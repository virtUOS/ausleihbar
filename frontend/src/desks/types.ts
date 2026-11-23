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
  | "rights"
  | "display";
/** Per-hour state in the department overview. */
export type HourState = "free" | "closed" | "booked" | "checked_in" | "potentially_free";

/** A picture of a piece of equipment (lowest position = cover). */
export interface FeatureImage {
  id: number;
  image: string;
  position: number;
}

/** Campus-wide equipment (shared by all departments). */
export interface Feature {
  id: number;
  name: string;
  name_de: string;
  name_en: string | null;
  description: string;
  description_de: string;
  description_en: string | null;
  images: FeatureImage[];
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
  /** The place's department (null: unassigned, not bookable). */
  pool: number | null;
  /** The department deliberately differs from the room's. */
  pool_overridden: boolean;
  kind: PlaceKind;
  name: string;
  name_de: string;
  name_en: string | null;
  capacity: number | null;
  features: number[];
  access_groups: number[];
  /** The place has groups of its own (otherwise it follows its room's). */
  groups_overridden: boolean;
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
  name_de: string;
  name_en: string | null;
  capacity: number | null;
  features: number[];
  access_groups: number[];
  /** false: follow the room's groups (posted groups are ignored); true: own groups. */
  groups_overridden?: boolean;
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
  /** The room's default department, handed down to its places (null: unassigned). */
  pool: number | null;
  name: string;
  name_de: string;
  name_en: string | null;
  kind: RoomKind;
  /** Default access groups ("Who may book") of the room's places that follow it. */
  access_groups: number[];
  is_active: boolean;
}

/** A campus building (`/api/desks/manage/buildings/`), shared by all departments. */
export interface Building {
  id: number;
  /** Short code as people say it ("15", "AX"). */
  code: string;
  description: string;
  address: string;
  /** The viewer may change or delete it (app admins). */
  editable: boolean;
}

/** A department floor for the location picker (`GET /api/desks/floors/`). */
export interface LocationFloor {
  id: number;
  name: string;
  position: number;
  building_id: number | null;
  /** The building's code ("" without one). */
  building: string;
  building_description: string;
}

/** A campus-wide floor (not tied to a department). */
export interface Floor {
  id: number;
  /** Building id (null: none). */
  building: number | null;
  building_code: string;
  building_description: string;
  name: string;
  name_de: string;
  name_en: string | null;
  position: number;
  is_active: boolean;
  has_template: boolean;
  template_url: string | null;
  scale_px_per_m: number | null;
  plan: PlanJson;
}

export type PlanShapeType = "room" | "wall" | "door" | "window" | "label";
/** Symbol drawn in the middle of a room shape. */
export type RoomIcon = "stairs" | "wc_men" | "wc_women" | "wc_all" | "wc_accessible";
/** Where a door/window sits: edge `edge` (point i → point i+1 mod n) of the
 *  room shape `shape`, centre at `t` (0–1) along it. */
export interface WallRef {
  shape: string;
  edge: number;
  t: number;
}
export interface PlanShape {
  id: string;
  type: PlanShapeType;
  /** Old doors, rooms, walls and labels; wall-bound doors and windows have none. */
  points?: [number, number][];
  text?: string;
  room_id?: number | null;
  /** Room: draw the outline as walls (rooms of the newer tools). */
  outline?: "wall";
  /** Room: symbol in the middle (stairs, toilets). */
  icon?: RoomIcon | null;
  /** Door (new form) / window: the room edge it sits in. */
  wall?: WallRef;
  /** Door/window width in plan units. */
  width?: number;
  /** Door: hinge at the edge's later end instead of the earlier one. */
  flip_hinge?: boolean;
  /** Door: opens to the outside of its room instead of into it. */
  flip_swing?: boolean;
}
export interface PlanJson {
  shapes: PlanShape[];
}

/** A place that is free for a requested time (e.g. move targets). */
export interface FreePlace {
  id: number;
  name: string;
  kind: PlaceKind;
  capacity: number | null;
  room: string;
  floor: string;
  floor_id: number;
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
  /** Names of others in the room (null = hidden person); only in the "mine" list. */
  neighbours?: (string | null)[];
}

export interface ManageReservation extends Reservation {
  holder_name: string | null;
  /** The viewer's own reservation (managed under "My reservations"). */
  mine: boolean;
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
  /** Release requests sent together share a batch (null for single/legacy ones). */
  batch?: string | null;
  /** The hours asked for (release requests of a batch); null = the rest of `own`/`other`. */
  wanted?: { day: string; start_hour: number; end_hour: number } | null;
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

/** `GET /api/desks/window/`: the department's booking window and how much
 *  of the advance quota the person (or `holder`) has used. */
export interface BookingWindow {
  today: string;
  /** Last day of the open window (no quantity limit up to here). */
  open_until: string;
  /** From this day on the next cycle is open too. */
  transition_from: string;
  /** End of the next cycle (the window during the transition). */
  next_open_until: string;
  /** Last day that can be booked at all (advance quota beyond `open_until`). */
  advance_until: string;
  advance_days: number;
  advance_places: number;
  advance_days_used: number;
  advance_days_left: number;
}

/** `GET /api/desks/places/<id>/days/`: one day of a place. */
export interface PlaceDay {
  day: string;
  /** The department is closed (closed weekday or a block). */
  closed: boolean;
  /** Grid hours taken by others (or fixed for someone else). */
  taken: number[];
}

/** `GET /api/desks/availability/`: a bookable place over several days. */
export interface DaysAvailability {
  id: number;
  name: string;
  floor_id: number;
  room: string;
  /** Room, building code and floor as one line. */
  where: string;
  features: number[];
  /** Days with one other reservation in the hours (can be requested). */
  taken_days: string[];
  /** Days that can't be booked or requested (closed, fixed, own overlap…). */
  unavailable_days: string[];
}

export interface BookDaysRequest {
  place_ids: number[];
  days: string[];
  start_hour: number;
  end_hour: number;
  comment?: string;
  holder_id?: number | null;
  on_taken: "fail" | "request";
  show_name?: boolean;
}

/** `POST /api/desks/reservations/days/` (201). */
export interface BookDaysResult extends BookResult {
  requests: DeskRequest[];
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
  /** Release requests for taken dates (`on_taken: "request"`). */
  requests: DeskRequest[];
  warnings?: BookWarning[];
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
  /** "request": dates blocked by exactly one other booking are asked of
   *  their holders instead of becoming conflicts. */
  on_taken?: "conflict" | "request";
  show_name?: boolean;
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

/** Read-only context of a mail action token (`GET /api/desks/actions/context/`). */
export interface ActionContext {
  reservation: {
    id: number;
    place: string;
    room: string;
    floor: string;
    start: string;
    end: string;
    status: ReservationStatus;
    checked_in: boolean;
  };
  expired: boolean;
}

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
  /** The viewer may book it (hour selection in the overview). */
  bookable: boolean;
  hours: OverviewHour[];
  now: PlaceStatus | null;
}
export interface OverviewFloor {
  id: number;
  name: string;
  /** The building's code ("" without one). */
  building: string;
  position: number;
  building_id: number | null;
  building_description: string;
  building_address: string;
  plan: PlanJson;
  /** Plan units per metre; sizes the place symbols (null: unknown). */
  scale_px_per_m: number | null;
  rooms: { id: number; name: string; kind: RoomKind }[];
  places: OverviewPlace[];
}
export interface MeetingRoomDay {
  id: number;
  name: string;
  room: string;
  floor: string;
  floor_id: number;
  capacity: number | null;
  /** The viewer may book it (selection in the overview timeline). */
  bookable: boolean;
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
  /** Floor of the viewer's latest own booking in the department (preselected). */
  last_floor_id: number | null;
}

export interface Absence {
  id: number;
  user: number;
  user_name: string;
  start_date: string;
  end_date: string;
  /** Entered by the person themselves (else by an assistant / admin). */
  self_entered: boolean;
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
  /** Booking window (cycles) and advance quota. */
  cycle_months: number;
  transition_weeks: number;
  advance_months: number;
  advance_days: number;
  advance_places: number;
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

/** A favourite place with where it is (`GET /api/desks/favorites/`). */
export interface FavoritePlace {
  id: number;
  name: string;
  kind: PlaceKind;
  room: string;
  floor: string;
  building: string;
  pool: number;
  pool_name: string;
}

/** Result of a batch create (or its `dry_run` preview): names created / skipped as existing. */
export interface BatchResult {
  created: string[];
  skipped: string[];
}

export interface RoomBatchRequest {
  floor: number;
  prefix: string;
  start: string;
  end: string;
  pool?: number | null;
  kind?: RoomKind;
  dry_run?: boolean;
}

export interface PlaceBatchRequest {
  room_ids: number[];
  count: number;
  kind: PlaceKind;
  capacity?: number | null;
  dry_run?: boolean;
}

/** Assign rooms/places to a department (`pool: null` clears it). */
export interface AssignRequest {
  room_ids?: number[];
  place_ids?: number[];
  pool: number | null;
  /** Places of the given rooms follow the room's department again. */
  follow_room?: boolean;
  access_group_ids?: number[];
  admin_group_ids?: number[];
}

/** Bulk change of the access groups of rooms (their following places) and places. */
export interface PlaceGroupsRequest {
  room_ids: number[];
  place_ids: number[];
  add_ids: number[];
  remove_ids: number[];
  /** Selected places drop their own groups and follow their room again. */
  follow_room: boolean;
}

/** Campus-wide naming of new places. */
export interface DeskAdminSetting {
  place_name_pattern: "letter" | "number";
}
