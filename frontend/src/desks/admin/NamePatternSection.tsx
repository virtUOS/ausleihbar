// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@basicbar/ui";
import { ErrorBox, Loading } from "../../components/Status";
import { useToast } from "../../components/Toast";
import { useFetch } from "../../useFetch";
import { desksApi } from "../api";
import { primaryBtn, sectionTitleCls } from "../components/formStyles";
import type { DeskAdminSetting } from "../types";

/**
 * The campus-wide place name pattern (app admins, settings tab): new place
 * names continue the room's name with letters ("15/201 A") or numbers
 * ("15/201-1").
 */
export function NamePatternSection() {
  const { t } = useTranslation();
  const setting = useFetch(() => desksApi.adminSetting(), []);
  return (
    <section aria-labelledby="set-name-pattern">
      <h2 id="set-name-pattern" className={sectionTitleCls}>
        {t("Place name pattern")}
      </h2>
      <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
        {t("Applies to all pools.")} {t("New places continue the room's name.")}
      </p>
      {setting.error ? (
        <ErrorBox message={setting.error} />
      ) : !setting.data ? (
        <Loading />
      ) : (
        <NamePatternForm initial={setting.data.place_name_pattern} />
      )}
    </section>
  );
}

function NamePatternForm({ initial }: { initial: DeskAdminSetting["place_name_pattern"] }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [saved, setSaved] = useState(initial);
  const [pattern, setPattern] = useState(initial);
  const [busy, setBusy] = useState(false);
  const example = pattern === "letter" ? "15/201 A, 15/201 B, 15/201 C" : "15/201-1, 15/201-2, 15/201-3";
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          const result = await desksApi.saveAdminSetting({ place_name_pattern: pattern });
          setSaved(result.place_name_pattern);
          toast.success(t("Name pattern saved."));
        } catch (err) {
          toast.error(err instanceof Error ? err.message : t("The request failed."));
        } finally {
          setBusy(false);
        }
      }}
      className="flex flex-col gap-3"
    >
      <SegmentedControl
        size="md"
        ariaLabel={t("Place name pattern")}
        value={pattern}
        onChange={(v) => setPattern(v)}
        options={[
          { value: "letter" as const, label: t("Letters") },
          { value: "number" as const, label: t("Numbers") },
        ]}
        className="w-full sm:w-max"
      />
      <p className="text-sm text-slate-800 dark:text-slate-200">{t("Example: {{names}}", { names: example })}</p>
      <div>
        <button type="submit" disabled={busy || pattern === saved} className={primaryBtn}>
          {t("Save")}
        </button>
      </div>
    </form>
  );
}
