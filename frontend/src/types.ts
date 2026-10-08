// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Types mirroring the catalog API responses.

export type LendingType = "hours" | "days";

/** One pool's lending-duration range in a product's unit (#109). */
export interface PoolDurationLimit {
  pool_id: number;
  pool_name: string;
  min: number | null;
  max: number | null;
}

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
  /** Saved shop language used for this user's notification emails (#25). */
  language?: string;
  /** Admins assigned as lenders: their (active) pools — the default
   *  lending-area scope behind the "My pools | All pools" switch. null for
   *  everyone else (no switch). */
  lending_scope_pool_ids?: number[] | null;
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
  /** Language used for emails to this pool's contact and its lenders ("de"/"en"). */
  email_language: string;
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
  complementary_products: number[];
  /** Shop navigation categories (#78), any depth. */
  categories: number[];
  resource_count: number;
  /** Per pool holding a unit: its default min/max in the product's unit —
   *  what "inherit from pool" resolves to (#109). Read-only. */
  pool_duration_defaults?: PoolDurationLimit[];
}

/** AI category suggestion for a product (#98): an existing live category
 *  with its path ("Root › Child") and a short plain-text reason. */
export interface CategorySuggestion {
  id: number;
  path: string;
  reason: string;
}

export type ManageProductInput = Omit<
  ManageProduct,
  | "id"
  | "product_type_name"
  | "resource_count"
  | "pool_duration_defaults"
  | "image"
  | "images"
  | "title"
  | "description"
  | "short_description"
  | "return_info"
>;

export interface ManageSection
  extends Translations<"title">,
    Translations<"description"> {
  id: number;
  title: string;
  description: string;
  image: string | null;
  /** Top-level categories (shop navigation, #78), in the saved order. */
  categories: number[];
  sets: number[];
  category_count: number;
  position: number;
}

export type ManageSectionInput = Omit<
  ManageSection,
  "id" | "category_count" | "position" | "title" | "description"
>;

/** A category row of `GET /api/manage/categories/` (flat, tree pre-order). */
export interface ManageCategory
  extends Translations<"name">,
    Translations<"description"> {
  id: number;
  name: string;
  description: string;
  image: string | null;
  parent: number | null;
  position: number;
  /** 0 = top-level. */
  depth: number;
  /** Names from the root down to this category. */
  path: string[];
  sections: number[];
  /** Directly assigned products in shop order. */
  products: { id: number; title: string }[];
  product_order: number[];
  product_count: number;
  child_count: number;
}

/** Writable fields of a category (`image` goes via the image endpoint). */
export type ManageCategoryInput = Translations<"name"> &
  Translations<"description"> & {
    parent: number | null;
    sections: number[];
    product_order: number[];
  };

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

/** A lender (pool `manager` membership) as returned by
 *  `GET|PUT /api/manage/pools/<id>/lenders/`. */
