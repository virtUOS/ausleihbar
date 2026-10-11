// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

export interface TabItem {
  to: string;
  label: string;
  end?: boolean;
  /** Optional count shown as a red badge. 0 hides it. */
  badge?: number;
  /** Further path prefixes owned by this view (e.g. its detail pages). */
  alsoMatch?: string[];
}

function itemMatches(item: TabItem, pathname: string): number {
  if (item.end ? pathname === item.to : pathname.startsWith(item.to)) return item.to.length;
  return matchesAlso(item, pathname) ? Math.max(...(item.alsoMatch ?? []).map((p) => p.length)) : -1;
}

function tabClass(isActive: boolean): string {
  return `-mb-px flex items-center gap-1.5 border-b-2 py-2 text-sm transition-colors duration-150 ${
    isActive
      ? "border-brand-500 font-semibold text-slate-900 dark:text-slate-100"
      : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-900 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:text-slate-100"
  }`;
}

/** Whether the path is one of the item's extra paths or below one. */
function matchesAlso(item: TabItem, pathname: string): boolean {
  return (item.alsoMatch ?? []).some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export interface TabGroup {
  label: string;
  items: TabItem[];
}

/** Index of the group that owns the current route (longest matching item). */
function groupForPath(groups: TabGroup[], pathname: string): number {
  let best = 0;
  let bestLen = -1;
  groups.forEach((group, groupIndex) => {
    group.items.forEach((item) => {
      const len = itemMatches(item, pathname);
      if (len > bestLen) {
        best = groupIndex;
        bestLen = len;
      }
    });
  });
  return best;
}

/**
 * Shared two-level area menu for the lending desk (`ManageTabs`) and admin
 * (`AdminTabs`). The top row are group pills — a filled set with a dark-ink
 * active pill for strong wayfinding; switching a group lands on its first view.
 * The second row are underline tabs for the views within the active group, with
 * a honey active indicator that ties the menu into the design system. A view may
 * carry a red count badge.
 */
export function TabMenu({ groups }: { groups: TabGroup[] }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const activeGroup = groupForPath(groups, pathname);

  return (
    <nav className="mb-6">
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
        {groups.map((group, groupIndex) => {
          const active = groupIndex === activeGroup;
          return (
            <button
              key={group.label}
              type="button"
              onClick={() => {
                // Switch area → land on its first view (no-op if already here).
                if (!active) navigate(group.items[0].to);
              }}
              className={`text-lg tracking-tight transition-colors duration-150 ${
                active
                  ? "font-bold text-slate-900 dark:text-slate-100"
                  : "font-semibold text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100"
              }`}
            >
              {group.label}
            </button>
          );
        })}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-5 border-b border-slate-200 dark:border-slate-800">
        {groups[activeGroup].items.map((item) => {
          const content = (
            <>
              {item.label}
              {item.badge ? (
                <span className="inline-flex min-w-[1.25rem] justify-center rounded-full bg-red-600 px-1.5 text-xs font-semibold text-white">
                  {item.badge}
                </span>
              ) : null}
            </>
          );
          // A path owned via `alsoMatch` (e.g. a detail page) is not NavLink's
          // own match, so mark it current explicitly.
          if (matchesAlso(item, pathname)) {
            return (
              <Link key={item.to} to={item.to} aria-current="page" className={tabClass(true)}>
                {content}
              </Link>
            );
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => tabClass(isActive)}
            >
              {content}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
