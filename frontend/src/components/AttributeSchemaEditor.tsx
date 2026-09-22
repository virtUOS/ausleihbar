// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import { ATTRIBUTE_TYPES } from "../types";
import type { AttributeDef, AttributeType } from "../types";
import { TranslatableField } from "@basicbar/ui";
import { localizedMap, localizedText, setLocalizedLang } from "@basicbar/ui";

const inputClass =
  "w-full rounded-md border border-slate-300 dark:border-slate-600 px-2 py-1 text-sm text-slate-900 dark:text-slate-100";

const TYPE_LABELS: Record<AttributeType, string> = {
  short_text: i18n.t("Short text"),
  long_text: i18n.t("Long text"),
  date: i18n.t("Date"),
  time: i18n.t("Time"),
  number: i18n.t("Number"),
  url: i18n.t("URL"),
  media: i18n.t("Media"),
  image: i18n.t("Image"),
  pdf: i18n.t("PDF document"),
};

/** Editor for a product type's dynamic attribute schema (a list of fields). */
export function AttributeSchemaEditor({
  value,
  onChange,
  removeWarnings = {},
}: {
  value: AttributeDef[];
  onChange: (next: AttributeDef[]) => void;
  /** Per-key count of products that have filled the attribute (§5.2 warning). */
  removeWarnings?: Record<string, number>;
}) {
  const { t } = useTranslation();
  // Index awaiting confirmation because removing it would discard filled values.
  const [pendingRemove, setPendingRemove] = useState<number | null>(null);

  function update(index: number, patch: Partial<AttributeDef>) {
    onChange(value.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  }

  function remove(index: number) {
    onChange(value.filter((_, i) => i !== index));
    setPendingRemove(null);
  }

  function requestRemove(index: number) {
    if ((removeWarnings[value[index].key] ?? 0) > 0) setPendingRemove(index);
    else remove(index);
  }

  function add() {
    onChange([
      ...value,
      {
        key: "",
        label: "",
        type: "short_text",
        default: "",
        visible: true,
        required: false,
      },
    ]);
  }

  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <p className="text-xs text-slate-400 dark:text-slate-300">{t("No attributes yet.")}</p>
      )}
      {value.map((attr, index) => (
        <div
          key={index}
          className="rounded-lg border border-slate-200 dark:border-slate-800 p-3"
        >
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <label className="text-xs text-slate-600 dark:text-slate-300">
              {t("Key")}
              <input
                value={attr.key}
                onChange={(e) => update(index, { key: e.target.value })}
                placeholder="serial_number"
                className={`mt-1 ${inputClass}`}
              />
            </label>
            <TranslatableField
              label={t("Label")}
              values={localizedMap(attr.label)}
              onChange={(lang, v) =>
                update(index, { label: setLocalizedLang(attr.label, lang, v) })
              }
              inputClass={inputClass}
            />
            <label className="text-xs text-slate-600 dark:text-slate-300">
              {t("Type")}
              <select
                value={attr.type}
                onChange={(e) =>
                  update(index, { type: e.target.value as AttributeType })
                }
                className={`mt-1 ${inputClass}`}
              >
                {ATTRIBUTE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-slate-600 dark:text-slate-300">
              {t("Default")}
              <input
                value={String(attr.default ?? "")}
                onChange={(e) => update(index, { default: e.target.value })}
                className={`mt-1 ${inputClass}`}
              />
            </label>
          </div>
          <div className="mt-2 flex items-center gap-4">
            <label className="flex items-center gap-1 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox"
                checked={attr.visible}
                onChange={(e) => update(index, { visible: e.target.checked })}
              />
              {t("Visible to borrowers")}
            </label>
            <label className="flex items-center gap-1 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox"
                checked={attr.required}
                onChange={(e) => update(index, { required: e.target.checked })}
              />
              {t("Required")}
            </label>
            <button
              type="button"
              onClick={() => requestRemove(index)}
              className="ml-auto text-sm text-red-600 dark:text-red-400 hover:underline"
            >
              {t("Remove")}
            </button>
          </div>
          {pendingRemove === index && (
            <div className="mt-2 rounded-md border border-amber-300 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 p-2 text-sm text-amber-800 dark:text-amber-300">
              <p>
                <span className="font-medium">{localizedText(attr.label) || attr.key}</span>{" "}
                {t(
                  "is filled on {{count}} product — removing it discards those values.",
                  { count: removeWarnings[attr.key] },
                )}
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => remove(index)}
                  className="rounded-full bg-amber-600 px-3 py-1 text-sm font-semibold text-white"
                >
                  {t("Remove anyway")}
                </button>
                <button
                  type="button"
                  onClick={() => setPendingRemove(null)}
                  className="rounded-full border border-slate-300 dark:border-slate-600 px-3 py-1 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  {t("Keep")}
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="rounded-full border border-slate-300 dark:border-slate-600 px-3 py-1 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
      >
        {t("+ Add attribute")}
      </button>
    </div>
  );
}