export interface PoolLender {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
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

export interface ManageResource extends Partial<ResourceDurationInfo> {
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
  /** Own lending-duration limits in the product's unit; null = inherit (#109). */
  min_duration: number | null;
  max_duration: number | null;
}

/** Where an effective duration limit comes from (#109). */
export type DurationSource = "resource" | "product" | "pool" | "none";

/** Read-only effective/inherited limits the API adds to a resource (#109). */
export interface ResourceDurationInfo {
  lending_unit: LendingType;
  effective_min_duration: number | null;
  effective_min_duration_source: DurationSource;
  effective_max_duration: number | null;
  effective_max_duration_source: DurationSource;
  inherited_min_duration: number | null;
  inherited_min_duration_source: DurationSource;
  inherited_max_duration: number | null;
  inherited_max_duration_source: DurationSource;
}

export type ManageResourceInput = Omit<
  ManageResource,
  "id" | "product_title" | "pool_name" | keyof ResourceDurationInfo
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

/** A direct subcategory as a filter chip (section and category detail). */
export interface CategoryFilterChild {
  id: number;
  name: string;
  /** Visible products of its whole subtree, deduplicated. */
  product_count: number;
  /** Ids of those products (sorted) — filters the parent's product list. */
  product_ids: number[];
}

/** A category as a shop group (#78): its whole subtree's products, already
 *  ordered daily before hourly, then curated order (#19). */
export interface CategoryGroup {
  id: number;
  name: string;
  description: string;
  image: string | null;
  product_count: number;
  child_count: number;
  products: ProductBrief[];
}

/** A top-level category box on a section page, with its filter chips. */
export interface SectionCategoryGroup extends CategoryGroup {
  /** Direct shown subcategories in sibling order. */
  children: CategoryFilterChild[];
}

export interface SectionDetail {
  id: number;
  title: string;
  description: string;
  image: string | null;
  /** Top-level categories in the section's order. */
  categories: SectionCategoryGroup[];
  sets: SetBrief[];
}

/** A subcategory tile on a category page (no product list). */
export interface CategoryChild {
  id: number;
  name: string;
  description: string;
  image: string | null;
  /** Visible products of its whole subtree, deduplicated. */
  product_count: number;
  child_count: number;
  /** Ids of its subtree's visible products — filters the category's list. */
  product_ids: number[];
}

/** `GET /api/categories/<id>/` — a shop category page. */
export interface CategoryDetail extends CategoryGroup {
  parent: number | null;
  /** Root → direct parent, for the breadcrumbs. */
  ancestors: { id: number; name: string }[];
  /** Live sections of the root category, in section order. */
  sections: { id: number; title: string }[];
  children: CategoryChild[];
}

/** Shop search: matched products plus categories/sections (with their content). */
export interface SearchResults {
  sections: SectionDetail[];
  /** Matched categories at any depth; `path` = ancestors root → parent. */
  categories: (CategoryGroup & { path: { id: number; name: string }[] })[];
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
  /** Daily time ("HH:MM:SS") at which held partial confirmations of
   *  multi-pool orders are collected and mailed. */
  confirmation_send_time: string;
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

/** One top-level category's slice of a pool's stock (#14, #78). ``category``
 *  is null for the last group: products without a category ("Other"). */
export interface PoolProductGroup {
  category: { id: number; name: string } | null;
  products: ProductBrief[];
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
  /** Legacy entries turned into the current structure (old archives'
   *  categories or product-type navigation mapped onto categories). */
  converted?: Record<string, number>;
  media: number;
  /** Storage names of rich-text images the import rejected as invalid (#68);
   *  missing in responses from older backends. */
  skipped_media?: string[];
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

/** The reservation's pickup location, shown on the borrower's booking cards (#37). */
export interface BookingPool {
  id: number;
  name: string;
  room: string;
  address: string;
  accent_color: string;
  opening_hours: OpeningHours;
  closed_weekdays: number[];
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
  pool?: BookingPool | null;
}

export interface BookingReminder {
  id: number;
  sent_at: string;
  overdue_pickups: number;
  overdue_returns: number;
}

export interface ManagedBooking extends Booking {
  /** Walk-in handed out beyond the duration limits on purpose (#109). */
  duration_override?: boolean;
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
  /** Effective limits in the chosen pool (widest over its units, #109). */
  effective_min_duration: number | null;
  effective_max_duration: number | null;
}

export interface WalkinResource {
  id: number;
  inventory_number: string;
  conflict: boolean;
  effective_min_duration: number | null;
  effective_max_duration: number | null;
}

/** One offending item of a walk-in refused for its duration (400, #109). */
export interface WalkinDurationViolation {
  product: number;
  title: string;
  lending_type: LendingType;
  requested: number;
  min: number | null;
  max: number | null;
  resource: string | null;
  pools: PoolDurationLimit[];
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

export interface DayStats {
  pickups: { open: number; done: number };
  returns: { open: number; done: number };
  overdue: number;
  to_confirm: number;
  lent_out: number;
}

export interface DayOverview {
  date: string;
  stats: DayStats;
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
  /** Widest lending-duration range (lending-type unit) over the bookable
   *  units in the requester's eligible pools, with inheritance device →
   *  product → pool default (#109); null = no limit. */
  effective_min_duration: number | null;
  effective_max_duration: number | null;
  /** Each eligible pool's range; when they differ, the page lists them. */
  duration_limits_by_pool: PoolDurationLimit[];
  product_type_name: string;
  visible_attributes: VisibleAttribute[];
  pools: PoolBrief[];
  sets: { id: number; name: string }[];
  is_favorite: boolean;
  complementary_products: {
    id: number;
    title: string;
    short_description: string;
    /** Cover image URL (thumbnail), or null → emoji fallback. */
    image: string | null;
    product_type_name: string;
    pools: PoolBrief[];
  }[];
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
  /** Effective limits of the most restricted product in the set's pool. */
  min_duration: number | null;
  max_duration: number | null;
  pool: PoolBrief | null;
}

export interface SetAvailability {
  available: number;
  products: { id: number; title: string; total: number; available: number }[];
  scarcest: string | null;
}

export interface PoolAvailability {
  pool_id: number;
  name: string;
  accent_color: string;
  position: number;
  total: number;
  available: number;
}
