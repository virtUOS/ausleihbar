// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Thin client for the catalog and booking API.
import type {
  AccessGroup,
  AccessGroupInput,
  AttributeDef,
  Availability,
  BlockDay,
  BlockDayInput,
  Booking,
  BorrowerProfile,
  DefectRow,
  DefectTicketConfig,
  ImportSummary,
  CapacityStats,
  DefectStats,
  FeaturedProducts,
  CartSetting,
  ShopSetting,
  NotificationSetting,
  HolidaySetting,
  WelcomeData,
  WelcomeSetting,
  LendingOverview,
  ProductStatsResponse,
  ProductTimeseries,
  ResourceBooking,
  BorrowerCandidate,
  HandoutResource,
  ScanResult,
  WalkinPool,
  WalkinProduct,
  WalkinResource,
  SetAvailability,
  SetBrief,
  SetDetail,
  Strike,
  RetentionSetting,
  StrikeSetting,
  TrashItem,
  TrashSetting,
  DayAvailability,
  DayOverview,
  HourlyAvailability,
  HourlyCalendarDay,
  ManageCalendarDay,
  ManagedBooking,
  Paginated,
  ManageCategory,
  ManageCategoryInput,
  ManageProduct,
  ManageProductInput,
  ManageResource,
  ManageResourceInput,
  ManageSection,
  ManageSectionInput,
  ManageSet,
  ManageSetInput,
  ManageUser,
  Branding,
  PageLink,
  PageDetail,
  CmsPage,
  CmsPageInput,
  PoolAvailability,
  PoolCard,
  PoolDetail,
  PoolProductGroup,
  ProductBrief,
  ProductDetail,
  ProductImage,
  ProductType,
  ProductTypeInput,
  ResourceDetail,
  ResourcePool,
  ResourcePoolInput,
  SearchResults,
  SectionDetail,
  SectionListItem,
} from "./types";
import i18n from "./i18n";

// Same-origin relative requests by default — correct for the released image,
// where Caddy proxies /api on the same domain as the SPA (no VITE_API_BASE_URL
// is ever set at its GHCR build time). Falls back to the documented dev
// backend port only for `vite`/`vite build` runs outside docker compose,
// which otherwise sets VITE_API_BASE_URL itself.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

// Tell the API which language to serve translated catalog content in (issue
// #6). The backend's ActiveLanguageMiddleware reads Accept-Language and
// django-modeltranslation returns the matching translation (falling back when a
// field is untranslated), so the shop content follows the chosen UI language.
function langHeaders(): Record<string, string> {
  const lang = i18n.resolvedLanguage;
  return lang ? { "Accept-Language": lang } : {};
}

// Common list query params: page-number pagination + server-side search.
// `pageSize` lets pickers fetch the full option list in one go.
export interface ListParams {
  page?: number;
  search?: string;
  pageSize?: number;
}

function listQuery(params: ListParams = {}): string {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.search) q.set("search", params.search);
  if (params.pageSize) q.set("page_size", String(params.pageSize));
  const s = q.toString();
  return s ? `?${s}` : "";
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^|;)\\s*" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

/** An error from a failed API request; carries the HTTP status so callers can
 *  react (e.g. a 404 means "not found" → show an empty state, a 401/403 means
 *  the session is gone → prompt to sign in). */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: langHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    throw new ApiError(`Request failed (${response.status}): ${path}`, response.status);
  }
  return response.json() as Promise<T>;
}

/** Flatten any DRF error body into individual messages: handles `{detail}`,
 *  `{non_field_errors: [...]}` and field-keyed `{field: ["msg", …]}` shapes. */
function messagesFrom(value: unknown): string[] {
  if (value == null) return [];
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(messagesFrom);
  if (typeof value === "object")
    return Object.values(value as Record<string, unknown>).flatMap(messagesFrom);
  return [String(value)];
}

/** Turn an error response into a readable, localized message. Backend strings
 *  are stable English; `t()` translates the ones present in the catalog and
 *  passes the rest through unchanged. */
function extractApiError(data: unknown, status: number): string {
  const messages = messagesFrom(data)
    .map((m) => m.trim())
    .filter(Boolean);
  if (messages.length) {
    return Array.from(new Set(messages.map((m) => i18n.t(m)))).join(" ");
  }
  return i18n.t("The request failed ({{status}}).", { status });
}

async function mutate<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken") ?? "",
      ...langHeaders(),
    },
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let message: string;
    try {
      message = extractApiError(await response.json(), response.status);
    } catch {
      message = i18n.t("The request failed ({{status}}).", { status: response.status });
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** Catalog entities that carry an uploadable image. */
export type ImageEntity = "products" | "categories" | "sections" | "pools";

/** Pending image change produced by the crop component. */
export type ImageAction =
  | { kind: "set"; blob: Blob }
  | { kind: "clear" }
  | null;

async function imageRequest(path: string, method: string, blob?: Blob): Promise<void> {
  let body: FormData | undefined;
  if (blob) {
    body = new FormData();
    body.append("image", blob, "image.jpg");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    credentials: "include",
    body,
  });
  if (!response.ok) {
    let detail = `Image upload failed (${response.status})`;
    try {
      const data = await response.json();
      if (data?.detail) detail = data.detail;
    } catch {
      // keep generic message
    }
    throw new Error(detail);
  }
}

