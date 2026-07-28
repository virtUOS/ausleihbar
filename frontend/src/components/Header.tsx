// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Handshake,
  Heart,
  Monitor,
  Moon,
  QrCode,
  Search,
  Settings,
  ShoppingCart,
  Store,
  Sun,
  X,
} from "lucide-react";
import { useAuth } from "../auth";
import { useCart } from "../cart";
import { useStartDate } from "../startDate";
import { useTheme, type Appearance } from "@basicbar/ui";
import { useFetch } from "../useFetch";
import { useOutsideClose } from "../useOutsideClose";
import { api } from "../api";
import type { Branding } from "../types";
import { DateField } from "./DateField";
import { LanguageMenu } from "./LanguageSwitcher";

/** The wordmark: plain ink, "ausleihBAR" — the pun carried by case alone. */
function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`whitespace-nowrap text-lg font-extrabold tracking-tight text-slate-900 dark:text-slate-100 ${className}`}
    >
      ausleihBAR
    </span>
  );
}

/** Auto / Light / Dark setting (concept #2), surfaced in the account menu.
 *  Auto follows the OS; an explicit pick overrides it. */
function AppearanceControl() {
  const { t } = useTranslation();
  const { appearance, setAppearance } = useTheme();
  const options: {
    value: Appearance;
    label: string;
    hint?: string;
    icon: typeof Sun;
  }[] = [
    { value: "auto", label: t("Auto"), hint: t("(follows your system)"), icon: Monitor },
    { value: "light", label: t("Light"), icon: Sun },
    { value: "dark", label: t("Dark"), icon: Moon },
  ];
  // Full-width radio rows (like the area/language menus) rather than a
  // segmented pill: three labels don't fit the menu width, and this matches
  // the menu's vocabulary — icon + label + a check on the active option.
  return (
    <div role="radiogroup" aria-label={t("Appearance")}>
      <p className="px-3 pb-0.5 pt-1 text-xs text-slate-400 dark:text-slate-500">
        {t("Appearance")}
      </p>
      {options.map((opt) => {
        const active = appearance === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setAppearance(opt.value)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            <opt.icon aria-hidden className="h-4 w-4 text-slate-400" />
            <span className="flex-1">
              {opt.label}
              {opt.hint && (
                <span className="block text-xs text-slate-400 dark:text-slate-500">
                  {opt.hint}
                </span>
              )}
            </span>
            {active && <Check aria-hidden className="h-4 w-4 text-brand-600" />}
          </button>
        );
      })}
    </div>
  );
}

/** Closes a popover on outside click. */
/** Visible area switcher for lenders/admins: shows the current area (Shop /
 *  Lending / Admin) and switches in one click each. Hidden for plain
 *  borrowers — their whole app is the shop. */
