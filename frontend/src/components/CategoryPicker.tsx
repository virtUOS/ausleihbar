// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { categoryTree, pathLabel } from "../categories";
import { useFetch } from "../useFetch";
import type { ManageCategory } from "../types";
import { MultiSelectList, type Option } from "./MultiSelectList";

/** The categories a product or set can be placed in: those reachable in the
 *  shop (not below a trashed one), labelled with their path ("Kameras ›
 *  Video"). `loaded` is false until the tree arrived. */
export function usePickableCategories() {
  const categories = useFetch<ManageCategory[]>(() => api.listManagedCategories(), []);
  const options = useMemo<Option[]>(
    () =>
      categoryTree(categories.data ?? []).ordered.map((c) => ({
        id: c.id,
        label: pathLabel(c),
      })),
    [categories.data],
  );
  const pickableIds = useMemo(() => new Set(options.map((o) => o.id)), [options]);
  return { options, pickableIds, loaded: categories.data !== null };
}

/** Searchable checkbox list of categories (product and set forms). Only
 *  pickable categories are shown as selected; the backend keeps links to
 *  trashed or hidden ones by itself. */
export function CategoryPicker({
  options,
  pickableIds,
  selected,
  onToggle,
}: {
  options: Option[];
  pickableIds: Set<number>;
  selected: number[];
  onToggle: (id: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <MultiSelectList
      options={options}
      selected={selected.filter((id) => pickableIds.has(id))}
      onToggle={onToggle}
      placeholder={t("Search categories…")}
      emptyText={t("No categories available.")}
    />
  );
}
