// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { PersonPicker } from "../components/PersonPicker";
import type { PersonChoice } from "../types";

type Whom = "me" | "other";

/** "For me | For another person" (assistants and department admins): the
 *  second option reveals the person search. Switching back to "for me"
 *  books for oneself again. */
export function ForWhom({
  pool,
  value,
  onChange,
}: {
  pool: number;
  value: PersonChoice | null;
  onChange: (person: PersonChoice | null) => void;
}) {
  const { t } = useTranslation();
  const [whom, setWhom] = useState<Whom>(value ? "other" : "me");
  return (
    <div className="flex flex-col gap-3">
      <SegmentedControl
        size="md"
        ariaLabel={t("Book for whom")}
        value={whom}
        onChange={(next: Whom) => {
          setWhom(next);
          if (next === "me") onChange(null);
        }}
        options={[
          { value: "me" as Whom, label: t("For me") },
          { value: "other" as Whom, label: t("For another person") },
        ]}
        className="w-full sm:w-max"
      />
      {whom === "other" && (
        <div className="max-w-md">
          <PersonPicker pool={pool} value={value} onChange={onChange} label={t("Person")} />
          {value && (
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              {t("Free places are shown for {{name}}.", { name: value.name })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
