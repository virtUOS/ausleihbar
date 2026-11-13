// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { usePrompt } from "../../components/PromptDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import { pad2 } from "../weekdays";
import { MovePanel } from "./ReservationCard";
import type { ManageReservation } from "../types";

const btn =
  "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";

/** Whether a department admin can still act on someone else's reservation. */
export function isManageable(r: ManageReservation, now = Date.now()): boolean {
  return !r.mine && r.status === "active" && new Date(r.end).getTime() > now;
}

/** The holder as admins see it: the name, or "Person (verborgen)". */
export function useHolderText() {
  const { t } = useTranslation();
  return (r: ManageReservation) => r.holder_name ?? t("Person (hidden)");
}

/** Department admins: move someone else's reservation to a free place of
 *  the same kind, or cancel it with a reason (the holder is notified). They
 *  act on the reservation id only; a hidden holder stays hidden. */
export function AdminReservationActions({
  reservation: r,
  onChanged,
}: {
  reservation: ManageReservation;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const askText = usePrompt();
  const toast = useToast();
  const [moving, setMoving] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      setMoving(false);
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    const reason = await askText({
      title: t("Cancel reservation"),
      message: t(
        "Cancel {{place}} ({{time}})? The holder is notified with your reason.",
        { place: r.place.name, time: `${pad2(r.start_hour)}:00–${pad2(r.end_hour)}:00` },
      ),
      label: t("Reason"),
      required: true,
      multiline: true,
      danger: true,
      confirmLabel: t("Cancel reservation"),
      cancelLabel: t("Keep"),
    });
    if (reason === null) return;
    await run(() => desksApi.cancelReservation(r.id, reason), t("Reservation cancelled."));
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          aria-expanded={moving}
          disabled={busy}
          onClick={() => setMoving(!moving)}
          className={btn}
        >
          {t("Move")}
        </button>
        <button type="button" disabled={busy} onClick={cancel} className={btn}>
          {t("Cancel reservation")}
        </button>
      </div>
      {moving && <MovePanel r={r} busy={busy} run={(action, success) => run(action, success)} />}
    </div>
  );
}
