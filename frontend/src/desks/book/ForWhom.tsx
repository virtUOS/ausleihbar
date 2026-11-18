// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { PersonPicker } from "../components/PersonPicker";
import type { PersonChoice } from "../types";

type Whom = "me" | "other";

/** "For me | For another person" (assistants and department admins): the
 *  second option reveals the person search; the page shows the next steps
 *  only once a person is chosen. "For me" books for oneself again. */
export function ForWhom({
  pool,
  other,
  onOther,
  value,
  onChange,
}: {
  pool: number;
  /** "For another person" is chosen. */
  other: boolean;
  onOther: (other: boolean) => void;
  value: PersonChoice | null;
  onChange: (person: PersonChoice | null) => void;
}) {
  const { t } = useTranslation();
  const whom: Whom = other ? "other" : "me";
  return (
    <div className="flex flex-col gap-3">
      <SegmentedControl
        size="md"
        ariaLabel={t("Book for whom")}
        value={whom}
        onChange={(next: Whom) => onOther(next === "other")}
        options={[
          { value: "me" as Whom, label: t("For me") },
          { value: "other" as Whom, label: t("For another person") },
        ]}
        className="w-full sm:w-max"
      />
      {whom === "other" && (
        <div className="max-w-md">
          <PersonPicker pool={pool} value={value} onChange={onChange} label={t("Person")} />
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {value
              ? t("Free places are shown for {{name}}.", { name: value.name })
              : t("Choose the person first; the next steps follow.")}
          </p>
        </div>
      )}
    </div>
  );
}
