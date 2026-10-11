// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { RESOURCE_STATUSES } from "../types";
import type { ManageResource, ManageResourceInput } from "../types";
import { statusLabel } from "./ResourceForm";

const STATUS_BADGE: Record<string, string> = {
  available: "text-green-700 dark:text-green-300",
  blocked: "text-amber-600 dark:text-amber-300",
  defective: "text-red-600 dark:text-red-300",
  retired: "text-slate-400 dark:text-slate-300",
};

/** Inline status editor for the inventory table. Marking a working unit
 *  defective runs the rebooking/notify flow (and asks for a note); returning a
 *  repaired unit to service uses the repair flow; other changes are a plain
 *  status update. */
export function ResourceStatusCell({
  resource,
  onChanged,
}: {
  resource: ManageResource;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  async function change(next: string) {
    if (next === resource.status) return;
    setBusy(true);
    try {
      if (next === "defective" && resource.status === "available") {
        const note = window.prompt(
          t("Mark defective — what's wrong? (optional)"),
          "",
        );
        if (note === null) return; // cancelled
        const res = await api.markResourceDefective(resource.id, note.trim());
        if (res.unfulfilled) {
          window.alert(
            t(
              "{{rebooked}} booking(s) moved; {{unfulfilled}} could not be moved — those borrowers were notified.",
              { rebooked: res.rebooked, unfulfilled: res.unfulfilled },
            ),
          );
        }
      } else if (next === "available" && resource.status === "defective") {
        await api.markResourceAvailable(resource.id);
      } else {
        await api.updateResource(resource.id, {
          status: next as ManageResourceInput["status"],
          defect_note: next === "defective" ? resource.defect_note : "",
        });
      }
      onChanged();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : t("Save failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={resource.status}
        disabled={busy}
        onChange={(e) => change(e.target.value)}
        aria-label={t("Status")}
        className={`rounded-md border border-slate-300 bg-white px-1.5 py-0.5 text-sm font-medium disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 ${
          STATUS_BADGE[resource.status] ?? ""
        }`}
      >
        {RESOURCE_STATUSES.map((s) => (
          <option key={s} value={s}>
            {statusLabel(s)}
          </option>
        ))}
      </select>
      {resource.status === "defective" && resource.defect_note && (
        <span className="text-xs font-normal text-slate-400 dark:text-slate-300">
          ({resource.defect_note})
        </span>
      )}
    </div>
  );
}
