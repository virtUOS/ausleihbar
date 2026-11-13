// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { TranslatableField, getDefaultContentLang } from "@basicbar/ui";
import { useTranslation } from "react-i18next";
import { inputCls } from "./formStyles";

/** Name in German and English (the project's content-translation pattern:
 *  `name_de` is required, `name_en` optional). */
export function NameField({
  de,
  en,
  onChange,
}: {
  de: string;
  en: string;
  onChange: (lang: "de" | "en", value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <TranslatableField
      label={t("Name")}
      required
      values={{ de, en }}
      onChange={(lang, v) => onChange(lang as "de" | "en", v)}
      inputClass={inputCls}
    />
  );
}

/** True when the name is filled in the project's default content language
 *  (the language the backend requires). */
export function hasDefaultName(de: string, en: string): boolean {
  return (getDefaultContentLang() === "en" ? en : de).trim() !== "";
}
