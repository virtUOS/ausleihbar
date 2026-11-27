// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { ListFilter, X } from "lucide-react";
import { useOutsideClose } from "../../useOutsideClose";
import { activeFilterCount, EMPTY_FILTER, type PlaceFilter } from "../overviewFilter";
import type { Feature, PlaceKind } from "../types";
import { FeatureFilter, featureNames } from "./FeatureFilter";

const checkRow = "flex min-h-[44px] cursor-pointer items-start gap-3 py-2 text-sm text-slate-900 dark:text-slate-100";
const checkbox = "mt-0.5 h-5 w-5 shrink-0 rounded border-slate-300 accent-brand-600 dark:border-slate-600";

/** "Filter" button with a count badge opening the criteria panel; the active
 *  criteria also show as removable chips under the bar (the room chip too,
 *  when the overview is narrowed to one room). The root is `display: contents`
 *  so the button sits in the caller's bar while the chip row (`order-last`,
 *  full width) wraps below it in a flex-wrap bar. The room lives in
 *  `value.roomId`; "Filter zurücksetzen" clears it as well. */
export function PlaceFilterMenu({
  value,
  onChange,
  features,
  hasFavorites,
  roomName,
  onClearRoom,
  isToday = false,
}: {
  value: PlaceFilter;
  onChange: (filter: PlaceFilter) => void;
  features: Feature[];
  /** Whether the viewer has favourites ("Nur Favoriten" is shown then, or while active). */
  hasFavorites: boolean;
  /** Name of the room the overview is narrowed to (adds a chip). */
  roomName?: string;
  onClearRoom?: () => void;
  /** The shown day is today: "Nur freie" means free right now. */
  isToday?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const rootRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const panelId = useId();
  const count = activeFilterCount(value);
  const patch = (p: Partial<PlaceFilter>) => onChange({ ...value, ...p });

  const kindLabel = (k: PlaceKind) => (k === "desk" ? t("Desks") : t("Meeting rooms"));
  const chips: { key: string; label: string; remove: () => void }[] = [];
  if (value.onlyFree) chips.push({ key: "free", label: t("Only free"), remove: () => patch({ onlyFree: false }) });
  if (value.onlyFavorites)
    chips.push({ key: "fav", label: t("Only favorites"), remove: () => patch({ onlyFavorites: false }) });
  if (value.kind !== "") chips.push({ key: "kind", label: kindLabel(value.kind), remove: () => patch({ kind: "" }) });
  const ids = value.features.filter((id) => features.some((f) => f.id === id));
  ids.forEach((id) => {
    const [name] = featureNames(features, [id]);
    chips.push({ key: `f${id}`, label: name, remove: () => patch({ features: value.features.filter((v) => v !== id) }) });
  });
  if (roomName)
    chips.push({
      key: "room",
      label: t("Only room {{name}}", { name: roomName }),
      remove: () => (onClearRoom ? onClearRoom() : patch({ roomId: null })),
    });

  return (
    <div className="contents">
      <div
        ref={rootRef}
        className="relative"
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.stopPropagation();
            setOpen(false);
            buttonRef.current?.focus();
          }
        }}
      >
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => setOpen(!open)}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-slate-300 bg-white px-3.5 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:border-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-slate-500"
        >
          <ListFilter aria-hidden className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
          {t("Filter")}
          {count > 0 && (
            <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-slate-900 px-1.5 text-xs font-bold text-white dark:bg-slate-100 dark:text-slate-900">
              {count}
              <span className="sr-only"> {t("active")}</span>
            </span>
          )}
        </button>
        {open && (
          <div
            id={panelId}
            role="dialog"
            aria-label={t("Filter")}
            className="absolute left-0 z-30 mt-1 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white p-4 shadow-lg dark:border-slate-700 dark:bg-slate-800"
          >
            <label className={checkRow}>
              <input
                type="checkbox"
                checked={value.onlyFree}
                onChange={(e) => patch({ onlyFree: e.target.checked })}
                className={checkbox}
              />
              <span>
                <span className="font-medium">{t("Only free")}</span>
                <span className="block text-xs text-slate-600 dark:text-slate-300">
                  {isToday ? t("free right now") : t("at least 4 hours in a row")}
                </span>
              </span>
            </label>
            {(hasFavorites || value.onlyFavorites) && (
              <label className={checkRow}>
                <input
                  type="checkbox"
                  checked={value.onlyFavorites}
                  onChange={(e) => patch({ onlyFavorites: e.target.checked })}
                  className={checkbox}
                />
                <span className="font-medium">{t("Only favorites")}</span>
              </label>
            )}
            <SegmentedControl
              size="md"
              ariaLabel={t("Show")}
              value={value.kind || "all"}
              onChange={(v) => patch({ kind: v === "all" ? "" : v })}
              options={[
                { value: "all" as PlaceKind | "all", label: t("All") },
                { value: "desk" as PlaceKind | "all", label: t("Desks") },
                { value: "meeting_room" as PlaceKind | "all", label: t("Meeting rooms") },
              ]}
              className="my-2 w-full"
            />
            {features.length > 0 && (
              <div className="mt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
                  {t("Equipment")}
                </p>
                <FeatureFilter features={features} value={value.features} onChange={(f) => patch({ features: f })} />
              </div>
            )}
          </div>
        )}
      </div>
      {chips.length > 0 && (
        <ul className="order-last flex w-full basis-full flex-wrap items-center gap-2">
          {chips.map((c) => (
            <li key={c.key}>
              <button
                type="button"
                onClick={c.remove}
                aria-label={t("Remove {{name}}", { name: c.label })}
                className="group flex min-h-[44px] items-center"
              >
                <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-500 bg-brand-100 py-1 pl-3 pr-2 text-sm font-medium text-slate-900 transition-colors duration-150 group-hover:bg-brand-200">
                  {c.label}
                  <X aria-hidden className="h-3.5 w-3.5" />
                </span>
              </button>
            </li>
          ))}
          {chips.length >= 2 && (
            <li>
              <button
                type="button"
                onClick={() => onChange({ ...EMPTY_FILTER })}
                className="min-h-[44px] rounded-full px-3 text-sm font-medium text-slate-700 underline underline-offset-2 hover:text-slate-900 dark:text-slate-200 dark:hover:text-white"
              >
                {t("Reset filters")}
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