function AreaSwitcher() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(open, () => setOpen(false));
  useEffect(() => setOpen(false), [location.pathname]);

  if (!user?.is_lender && !user?.is_staff) return null;

  const areas = [
    {
      to: "/",
      label: t("Shop"),
      icon: Store,
      active:
        !location.pathname.startsWith("/manage") &&
        !location.pathname.startsWith("/admin") &&
        !location.pathname.startsWith("/qr"),
    },
    ...(user.is_lender
      ? [{ to: "/manage", label: t("Lending"), icon: Handshake, active: location.pathname.startsWith("/manage") }]
      : []),
    ...(user.is_lender || user.is_staff
      ? [{ to: "/qr", label: t("QR codes"), icon: QrCode, active: location.pathname.startsWith("/qr") }]
      : []),
    ...(user.is_staff
      ? [{ to: "/admin", label: t("Admin"), icon: Settings, active: location.pathname.startsWith("/admin") }]
      : []),
  ];
  const current = areas.find((a) => a.active) ?? areas[0];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("Switch area")}
        className="flex h-10 items-center gap-1.5 rounded-full px-2.5 text-sm font-medium text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 sm:px-3"
      >
        <current.icon aria-hidden className="h-4 w-4" />
        <span className="hidden sm:inline">{current.label}</span>
        <ChevronDown aria-hidden className="h-3.5 w-3.5 text-slate-400" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-2 w-44 animate-fade-up overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg shadow-slate-900/5 dark:border-slate-700 dark:bg-slate-800"
        >
          {areas.map((area) => (
            <Link
              key={area.to}
              to={area.to}
              role="menuitemradio"
              aria-checked={area.active}
              className="flex items-center gap-2 px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <area.icon aria-hidden className="h-4 w-4 text-slate-400" />
              <span className="flex-1">{area.label}</span>
              {area.active && <Check aria-hidden className="h-4 w-4 text-brand-600" />}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Persistent, mobile-first shop header (concept §4.1). Everything stays
 * visible and one click away: area switcher (for lenders/admins), language
 * globe, the cart in a fixed spot beside the account menu; search expands on
 * small screens.
 */
export function Header() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const { user, login, logout } = useAuth();
  const { count } = useCart();
  const { startDate, setStartDate } = useStartDate();
  const branding = useFetch<Branding>(() => api.getBranding(), []);
  const location = useLocation();
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useOutsideClose(accountOpen, () => setAccountOpen(false));
  const mobileSearchRef = useRef<HTMLInputElement>(null);
  // The "available from" date filters the shop catalog by availability, so the
  // bar belongs on the catalog/browsing pages only — not the cart, "my
  // bookings", or the management/admin areas, where it confused testers (#13).
  const path = location.pathname;
  const isShopBrowsing =
    path === "/" ||
    path === "/search" ||
    ["/sections/", "/pools/", "/products/", "/sets/"].some((prefix) =>
      path.startsWith(prefix),
    );

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      navigate(`/search?q=${encodeURIComponent(trimmed)}`);
      setSearchOpen(false);
    }
  }

  useEffect(() => {
    setAccountOpen(false);
    setSearchOpen(false);
  }, [location.pathname]);
  useEffect(() => {
    if (searchOpen) mobileSearchRef.current?.focus();
  }, [searchOpen]);

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white print:hidden dark:border-slate-800 dark:bg-slate-900">
      {searchOpen && user?.authenticated ? (
        /* Expanded mobile search: takes over the header row, Esc/✕ closes. */
        <form
          onSubmit={onSubmit}
          role="search"
          className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-3"
        >
          <button
            type="button"
            onClick={() => setSearchOpen(false)}
            aria-label={t("Back to menu")}
            title={t("Back to menu")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <ArrowLeft aria-hidden className="h-5 w-5" />
          </button>
          <div className="relative min-w-0 flex-1">
            <Search
              aria-hidden
              className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            />
            <input
              ref={mobileSearchRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setSearchOpen(false)}
              placeholder={t("Search…")}
              aria-label={t("Search the catalog")}
              className="w-full rounded-full border border-slate-200 bg-slate-50 py-2 pl-9 pr-4 text-sm text-slate-900 placeholder:text-slate-400 focus:border-slate-300 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-600 dark:focus:bg-slate-800"
            />
          </div>
        </form>
      ) : (
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-3">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2.5 rounded-md"
            aria-label={t("Home")}
          >
            {branding.data?.logo && (
              <img
                src={branding.data.logo}
                alt=""
                className="h-8 w-auto max-w-[110px] object-contain sm:max-w-[140px]"
              />
            )}
            {/* With a logo, the wordmark yields on small screens so the
                controls keep room. */}
            <Wordmark className={branding.data?.logo ? "hidden md:inline" : ""} />
          </Link>
          {user?.authenticated ? (
            <form
              onSubmit={onSubmit}
              className="relative hidden min-w-0 flex-1 sm:block"
              role="search"
            >
              <Search
                aria-hidden
                className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("Search…")}
                aria-label={t("Search the catalog")}
                className="w-full rounded-full border border-slate-200 bg-slate-50 py-2 pl-9 pr-4 text-sm text-slate-900 placeholder:text-slate-400 transition-colors duration-150 focus:border-slate-300 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-600 dark:focus:bg-slate-800"
              />
            </form>
          ) : (
            <div className="flex-1" />
          )}
          <div className="ml-auto flex shrink-0 items-center gap-0.5 sm:gap-1">
            {user?.authenticated && (
              <button
                type="button"
                onClick={() => setSearchOpen(true)}
                aria-label={t("Search the catalog")}
                className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 sm:hidden"
              >
                <Search aria-hidden className="h-5 w-5" />
              </button>
            )}
            {user?.authenticated && <AreaSwitcher />}
            <LanguageMenu />
            {user?.authenticated && (
              <Link
                to="/favorites"
                aria-label={t("Favorites")}
                title={t("Favorites")}
                className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              >
                <Heart aria-hidden className="h-5 w-5" />
              </Link>
            )}
            {user?.authenticated && (
              <Link
                to="/cart"
                aria-label={
                  count > 0 ? t("Cart ({{count}} items)", { count }) : t("Cart")
                }
                title={t("Cart")}
                className="relative flex h-10 w-10 items-center justify-center rounded-full text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              >
                <ShoppingCart aria-hidden className="h-5 w-5" />
                {count > 0 && (
                  <span
                    key={count}
                    className="absolute right-0 top-0 flex h-[18px] min-w-[18px] animate-pop items-center justify-center rounded-full bg-brand-400 px-1 text-[11px] font-bold tabular-nums text-slate-900"
                  >
                    {count}
                  </span>
                )}
              </Link>
            )}
            {user?.authenticated ? (
              <div className="relative" ref={accountRef}>
                <button
                  type="button"
                  onClick={() => setAccountOpen((open) => !open)}
                  aria-haspopup="menu"
                  aria-expanded={accountOpen}
                  aria-label={t("Account menu")}
                  className="flex items-center rounded-full p-1 transition-colors duration-150 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-400 text-sm font-bold text-slate-900">
                    {(user.username?.[0] ?? "?").toUpperCase()}
                  </span>
                </button>
                {accountOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 z-30 mt-2 w-56 animate-fade-up overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg shadow-slate-900/5 dark:border-slate-700 dark:bg-slate-800"
                  >
                    <p className="truncate px-3 py-2 text-xs text-slate-400 dark:text-slate-500">
                      {t("Signed in as")}{" "}
                      <span className="font-medium text-slate-600 dark:text-slate-300">
                        {user.username}
                      </span>
                    </p>
                    <Link
                      to="/bookings"
                      role="menuitem"
                      className="block px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
                    >
                      {t("My bookings")}
                    </Link>
                    <div className="my-1 border-t border-slate-100 dark:border-slate-700" />
                    <AppearanceControl />
                    <div className="my-1 border-t border-slate-100 dark:border-slate-700" />
                    <button
                      type="button"
                      role="menuitem"
                      onClick={logout}
                      className="block w-full px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
                    >
                      {t("Sign out")}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <button
                type="button"
                onClick={login}
                className="ml-1 shrink-0 rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
              >
                {t("Sign in")}
              </button>
            )}
          </div>
        </div>
      )}
      {user?.authenticated && isShopBrowsing && !searchOpen && (
        <div className="border-t border-slate-100 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-2 text-sm">
            <label htmlFor="start-date" className="text-slate-600 dark:text-slate-300">
              {t("Available from")}
            </label>
            <DateField
              id="start-date"
              ariaLabel={t("Available from")}
              value={startDate ?? ""}
              onChange={(v) => setStartDate(v || null)}
            />
            {startDate && (
              <button
                type="button"
                onClick={() => setStartDate(null)}
                className="flex items-center gap-1 rounded-full px-2 py-1 text-slate-500 transition-colors duration-150 hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100"
              >
                <X aria-hidden className="h-3.5 w-3.5" />
                {t("clear")}
              </button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