/** Pending PDF change for a product's `pdf` attribute, keyed by attribute. */
export type PdfAction = { kind: "set"; file: File } | { kind: "clear" };

/** Turn a stored media path (e.g. "/media/…") into an absolute URL the SPA can
 *  link to (same-origin in prod, the API host in dev). Absolute URLs pass through. */
export function mediaUrl(path: string): string {
  if (!path) return path;
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}

export const api = {
  /** Apply a pending image change to a saved entity (no-op when null). */
  applyImage: async (entity: ImageEntity, id: number, action: ImageAction) => {
    if (!action) return;
    const path = `/api/manage/${entity}/${id}/image/`;
    if (action.kind === "set") await imageRequest(path, "POST", action.blob);
    else await imageRequest(path, "DELETE");
  },
  /** Append one image to a product's gallery; returns the created image. */
  uploadProductImage: async (productId: number, file: File): Promise<ProductImage> => {
    const body = new FormData();
    body.append("image", file, file.name);
    const response = await fetch(
      `${API_BASE_URL}/api/manage/products/${productId}/images/`,
      {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
        credentials: "include",
        body,
      },
    );
    if (!response.ok) {
      let detail = `Image upload failed (${response.status})`;
      try {
        const data = await response.json();
        if (data?.detail) detail = data.detail;
      } catch {
        // keep the generic message
      }
      throw new Error(detail);
    }
    return response.json() as Promise<ProductImage>;
  },
  /** Extract product fields (title/description/attributes) from an uploaded
   *  PDF manual, to pre-fill the product form (AI feature 2). Nothing is
   *  persisted — the caller merges the result into local form state. */
  extractProductFromPdf: async (
    productTypeId: number,
    file: File,
  ): Promise<{
    title: Record<string, string>;
    description: Record<string, string>;
    attributes: Record<string, unknown>;
  }> => {
    const body = new FormData();
    body.append("product_type", String(productTypeId));
    body.append("file", file, file.name);
    const response = await fetch(
      `${API_BASE_URL}/api/manage/products/extract-from-pdf/`,
      {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
        credentials: "include",
        body,
      },
    );
    if (!response.ok) {
      let detail = `Extraction failed (${response.status})`;
      try {
        const data = await response.json();
        if (data?.detail) detail = i18n.t(data.detail);
      } catch {
        // keep the generic message
      }
      throw new Error(detail);
    }
    return response.json();
  },
  deleteProductImage: (productId: number, imageId: number) =>
    mutate<void>(`/api/manage/products/${productId}/images/${imageId}/`, "DELETE"),
  reorderProductImages: (productId: number, ids: number[]) =>
    mutate<ProductImage[]>(
      `/api/manage/products/${productId}/images/reorder/`,
      "POST",
      { order: ids },
    ),
  /** Apply a pending PDF change to a product's `pdf` attribute. */
  applyProductPdf: async (id: number, key: string, action: PdfAction) => {
    const path = `/api/manage/products/${id}/attribute-pdf/?key=${encodeURIComponent(key)}`;
    let body: FormData | undefined;
    if (action.kind === "set") {
      body = new FormData();
      body.append("file", action.file, action.file.name);
    }
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: action.kind === "set" ? "POST" : "DELETE",
      headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
      credentials: "include",
      body,
    });
    if (!response.ok) {
      let detail = `PDF upload failed (${response.status})`;
      try {
        const data = await response.json();
        if (data?.detail) detail = data.detail;
      } catch {
        // keep generic message
      }
      throw new Error(detail);
    }
  },
  /** Machine-translate a snippet for the editor's pre-fill (basicbar contract:
   *  `{text, source, target, format?}` → `{translated}`). */
  translate: (
    text: string,
    source: string,
    target: string,
    format: "text" | "html" = "text",
  ) =>
    mutate<{ translated: string }>("/api/manage/translate/", "POST", {
      text,
      source,
      target,
      format,
    }),
  listSections: () => getJson<Paginated<SectionListItem>>("/api/sections/"),
  getSection: (id: number | string) => getJson<SectionDetail>(`/api/sections/${id}/`),
  getProduct: (id: number | string) => getJson<ProductDetail>(`/api/products/${id}/`),
  getFeatured: () => getJson<FeaturedProducts>("/api/products/featured/"),
  /** Resource pools the current user may access (shop browse-by-pool). */
  getShopPools: () => getJson<PoolCard[]>("/api/pools/"),
  /** One pool's public info page (opening hours, address, contact). */
  getPool: (poolId: number | string) =>
    getJson<PoolDetail>(`/api/pools/${poolId}/`),
  /** Bookable products that have a unit in the given pool. */
  getPoolProducts: (poolId: number | string) =>
    getJson<Paginated<ProductBrief>>(`/api/products/?pool=${poolId}&page_size=2000`),
  /** The same stock, clustered by category for the pool page (#14). */
  getPoolProductsGrouped: (poolId: number | string) =>
    getJson<PoolProductGroup[]>(`/api/pools/${poolId}/products-grouped/`),
  // Borrower-facing sets (§4.5).
  listShopSets: () => getJson<Paginated<SetBrief>>("/api/sets/"),
  getSet: (id: number | string) => getJson<SetDetail>(`/api/sets/${id}/`),
  getSetAvailability: (setId: number, start: string, end: string) =>
    getJson<SetAvailability>(
      `/api/sets/${setId}/availability/?start=${encodeURIComponent(start)}` +
        `&end=${encodeURIComponent(end)}`,
    ),
  // Set booking reuses the same calendar shapes as products (§5.5).
  getSetCalendar: (setId: number | string, from: string, to: string) =>
    getJson<{ days: DayAvailability[] }>(
      `/api/sets/${setId}/availability/calendar/?from=${from}&to=${to}`,
    ),
  getSetHourlyAvailability: (setId: number | string, date: string) =>
    getJson<HourlyAvailability>(
      `/api/sets/${setId}/availability/hours/?date=${date}`,
    ),
  getSetHourlyCalendar: (setId: number | string, from: string, to: string) =>
    getJson<{ days: HourlyCalendarDay[] }>(
      `/api/sets/${setId}/availability/hours/calendar/?from=${from}&to=${to}`,
    ),
  addSetToCart: (set: number, start: string, end: string) =>
    mutate<Booking>("/api/cart/sets/", "POST", { set, start, end }),
  searchProducts: (query: string) =>
    getJson<Paginated<ProductBrief>>(`/api/products/?search=${encodeURIComponent(query)}`),
  search: (query: string) =>
    getJson<SearchResults>(`/api/search/?q=${encodeURIComponent(query)}`),
  getAvailability: (productId: number | string, start: string, end: string, pool?: number) =>
    getJson<Availability>(
      `/api/products/${productId}/availability/?start=${encodeURIComponent(start)}` +
        `&end=${encodeURIComponent(end)}${pool ? `&pool=${pool}` : ""}`,
    ),
  getPoolAvailability: (productId: number | string, start: string, end: string) =>
    getJson<{ pools: PoolAvailability[] }>(
      `/api/products/${productId}/availability/pools/?start=${encodeURIComponent(start)}` +
        `&end=${encodeURIComponent(end)}`,
    ),
  getAvailabilityCalendar: (
    productId: number | string, from: string, to: string, pool?: number,
  ) =>
    getJson<{ days: DayAvailability[] }>(
      `/api/products/${productId}/availability/calendar/?from=${from}&to=${to}` +
        (pool ? `&pool=${pool}` : ""),
    ),
  getHourlyAvailability: (productId: number | string, date: string, pool?: number) =>
    getJson<HourlyAvailability>(
      `/api/products/${productId}/availability/hours/?date=${date}` +
        (pool ? `&pool=${pool}` : ""),
    ),
  getHourlyCalendar: (productId: number | string, from: string, to: string, pool?: number) =>
    getJson<{ days: HourlyCalendarDay[] }>(
      `/api/products/${productId}/availability/hours/calendar/?from=${from}&to=${to}` +
        (pool ? `&pool=${pool}` : ""),
    ),
  getBulkAvailability: (date: string, productIds: number[]) =>
    getJson<{ date: string; availability: Record<string, { available: number; total: number }> }>(
      `/api/availability/?date=${date}&products=${productIds.join(",")}`,
    ),
  // Remember the user's UI/email language (so notification emails match).
  setLanguage: (language: string) =>
    mutate<{ language: string }>("/api/whoami/language/", "POST", { language }),
  listMyBookings: () => getJson<Paginated<Booking>>("/api/bookings/"),
  myBookingsCurrentCount: () =>
    getJson<{ count: number }>("/api/bookings/current-count/"),
  getMyBookingByCode: (code: string) =>
    getJson<Booking>(`/api/bookings/by-code/?code=${encodeURIComponent(code)}`),
  cancelBooking: (id: number) => mutate<void>(`/api/bookings/${id}/`, "DELETE"),
  // Favorites (borrower's saved products).
  getFavorites: () => getJson<ProductBrief[]>("/api/favorites/"),
  addFavorite: (product: number) =>
    mutate<{ product: number; is_favorite: boolean }>("/api/favorites/", "POST", {
      product,
    }),
  removeFavorite: (product: number) =>
    mutate<void>(`/api/favorites/${product}/`, "DELETE"),
  // Cart (a held, not-yet-submitted reservation).
  getCart: () => getJson<{ cart: Booking | null }>("/api/cart/"),
  addToCart: (product: number, start: string, end: string, pool?: number) =>
    mutate<Booking>(
      "/api/cart/items/",
      "POST",
      pool ? { product, start, end, pool } : { product, start, end },
    ),
  // Add one more of an existing line (same product + period, fresh resource).
  duplicateCartItem: (itemId: number) =>
    mutate<Booking>(`/api/cart/items/${itemId}/`, "POST"),
  removeCartItem: (itemId: number) =>
    mutate<Booking>(`/api/cart/items/${itemId}/`, "DELETE"),
  submitCart: (note: string) =>
    mutate<{ bookings: Booking[] }>("/api/cart/submit/", "POST", { note }),
  clearCart: () => mutate<void>("/api/cart/", "DELETE"),
  // Lending desk (lenders/admins).
  listManagedBookings: (params: { status?: string; search?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.search) q.set("search", params.search);
    const qs = q.toString();
    return getJson<Paginated<ManagedBooking>>(
      `/api/manage/bookings/${qs ? `?${qs}` : ""}`,
    );
  },
  getLendingOverview: () =>
    getJson<LendingOverview>("/api/manage/borrowers/"),
  getResourceBorrowers: (resourceId: number, page = 1) =>
    getJson<Paginated<ResourceBooking>>(
      `/api/manage/borrowers/resources/${resourceId}/?page=${page}`,
    ),
  getPendingCount: () =>
    getJson<{ count: number }>("/api/manage/bookings/pending-count/"),
  getDayOverview: (date: string) =>
    getJson<DayOverview>(`/api/manage/bookings/day/?date=${date}`),
  getManageCalendar: (from: string, to: string) =>
    getJson<{ days: ManageCalendarDay[]; closed_days: string[] }>(
      `/api/manage/bookings/calendar/?from=${from}&to=${to}`,
    ),
  confirmBooking: (id: number, message?: string) =>
    mutate<ManagedBooking>(
      `/api/manage/bookings/${id}/confirm/`,
      "POST",
      message ? { message } : undefined,
    ),
  handoutBooking: (id: number, itemIds?: number[]) =>
    mutate<ManagedBooking>(
      `/api/manage/bookings/${id}/handout/`,
      "POST",
      itemIds ? { item_ids: itemIds } : undefined,
    ),
  returnBooking: (id: number, itemIds?: number[]) =>
    mutate<ManagedBooking>(
      `/api/manage/bookings/${id}/return/`,
      "POST",
      itemIds ? { item_ids: itemIds } : undefined,
    ),
  cancelManagedBooking: (id: number) =>
    mutate<ManagedBooking>(`/api/manage/bookings/${id}/cancel/`, "POST"),
  remindBooking: (id: number) =>
    mutate<ManagedBooking>(`/api/manage/bookings/${id}/remind/`, "POST"),
  // QR device handout (concept §6.2).
  resolveScan: (value: string) =>
    getJson<ScanResult>(
      `/api/manage/bookings/scan/?value=${encodeURIComponent(value)}`,
    ),
  getBookingByCode: (code: string) =>
    getJson<ManagedBooking>(
      `/api/manage/bookings/by-code/?code=${encodeURIComponent(code)}`,
    ),
  resolveHandoutResource: (qr: string) =>
    getJson<HandoutResource>(
      `/api/manage/bookings/resolve-resource/?qr=${encodeURIComponent(qr)}`,
    ),
  swapBookingItem: (bookingId: number, itemId: number, resource: number) =>
    mutate<ManagedBooking>(`/api/manage/bookings/${bookingId}/swap/`, "POST", {
      item_id: itemId,
      resource,
    }),
  addBookingItem: (bookingId: number, resource: number) =>
    mutate<ManagedBooking>(`/api/manage/bookings/${bookingId}/add-item/`, "POST", {
      resource,
    }),
  // Public: resolve a device QR sticker to its product (for the /r redirect).
  resolveResourceByQr: (qrId: string) =>
    getJson<{ product: number; product_title: string; inventory_number: string }>(
      `/api/resources/by-qr/${encodeURIComponent(qrId)}/`,
    ),
  // Walk-in lending (lenders create a booking on a borrower's behalf, §6.4).
  getWalkinContext: () =>
    getJson<{ pools: WalkinPool[] }>("/api/manage/walkin/context/"),
  getWalkinProducts: (pool: number) =>
    getJson<{ products: WalkinProduct[] }>(
      `/api/manage/walkin/products/?pool=${pool}`,
    ),
  // Walk-in availability reuses the booking calendars (lead time/horizon off).
  getWalkinCalendar: (pool: number, product: number, from: string, to: string) =>
    getJson<{ days: DayAvailability[] }>(
      `/api/manage/walkin/availability/calendar/?pool=${pool}&product=${product}&from=${from}&to=${to}`,
    ),
  getWalkinHourly: (pool: number, product: number, date: string) =>
    getJson<HourlyAvailability>(
      `/api/manage/walkin/availability/hours/?pool=${pool}&product=${product}&date=${date}`,
    ),
  getWalkinHourlyCalendar: (
    pool: number,
    product: number,
    from: string,
    to: string,
  ) =>
    getJson<{ days: HourlyCalendarDay[] }>(
      `/api/manage/walkin/availability/hours/calendar/?pool=${pool}&product=${product}&from=${from}&to=${to}`,
    ),
  getWalkinResources: (
    pool: number,
    product: number,
    start: string,
    end: string,
  ) =>
    getJson<{ resources: WalkinResource[] }>(
      `/api/manage/walkin/resources/?pool=${pool}&product=${product}` +
        `&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
    ),
  searchBorrowers: (q: string) =>
    getJson<BorrowerCandidate[]>(
      `/api/manage/borrower-search/?q=${encodeURIComponent(q)}`,
    ),
  createWalkin: (payload: {
    borrower: number;
    pool: number;
    hand_out: boolean;
    note?: string;
    items: { product: number; resource: number; start: string; end: string }[];
  }) => mutate<ManagedBooking>("/api/manage/walkin/", "POST", payload),
  markResourceDefective: (id: number, note: string) =>
    mutate<{
      id: number;
      inventory_number: string;
      status: string;
      defect_note: string;
      rebooked: number;
      unfulfilled: number;
    }>(`/api/manage/resources/${id}/defective/`, "POST", { note }),
  markResourceAvailable: (id: number) =>
    mutate<{ id: number; inventory_number: string; status: string; defect_note: string }>(
      `/api/manage/resources/${id}/available/`,
      "POST",
    ),
  // Admin: resource-pool management.
  listPools: (params?: ListParams) =>
    getJson<Paginated<ResourcePool>>(`/api/manage/pools/${listQuery(params)}`),
  createPool: (data: ResourcePoolInput) =>
    mutate<ResourcePool>("/api/manage/pools/", "POST", data),
  updatePool: (id: number, data: Partial<ResourcePoolInput>) =>
    mutate<ResourcePool>(`/api/manage/pools/${id}/`, "PATCH", data),
  deletePool: (id: number) => mutate<void>(`/api/manage/pools/${id}/`, "DELETE"),
  reorderPools: (order: number[]) =>
    mutate<{ status: string; count: number }>(
      "/api/manage/pools/reorder/",
      "POST",
      { order },
    ),
  // Admin: data import/export (whole system or a single pool) as a ZIP archive.
  exportData: async (poolId?: number): Promise<void> => {
    const qs = poolId ? `?pool=${poolId}` : "";
    const response = await fetch(`${API_BASE_URL}/api/manage/export/${qs}`, {
      credentials: "include",
    });
    if (!response.ok) throw new ApiError(i18n.t("Export failed."), response.status);
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = match ? match[1] : "ausleihbar-export.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  importData: async (file: File, dryRun: boolean): Promise<ImportSummary> => {
    const body = new FormData();
    body.append("file", file);
    if (dryRun) body.append("dry_run", "1");
    const response = await fetch(`${API_BASE_URL}/api/manage/import/`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new ApiError(
        extractApiError(data, response.status),
        response.status,
      );
    }
    return data as ImportSummary;
  },
  // Admin: product-type management.
  listProductTypes: (params?: ListParams) =>
    getJson<Paginated<ProductType>>(`/api/manage/product-types/${listQuery(params)}`),
  createProductType: (data: ProductTypeInput) =>
    mutate<ProductType>("/api/manage/product-types/", "POST", data),
  updateProductType: (id: number, data: Partial<ProductTypeInput>) =>
    mutate<ProductType>(`/api/manage/product-types/${id}/`, "PATCH", data),
  deleteProductType: (id: number) =>
    mutate<void>(`/api/manage/product-types/${id}/`, "DELETE"),
  // Per-attribute count of products with a non-empty, non-default value (§5.2).
  getAttributeUsage: (id: number) =>
    getJson<Record<string, number>>(
      `/api/manage/product-types/${id}/attribute-usage/`,
    ),
  /** AI-generated attribute-schema suggestions for a product type. The type's
   *  name/description give context; `hints` are optional extra guidance.
   *  `existingKeys` is excluded to avoid duplicates. */
  suggestAttributes: (
    input: { name?: string; description?: string; hints?: string; existingKeys: string[] },
  ) =>
    mutate<{ attributes: AttributeDef[] }>(
      "/api/manage/product-types/suggest-attributes/",
      "POST",
      {
        name: input.name ?? "",
        description: input.description ?? "",
        hints: input.hints ?? "",
        existing_keys: input.existingKeys,
      },
    ),
  // Admin: product management.
  listManagedProducts: (params: ListParams & { category?: string } = {}) => {
    const base = listQuery(params);
    const cat = params.category
      ? `${base ? "&" : "?"}category=${encodeURIComponent(params.category)}`
      : "";
    return getJson<Paginated<ManageProduct>>(`/api/manage/products/${base}${cat}`);
  },
  createProduct: (data: ManageProductInput) =>
    mutate<ManageProduct>("/api/manage/products/", "POST", data),
  updateProduct: (id: number, data: Partial<ManageProductInput>) =>
    mutate<ManageProduct>(`/api/manage/products/${id}/`, "PATCH", data),
  deleteProduct: (id: number) =>
    mutate<void>(`/api/manage/products/${id}/`, "DELETE"),
  // Admin: category management.
  listManagedCategories: (params?: ListParams) =>
    getJson<Paginated<ManageCategory>>(`/api/manage/categories/${listQuery(params)}`),
  createCategory: (data: ManageCategoryInput) =>
    mutate<ManageCategory>("/api/manage/categories/", "POST", data),
  updateCategory: (id: number, data: Partial<ManageCategoryInput>) =>
    mutate<ManageCategory>(`/api/manage/categories/${id}/`, "PATCH", data),
  deleteCategory: (id: number) =>
    mutate<void>(`/api/manage/categories/${id}/`, "DELETE"),
  reorderCategories: (ids: number[]) =>
    mutate<{ status: string; count: number }>(
      "/api/manage/categories/reorder/",
      "POST",
      { order: ids },
    ),
  // Admin: set management (products lent together, §5.5).
  listSets: (params?: ListParams) =>
    getJson<Paginated<ManageSet>>(`/api/manage/product-sets/${listQuery(params)}`),
  createSet: (data: ManageSetInput) =>
    mutate<ManageSet>("/api/manage/product-sets/", "POST", data),
  updateSet: (id: number, data: Partial<ManageSetInput>) =>
    mutate<ManageSet>(`/api/manage/product-sets/${id}/`, "PATCH", data),
  deleteSet: (id: number) =>
    mutate<void>(`/api/manage/product-sets/${id}/`, "DELETE"),
  // Admin: section ("Sparte") management.
  listManagedSections: (params?: ListParams) =>
    getJson<Paginated<ManageSection>>(`/api/manage/sections/${listQuery(params)}`),
  createSection: (data: ManageSectionInput) =>
    mutate<ManageSection>("/api/manage/sections/", "POST", data),
  updateSection: (id: number, data: Partial<ManageSectionInput>) =>
    mutate<ManageSection>(`/api/manage/sections/${id}/`, "PATCH", data),
  deleteSection: (id: number) =>
    mutate<void>(`/api/manage/sections/${id}/`, "DELETE"),
  reorderSections: (ids: number[]) =>
    mutate<{ status: string; count: number }>(
      "/api/manage/sections/reorder/",
      "POST",
      { order: ids },
    ),
  // Admin: inventory (resource) management.
  listInventory: (
    params: {
      pool?: number;
      status?: string;
      created_after?: string;
      page?: number;
      search?: string;
      pageSize?: number;
      ordering?: string;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.pool) q.set("pool", String(params.pool));
    if (params.status) q.set("status", params.status);
    if (params.created_after) q.set("created_after", params.created_after);
    if (params.page) q.set("page", String(params.page));
    if (params.search) q.set("search", params.search);
    if (params.pageSize) q.set("page_size", String(params.pageSize));
    if (params.ordering) q.set("ordering", params.ordering);
    const qs = q.toString();
    return getJson<Paginated<ManageResource>>(
      `/api/manage/inventory/${qs ? `?${qs}` : ""}`,
    );
  },
  createResource: (data: ManageResourceInput) =>
    mutate<ManageResource>("/api/manage/inventory/", "POST", data),
  updateResource: (id: number, data: Partial<ManageResourceInput>) =>
    mutate<ManageResource>(`/api/manage/inventory/${id}/`, "PATCH", data),
  deleteResource: (id: number) =>
    mutate<void>(`/api/manage/inventory/${id}/`, "DELETE"),
  getInventoryItem: (id: number | string) =>
    getJson<ResourceDetail>(`/api/manage/inventory/${id}/`),
  getInventoryDefects: () =>
    getJson<{ resources: DefectRow[] }>("/api/manage/inventory/defects/"),
  // Per-pool GitLab defect-ticket settings (lender-scoped). The token is
  // write-only: never read back, only `defect_gitlab_token_set` reports it.
  getDefectTickets: () =>
    getJson<DefectTicketConfig[]>("/api/manage/defect-tickets/"),
  updateDefectTicket: (
    poolId: number,
    body: { defect_gitlab_url: string; defect_gitlab_token?: string },
  ) =>
    mutate<DefectTicketConfig>(
      `/api/manage/defect-tickets/${poolId}/`,
      "PATCH",
      body,
    ),
  // Device QR sticker image (authenticated) — returns an object URL.
  getInventoryQr: async (id: number): Promise<string> => {
    const response = await fetch(`${API_BASE_URL}/api/manage/inventory/${id}/qr/`, {
      credentials: "include",
    });
    if (!response.ok) throw new Error(`QR image failed (${response.status})`);
    return URL.createObjectURL(await response.blob());
  },
  suggestInventoryNumber: (pool: number) =>
    getJson<{ inventory_number: string; qr_code_id: string }>(
      `/api/manage/inventory/suggest-number/?pool=${pool}`,
    ),
  // Admin: user management (roles & lender pool memberships).
  listUsers: (params: { search?: string; role?: string; page?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.search) q.set("search", params.search);
    if (params.role) q.set("role", params.role);
    if (params.page) q.set("page", String(params.page));
    const qs = q.toString();
    return getJson<Paginated<ManageUser>>(
      `/api/manage/users/${qs ? `?${qs}` : ""}`,
    );
  },
  getUser: (id: number) => getJson<ManageUser>(`/api/manage/users/${id}/`),
  updateUserRole: (
    id: number,
    data: { is_admin?: boolean; is_active?: boolean },
  ) => mutate<ManageUser>(`/api/manage/users/${id}/`, "PATCH", data),
  setUserPools: (id: number, poolIds: number[]) =>
    mutate<ManageUser>(`/api/manage/users/${id}/pools/`, "PUT", {
      pool_ids: poolIds,
    }),
  setUserGroups: (id: number, groupIds: number[]) =>
    mutate<ManageUser>(`/api/manage/users/${id}/groups/`, "PUT", {
      group_ids: groupIds,
    }),
  getUserBookings: (
    id: number,
    group: "upcoming" | "handed_out" | "completed",
    page = 1,
  ) =>
    getJson<Paginated<Booking>>(
      `/api/manage/users/${id}/bookings/?group=${group}&page=${page}`,
    ),
  // Lending-desk borrower profile (lenders + admins): identity, status, history.
  getBorrowerProfile: (id: number) =>
    getJson<BorrowerProfile>(`/api/manage/borrower-profiles/${id}/`),
  getBorrowerBookings: (
    id: number,
    group: "upcoming" | "handed_out" | "completed",
    page = 1,
  ) =>
    getJson<Paginated<Booking>>(
      `/api/manage/borrower-profiles/${id}/bookings/?group=${group}&page=${page}`,
    ),
  // Strikes (lenders issue via a booking; admins manage).
  createStrike: (data: { booking?: number; user?: number; reason: string }) =>
    mutate<Strike>("/api/manage/strikes/", "POST", data),
  deleteStrike: (id: number) => mutate<void>(`/api/manage/strikes/${id}/`, "DELETE"),
  unblockUser: (id: number) =>
    mutate<ManageUser>(`/api/manage/users/${id}/unblock/`, "POST"),
  getStrikeSetting: () => getJson<StrikeSetting>("/api/manage/strike-setting/"),
  updateStrikeSetting: (data: StrikeSetting) =>
    mutate<StrikeSetting>("/api/manage/strike-setting/", "PUT", data),
  getRetentionSetting: () =>
    getJson<RetentionSetting>("/api/manage/retention-setting/"),
  updateRetentionSetting: (data: { enabled: boolean; retention_days: number }) =>
    mutate<RetentionSetting>("/api/manage/retention-setting/", "PUT", data),
  // Admin: central trash bin (soft-deleted catalog items).
  listTrash: () => getJson<TrashItem[]>("/api/manage/trash/"),
  restoreTrash: (type: string, id: number) =>
    mutate<{ detail: string }>(`/api/manage/trash/${type}/${id}/restore/`, "POST"),
  purgeTrashItem: (type: string, id: number) =>
    mutate<void>(`/api/manage/trash/${type}/${id}/`, "DELETE"),
  emptyTrash: () => mutate<void>("/api/manage/trash/", "DELETE"),
  getTrashSetting: () => getJson<TrashSetting>("/api/manage/trash-setting/"),
  updateTrashSetting: (data: { retention_days: number }) =>
    mutate<TrashSetting>("/api/manage/trash-setting/", "PUT", data),
  // Admin: access groups (pool eligibility rules).
  listAccessGroups: () =>
    getJson<Paginated<AccessGroup>>("/api/manage/access-groups/"),
  createAccessGroup: (data: AccessGroupInput) =>
    mutate<AccessGroup>("/api/manage/access-groups/", "POST", data),
  updateAccessGroup: (id: number, data: Partial<AccessGroupInput>) =>
    mutate<AccessGroup>(`/api/manage/access-groups/${id}/`, "PATCH", data),
  deleteAccessGroup: (id: number) =>
    mutate<void>(`/api/manage/access-groups/${id}/`, "DELETE"),
  importHolidays: (country: string, subdiv: string, year: number) =>
    mutate<{ created: { date: string; name: string }[]; count: number }>(
      "/api/manage/holidays/import/",
      "POST",
      { country, subdiv, year },
    ),
  // Admin/lender: block days (Sperrtage).
  listBlocks: (pool?: number) =>
    getJson<Paginated<BlockDay>>(
      `/api/manage/blocks/${pool ? `?pool=${pool}` : ""}`,
    ),
  createBlock: (data: BlockDayInput) =>
    mutate<BlockDay>("/api/manage/blocks/", "POST", data),
  deleteBlock: (id: number) => mutate<void>(`/api/manage/blocks/${id}/`, "DELETE"),
  // Lenders/admins: per-product lending statistics.
  getProductStats: (
    params: { from?: string; to?: string; pool?: number } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.from) q.set("from", params.from);
    if (params.to) q.set("to", params.to);
    if (params.pool) q.set("pool", String(params.pool));
    const qs = q.toString();
    return getJson<ProductStatsResponse>(
      `/api/manage/stats/products/${qs ? `?${qs}` : ""}`,
    );
  },
  getDefectStats: (pool?: number) =>
    getJson<DefectStats>(
      `/api/manage/stats/defects/${pool ? `?pool=${pool}` : ""}`,
    ),
  getCapacityStats: () =>
    getJson<CapacityStats>("/api/manage/stats/capacity/"),
  getProductTimeseries: (
    productId: number,
    params: { from?: string; to?: string; pool?: number; bucket?: string } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.from) q.set("from", params.from);
    if (params.to) q.set("to", params.to);
    if (params.pool) q.set("pool", String(params.pool));
    if (params.bucket) q.set("bucket", params.bucket);
    const qs = q.toString();
    return getJson<ProductTimeseries>(
      `/api/manage/stats/products/${productId}/timeseries/${qs ? `?${qs}` : ""}`,
    );
  },
  // Admin: public-holiday region (auto-loads holidays across the horizon).
  getHolidaySetting: () =>
    getJson<HolidaySetting>("/api/manage/holiday-setting/"),
  updateHolidaySetting: (data: { country: string; subdivision: string }) =>
    mutate<HolidaySetting>("/api/manage/holiday-setting/", "PUT", data),
  getCartSetting: () => getJson<CartSetting>("/api/manage/cart-setting/"),
  updateCartSetting: (data: { hold_minutes: number }) =>
    mutate<CartSetting>("/api/manage/cart-setting/", "PUT", data),
  getShopSetting: () => getJson<ShopSetting>("/api/manage/shop-setting/"),
  updateShopSetting: (data: Partial<ShopSetting>) =>
    mutate<ShopSetting>("/api/manage/shop-setting/", "PUT", data),
  getNotificationSetting: () =>
    getJson<NotificationSetting>("/api/manage/notification-setting/"),
  updateNotificationSetting: (data: Partial<NotificationSetting>) =>
    mutate<NotificationSetting>("/api/manage/notification-setting/", "PUT", data),
  // Public welcome page (for not-yet-logged-in visitors).
  getWelcome: () => getJson<WelcomeData>("/api/welcome/"),
  getWelcomeSetting: () => getJson<WelcomeSetting>("/api/manage/welcome-setting/"),
  updateWelcomeSetting: (data: { text: string }) =>
    mutate<WelcomeSetting>("/api/manage/welcome-setting/", "PUT", data),
  /** Public shop branding (institution logo) for the header. */
  getBranding: () => getJson<Branding>("/api/branding/"),
  /** Admin: upload the shop logo (image or SVG). */
  uploadShopLogo: async (file: File): Promise<Branding> => {
    const body = new FormData();
    body.append("logo", file, file.name);
    const response = await fetch(
      `${API_BASE_URL}/api/manage/welcome-setting/logo/`,
      {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
        credentials: "include",
        body,
      },
    );
    if (!response.ok) {
      let detail = `Logo upload failed (${response.status})`;
      try {
        const data = await response.json();
        if (data?.detail) detail = data.detail;
      } catch {
        // keep the generic message
      }
      throw new Error(detail);
    }
    return response.json() as Promise<Branding>;
  },
  deleteShopLogo: () =>
    mutate<Branding>("/api/manage/welcome-setting/logo/", "DELETE"),

  // --- Content pages (CMS): footer links + admin CRUD ---
  /** Public footer links (published, footer-flagged pages). */
  getFooterPages: () => getJson<PageLink[]>("/api/pages/"),
  /** Public read of one published page by slug. */
  getPage: (slug: string) => getJson<PageDetail>(`/api/pages/${slug}/`),
  listPages: () => getJson<Paginated<CmsPage>>("/api/manage/pages/?page_size=2000"),
  createPage: (data: CmsPageInput) =>
    mutate<CmsPage>("/api/manage/pages/", "POST", data),
  updatePage: (id: number, data: Partial<CmsPageInput>) =>
    mutate<CmsPage>(`/api/manage/pages/${id}/`, "PATCH", data),
  deletePage: (id: number) => mutate<void>(`/api/manage/pages/${id}/`, "DELETE"),
  reorderPages: (ids: number[]) =>
    mutate<{ status: string; count: number }>(
      "/api/manage/pages/reorder/",
      "POST",
      { order: ids },
    ),
};
