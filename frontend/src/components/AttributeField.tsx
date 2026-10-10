// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { EyeOff } from "lucide-react";
import { TranslatableField } from "@basicbar/ui";
import { localizedText } from "@basicbar/ui";
import type { AttributeDef } from "../types";

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

/** Inline marker next to an attribute label: this attribute is not shown to
 *  borrowers in the shop (#54). Sits on the label line so the form grid keeps
 *  its row alignment; visible attributes get no marker (visible is the norm). */
export function HiddenInShopBadge() {
  const { t } = useTranslation();
  return (
    <span className="ml-1.5 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-slate-100 px-1.5 align-middle text-[10px] font-medium leading-4 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
      <EyeOff aria-hidden className="h-3 w-3" />
      {t("Not visible in the shop")}
    </span>
  );
}

/** One attribute input, rendered by type (product form, device form). */
export function AttributeField({
  attr,
  value,
  onChange,
}: {
  attr: AttributeDef;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const hiddenBadge =
    (attr.scope ?? "product") === "product" && !attr.visible ? (
      <HiddenInShopBadge />
    ) : undefined;
  if (attr.type === "short_text" || attr.type === "long_text") {
    // A legacy value may still be a plain string (pre-bilingual data) — treat
    // it as the German value so it keeps displaying.
    const obj =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, string>)
        : { de: value == null ? "" : String(value), en: "" };
    return (
      <TranslatableField
        label={localizedText(attr.label) || attr.key}
        required={attr.required}
        multiline={attr.type === "long_text"}
        values={{ de: obj.de ?? "", en: obj.en ?? "" }}
        onChange={(lang, text) => onChange({ ...obj, [lang]: text })}
        inputClass={inputClass}
        labelAddon={hiddenBadge}
      />
    );
  }
  const str = value == null ? "" : String(value);
  const common = {
    value: str,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange(e.target.value),
    className: `mt-1 ${inputClass}`,
  };
  const typeMap: Record<string, string> = {
    number: "number",
    date: "date",
    time: "time",
    url: "url",
  };

  return (
    <label className="block text-xs text-slate-600 dark:text-slate-300">
      {localizedText(attr.label) || attr.key}
      {attr.required && <span className="text-red-500"> *</span>}
      {hiddenBadge}
      <input type={typeMap[attr.type] ?? "text"} {...common} />
    </label>
  );
}
