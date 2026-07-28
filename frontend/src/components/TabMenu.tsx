// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { NavLink, useLocation, useNavigate } from "react-router-dom";

export interface TabItem {
  to: string;
  label: string;
  end?: boolean;
  /** Optional count shown as a red badge (e.g. pending confirmations). 0 hides it. */
  badge?: number;
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
      const matches = item.end
        ? pathname === item.to
        : pathname.startsWith(item.to);
      if (matches && item.to.length > bestLen) {
        best = groupIndex;
        bestLen = item.to.length;
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
 * carry a red count badge (e.g. reservations awaiting confirmation).
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
                  : "font-semibold text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
              }`}
            >
              {group.label}
            </button>
          );
        })}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-5 border-b border-slate-200 dark:border-slate-800">
        {groups[activeGroup].items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `-mb-px flex items-center gap-1.5 border-b-2 py-2 text-sm transition-colors duration-150 ${
                isActive
                  ? "border-brand-500 font-semibold text-slate-900 dark:text-slate-100"
                  : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-900 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-100"
              }`
            }
          >
            {item.label}
            {item.badge ? (
              <span className="inline-flex min-w-[1.25rem] justify-center rounded-full bg-red-600 px-1.5 text-xs font-semibold text-white">
                {item.badge}
              </span>
            ) : null}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
