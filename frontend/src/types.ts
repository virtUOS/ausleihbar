// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Types mirroring the catalog API responses.

export type LendingType = "hours" | "days";

export interface WhoAmI {
  authenticated: boolean;
  username?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  subject?: string;
  is_staff?: boolean;
  is_lender?: boolean;
  /** Canonical content language and the full set (issue #6, per-deployment). */
  content_default_language?: string;
  content_languages?: string[];
  /** Whether the editor may offer machine-translation pre-fill (#6 Phase 4). */
  content_translation_enabled?: boolean;
  /** Whether the AI attribute-suggestion feature is configured and available. */
  ai_enabled?: boolean;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Weekday key ("mon"…"sun") → list of [from, to] "HH:MM" pairs. */
export type OpeningHours = Record<string, [string, string][]>;

/** Per-language editable variants of a translated field (issue #6). The bare
 *  field (e.g. `title`) stays for reading — it follows the active UI language —
 *  while admin forms edit these `*_de` / `*_en` variants. A null variant means
 *  "not translated" and falls back to German in the shop. */
export type Translations<K extends string> = {
  [P in `${K}_de` | `${K}_en`]: string | null;
};

export interface ResourcePool
  extends Translations<"name">,
    Translations<"description">,
    Translations<"address">,
    Translations<"room">,
    Translations<"directions">,
    Translations<"email_note"> {
  id: number;
  name: string;
  pool_id: string;
  description: string;
  address: string;
  room: string;
  image: string | null;
  directions: string;
  phone: string;
  email: string;
  email_note: string;
  notify_on_defect: boolean;
  notify_on_cancellation: boolean;
  require_booking_note: boolean;
  opening_hours: OpeningHours;
  closed_weekdays: number[];
  lead_time_hours: number;
  max_booking_months: number;
  default_min_days: number | null;
  default_max_days: number | null;
  default_min_hours: number | null;
  default_max_hours: number | null;
  is_active: boolean;
  resource_count: number;
  /** Access groups that grant access to this pool (read-only; edited on the
   *  access-group side). Empty = visible to everyone signed in. */
  access_groups?: { id: number; name: string }[];
  /** Palette key into `poolAccent()` (#16); blank/unknown renders neutral. */
  accent_color: string;
}

/** Writable fields when creating/updating a pool. The bare translated fields
 *  are edited via their `*_de` / `*_en` variants, so they're excluded here. */
export type ResourcePoolInput = Omit<
  ResourcePool,
  | "id"
  | "resource_count"
  | "name"
  | "description"
  | "address"
  | "room"
  | "directions"
  | "email_note"
>;

export const ATTRIBUTE_TYPES = [
  "short_text",
  "long_text",
  "date",
  "time",
  "number",
  "url",
  "media",
  "image",
  "pdf",
] as const;

export type AttributeType = (typeof ATTRIBUTE_TYPES)[number];

/** A user-entered text that may be a plain string (same in every language,
 *  backward compatible) or a `{ lang: text }` map. Canonically defined in
 *  `contentLang.ts`; re-exported here for convenience. */
import type { LocalizedText } from "@basicbar/ui";
export type { LocalizedText } from "@basicbar/ui";

export interface AttributeDef {
  key: string;
  /** Attribute label shown to borrowers; translatable per language (#6). */
  label: LocalizedText;
  type: AttributeType;
  default: unknown;
  visible: boolean;
  required: boolean;
}

export interface ProductType
  extends Translations<"name">,
    Translations<"description"> {
  id: number;
  name: string;
  description: string;
  attribute_schema: AttributeDef[];
  product_count: number;
}

export type ProductTypeInput = Omit<
  ProductType,
  "id" | "product_count" | "name" | "description"
>;

export interface ManageProduct
  extends Translations<"title">,
    Translations<"description">,
    Translations<"short_description">,
    Translations<"return_info"> {
  id: number;
  title: string;
  description: string;
  short_description: string;
  return_info: string;
  /** Cover (first gallery image); managed via the images endpoints, read-only. */
  image: string | null;
  images: ProductImage[];
  product_type: number;
  product_type_name: string;
  lending_type: "hours" | "days";
  min_duration: number | null;
  max_duration: number | null;
  min_gap: number;
  missing_notice_lead: number;
  attributes: Record<string, unknown>;
  categories: number[];
  resource_count: number;
}

export type ManageProductInput = Omit<
  ManageProduct,
  | "id"
  | "product_type_name"
  | "resource_count"
  | "image"
  | "images"
  | "title"
  | "description"
  | "short_description"
  | "return_info"
>;

export interface ManageCategory
  extends Translations<"title">,
    Translations<"description"> {
  id: number;
  title: string;
  description: string;
  image: string | null;
  products: number[];
  sections: number[];
  product_count: number;
  position: number;
}

export type ManageCategoryInput = Omit<
  ManageCategory,
  "id" | "product_count" | "position" | "title" | "description"
>;

export interface ManageSection
  extends Translations<"title">,
    Translations<"description"> {
  id: number;
  title: string;
  description: string;
  image: string | null;
  categories: number[];
  sets: number[];
  category_count: number;
  position: number;
}

export type ManageSectionInput = Omit<
  ManageSection,
  "id" | "category_count" | "position" | "title" | "description"
>;

export interface ManagedPoolMembership {
  id: number;
  resource_pool: number;
  pool_name: string;
  role: string;
}

export interface UserGroupBrief {
  id: number;
  name: string;
}

export interface Strike {
  id: number;
  reason: string;
  issued_by: string | null;
  created_at: string;
  expires_at: string;
  is_active: boolean;
}

export interface ManageUser {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_admin: boolean;
  /** Admin rights come from the IdP admin group → not editable in-app. */
  admin_via_oidc: boolean;
  is_lender: boolean;
  is_active: boolean;
  managed_pools: ManagedPoolMembership[];
  groups: UserGroupBrief[];
  strikes: Strike[];
  active_strikes: number;
  is_blocked: boolean;
  blocked_until: string | null;
  blocked_permanently: boolean;
  verified_at: string | null;
  date_joined: string;
  last_login: string | null;
}

export interface StrikeThreshold {
  count: number;
  block_days: number;
}

export interface StrikeSetting {
  strike_expiry_days: number;
  thresholds: StrikeThreshold[];
}

export interface AccessGroup {
  id: number;
  name: string;
  description: string;
  claim_key: string;
  claim_values: string[];
  pools: number[];
  pool_names: string[];
  member_count: number;
}

export type AccessGroupInput = Omit<
  AccessGroup,
  "id" | "pool_names" | "member_count"
>;

export interface ManageSet
  extends Translations<"name">,
    Translations<"description"> {
  id: number;
  name: string;
  description: string;
  resource_pool: number | null;
  pool_name: string | null;
  products: number[];
  product_count: number;
}

export type ManageSetInput = Omit<
  ManageSet,
  "id" | "product_count" | "pool_name" | "name" | "description"
>;

export const RESOURCE_STATUSES = [
  "available",
  "blocked",
  "defective",
  "retired",
] as const;

export type ResourceStatus = (typeof RESOURCE_STATUSES)[number];

export interface ManageResource {
  id: number;
  product: number;
  product_title: string;
  resource_pool: number;
  pool_name: string;
  inventory_number: string;
  qr_code_id: string;
  status: ResourceStatus;
  defect_note: string;
  storage_location: string;
  procurement_date: string | null;
  warranty_end: string | null;
  value: string | null;
  procuring_institution: string;
  owning_institution: string;
  condition_rating: number;
  condition_note: string;
}

export type ManageResourceInput = Omit<
  ManageResource,
  "id" | "product_title" | "pool_name"
>;

export interface ResourceDefectRecord {
  id: number;
  note: string;
  reported_at: string;
  resolved_at: string | null;
}

export interface ResourceBookingHistory {
  booking_id: number;
  status: string;
  borrower: string;
  start: string | null;
  end: string | null;
}

export interface ResourceDetail extends ManageResource {
  defects: ResourceDefectRecord[];
  bookings: ResourceBookingHistory[];
}

export interface SectionListItem {
  id: number;
  title: string;
  description: string;
  image: string | null;
  category_count: number;
  product_count: number;
}

export interface ProductBrief {
  id: number;
  title: string;
  short_description: string;
  image: string | null;
  lending_type: LendingType;
  is_new?: boolean;
}

export interface FeaturedProducts {
  popular: ProductBrief[];
  newest: ProductBrief[];
}

export interface CategoryWithProducts {
  id: number;
  title: string;
  description: string;
  product_count: number;
  products: ProductBrief[];
}

export interface SectionDetail {
  id: number;
  title: string;
  description: string;
  image: string | null;
  categories: CategoryWithProducts[];
  sets: SetBrief[];
}

/** Shop search: matched products plus categories/sections (with their content). */
export interface SearchResults {
  sections: SectionDetail[];
  categories: CategoryWithProducts[];
  products: ProductBrief[];
}

export interface VisibleAttribute {
  key: string;
  label: string;
  type: string;
  value: unknown;
}

export interface PoolBrief {
  id: number;
  name: string;
  address: string;
  room: string;
  lead_time_hours: number;
  max_booking_months: number;
  /** Palette key into `poolAccent()` (#16); blank/unknown renders neutral. */
  accent_color: string;
}

export interface BlockDay {
  id: number;
  scope: string;
  reason: string;
  resource_pool: number | null;
  pool_name: string | null;
  start_date: string;
  end_date: string;
  is_holiday: boolean;
  created_at: string;
  // Only on the create response: how existing bookings were adjusted.
  adjusted?: { rescheduled: number; cancelled: number };
}

export interface BlockDayInput {
  resource_pool?: number | null;
  start_date: string;
  end_date?: string;
  reason?: string;
}

export interface HolidaySetting {
  country: string;
  subdivision: string;
  horizon_months: number;
  loaded?: number;
}

export interface CartSetting {
  hold_minutes: number;
}

export interface WelcomeSetting {
  text: string;
  logo: string | null;
}

export interface ShopSetting {
  show_popular: boolean;
  show_new_arrivals: boolean;
  new_product_days: number;
}

export interface NotificationSetting
  extends Translations<"reservation_intro">,
    Translations<"reservation_footer">,
    Translations<"rescheduled_note">,
    Translations<"cancellation_note">,
    Translations<"reminder_note">,
    Translations<"defect_note"> {
  reservation_intro: string;
  reservation_footer: string;
  rescheduled_note: string;
  cancellation_note: string;
  reminder_note: string;
  defect_note: string;
}

export interface ScanResource {
  id: number;
  inventory_number: string;
  product_title: string;
  pool_name: string;
  status: string;
  storage_location: string;
  defect_note: string;
}

export interface ScanResult {
  kind: "booking" | "resource";
  mode: "handout" | "return" | "idle";
  resource: ScanResource | null;
  booking: ManagedBooking | null;
}

export interface Branding {
  logo: string | null;
}

/** A footer link to a published content page. */
export interface PageLink {
  slug: string;
  title: string;
}

/** Public read of a content page (Imprint, Privacy, …). */
export interface PageDetail {
  slug: string;
  title: string;
  body: string;
  updated_at: string;
}

/** Admin view of a content page, including drafts. */
export interface CmsPage
  extends PageDetail,
    Translations<"title">,
    Translations<"body"> {
  id: number;
  is_published: boolean;
  show_in_footer: boolean;
  footer_order: number;
}

export type CmsPageInput = Omit<
  CmsPage,
  "id" | "updated_at" | "title" | "body" | "footer_order"
>;

export interface PoolCard {
  id: number;
  name: string;
  description: string;
  room: string;
  image: string | null;
  /** Palette key into `poolAccent()` (#16); blank/unknown renders neutral. */
  accent_color: string;
}

export interface WelcomeData {
  text: string;
  pools: PoolCard[];
}

/** Public pool info page: where & when to pick things up (concept §1.5). */
export interface PoolDetail {
  id: number;
  name: string;
  description: string;
  room: string;
  image: string | null;
  address: string;
  directions: string;
  phone: string;
  email: string;
  opening_hours: OpeningHours;
  closed_weekdays: number[];
  /** Palette key into `poolAccent()` (#16); blank/unknown renders neutral. */
  accent_color: string;
}

/** One category's slice of a pool's stock (#14); ``category: null`` is the
 *  trailing "Other" bucket for pool products in no category. */
export interface PoolProductGroup {
  category: { id: number; title: string } | null;
  products: ProductBrief[];
}

export interface TreeResource {
  id: number;
  inventory_number: string;
  status: string;
  booking_count: number;
}

export interface TreeProduct {
  id: number;
  title: string;
  booking_count: number;
  resources: TreeResource[];
}

export interface TreePool {
  id: number;
  name: string;
  products: TreeProduct[];
}

export interface LendingOverview {
  pools: TreePool[];
}

export interface ResourceBooking {
  code: string;
  borrower: string;
  borrower_name: string;
  status: string;
  start: string | null;
  end: string | null;
}

export interface ProductStat {
  id: number;
  title: string;
  lending_type: LendingType;
  bookings: number;
  booked_hours: number;
  prev_bookings: number;
  trend: number;
}

export interface ProductStatsResponse {
  from: string;
  to: string;
  products: ProductStat[];
  pools: { id: number; name: string }[];
}

export interface DefectRow {
  id: number;
  inventory_number: string;
  product_title: string;
  pool_name: string;
  status: string;
  defect_count: number;
  currently_defective: boolean;
  defect_note: string;
  defective_since: string | null;
  last_defect: string | null;
  gitlab_issue_url: string;
}

export interface RetentionSetting {
  enabled: boolean;
  retention_days: number;
  affected_now?: number;
}

/** One soft-deleted catalog item awaiting purge or restore (concept trash bin). */
export interface TrashItem {
  type: string;
  id: number;
  label: string;
  deleted_at: string;
  deleted_by: string | null;
  purge_at: string;
}

export interface TrashSetting {
  retention_days: number;
}

export interface ImportSummary {
  created: Record<string, number>;
  updated: Record<string, number>;
  media: number;
  dry_run?: boolean;
}

export interface DefectTicketConfig {
  id: number;
  name: string;
  defect_gitlab_url: string;
  defect_gitlab_token_set: boolean;
}

export interface DefectProductStat {
  id: number;
  title: string;
  incidents: number;
  defective_resources: number;
  currently_defective: number;
}

export interface CapacityMetric {
  count: number;
  max: number | null;
}

export interface CapacityStats {
  resources: CapacityMetric;
  products: CapacityMetric;
  users: CapacityMetric;
}

export interface DefectStats {
  resources_total: number;
  currently_defective: number;
  ever_defective: number;
  incidents: number;
  products: DefectProductStat[];
}

export interface TimeseriesPoint {
  start: string;
  bookings: number;
}

export interface ProductTimeseries {
  from: string;
  to: string;
  bucket: "day" | "week" | "month";
  series: TimeseriesPoint[];
}

export interface Availability {
  total: number;
  available: number;
  start: string;
  end: string;
}

export interface HourSlot {
  start: string;
  end: string;
  label: string;
  available: number;
  total: number;
}

export interface HourlyAvailability {
  date: string;
  slots: HourSlot[];
  min_hours: number | null;
  max_hours: number | null;
}

export interface HourlyCalendarDay {
  date: string;
  booked_pct: number | null;
  closed: boolean;
}

export interface DayAvailability {
  date: string; // YYYY-MM-DD
  available: number;
  total: number;
  closed: boolean; // pool closed that day (block / closed weekday)
}

export interface BookingItem {
  id: number;
  product: number;
  product_title: string;
  inventory_number: string;
  qr_code_id: string;
  pool: string;
  pool_id?: number;
  /** Palette key into `poolAccent()` (#16); blank/unknown renders neutral. */
  accent_color: string;
  image?: string | null;
  resource: number;
  resource_status: string;
  defect_note: string;
  lending_type: LendingType;
  // Lender-only return guidance (present on managed bookings only).
  return_info?: string;
  start: string | null;
  end: string | null;
  handed_out_at: string | null;
  returned_at: string | null;
}

export interface HandoutResource {
  id: number;
  qr_code_id: string;
  inventory_number: string;
  status: string;
  product: number;
  product_title: string;
  pool_id: number;
  pool_name: string;
}

export interface BookingGroupItem {
  id: number;
  product: number;
  product_title: string;
  inventory_number: string;
  image?: string | null;
  /** Palette key into `poolAccent()` (#16); blank/unknown renders neutral. */
  accent_color: string;
}

export interface BookingPeriod {
  start: string | null;
  end: string | null;
  lending_type: LendingType;
  items: BookingGroupItem[];
}

export interface BookingGroup {
  pool_id: number;
  pool: string;
  room: string;
  periods: BookingPeriod[];
}

export interface Booking {
  id: number;
  code: string;
  status: string;
  note: string;
  expires_at: string | null;
  created_at: string;
  items: BookingItem[];
  groups: BookingGroup[];
  has_strike?: boolean;
  strike_reason?: string | null;
  note_required?: boolean;
}

export interface BookingReminder {
  id: number;
  sent_at: string;
  overdue_pickups: number;
  overdue_returns: number;
}

export interface ManagedBooking extends Booking {
  borrower: string;
  borrower_id: number;
  borrower_name: string;
  reminders: BookingReminder[];
}

/** Read-only borrower profile shown in the lending desk (lenders + admins). */
export interface BorrowerProfile {
  id: number;
  username: string;
  email: string;
  full_name: string;
  strikes: Strike[];
  active_strikes: number;
  is_blocked: boolean;
  blocked_until: string | null;
  blocked_permanently: boolean;
  date_joined: string;
}

export interface WalkinPool {
  id: number;
  name: string;
  room: string;
}

export interface WalkinProduct {
  id: number;
  title: string;
  lending_type: LendingType;
}

export interface WalkinResource {
  id: number;
  inventory_number: string;
  conflict: boolean;
}

export interface BorrowerCandidate {
  id: number;
  username: string;
  full_name: string;
  email: string;
  is_blocked: boolean;
}

export interface ManageCalendarDay {
  date: string;
  pickups: number;
  returns: number;
}

export interface DayOverview {
  date: string;
  to_confirm: ManagedBooking[];
  pickups: ManagedBooking[];
  returns: ManagedBooking[];
  overdue: ManagedBooking[];
}

export interface ProductImage {
  id: number;
  image: string;
  position: number;
}

export interface ProductDetail {
  id: number;
  title: string;
  description: string;
  short_description: string;
  image: string | null;
  images: ProductImage[];
  lending_type: LendingType;
  min_duration: number | null;
  max_duration: number | null;
  /** Max lending duration (lending-type unit) incl. inherited pool default;
   *  null = no limit. */
  effective_max_duration: number | null;
  product_type_name: string;
  visible_attributes: VisibleAttribute[];
  pools: PoolBrief[];
  sets: { id: number; name: string }[];
  is_favorite: boolean;
}

export interface SetBrief {
  id: number;
  name: string;
  product_count: number;
}

export interface SetDetail {
  id: number;
  name: string;
  description: string;
  products: ProductBrief[];
  lending_type: LendingType;
  min_duration: number | null;
  max_duration: number | null;
  pool: PoolBrief | null;
}

export interface SetAvailability {
  available: number;
  products: { id: number; title: string; total: number; available: number }[];
  scarcest: string | null;
}
