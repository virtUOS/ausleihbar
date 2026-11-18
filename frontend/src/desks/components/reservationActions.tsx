// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Clock } from "lucide-react";
import { useConfirm } from "../../components/ConfirmDialog";
import { useToast } from "../../components/Toast";
import { desksApi } from "../api";
import type { Reservation } from "../types";
import { lateOptionLabel, lateOptions, pickLate, type LateOption } from "../late";

export const btn =
  "min-h-[44px] rounded-full border border-slate-300 px-4 text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800";
export const btnIcon = `${btn} inline-flex h-11 w-11 items-center justify-center !px-0`;
export const btnPrimary =
  "min-h-[44px] rounded-full bg-brand-500 px-4 text-sm font-semibold text-slate-900 transition-colors duration-150 hover:bg-brand-400 disabled:opacity-50";

export type Run = (action: () => Promise<unknown>, success: string, after?: () => void) => Promise<void>;

/** What an action did to the reservation (callers may react, e.g. hide it). */
export type ActionDone = "checked_in" | "deleted" | "late" | "other";

/** The reported late arrival while it still lies ahead, else null. */
export function activeLateUntil(r: Reservation, now: number): string | null {
  return r.late_until && new Date(r.late_until).getTime() > now ? r.late_until : null;
}

/** The holder's actions on one own reservation (check in, late, delete),
 *  shared by the reservation card and the check-in banner. `now` is the
 *  caller's minute clock (late options are relative to it). */
export function useReservationActions(r: Reservation, now: number, onChanged: (done: ActionDone) => void) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [lateOpen, setLateOpen] = useState(false);
  const [lateMinutes, setLateMinutes] = useState<number | null>(null);
  const options = lateOptions(r.start, r.end, new Date(now));
  const selectedLate = pickLate(options, lateMinutes)?.minutes;

  const runAs = async (done: ActionDone, action: () => Promise<unknown>, success: string, after?: () => void) => {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      setLateOpen(false);
      after?.();
      onChanged(done);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("The request failed."));
    } finally {
      setBusy(false);
    }
  };
  const run: Run = (action, success, after) => runAs("other", action, success, after);

  const checkIn = () => runAs("checked_in", () => desksApi.checkIn(r.id), t("Checked in."));

  async function remove() {
    const ok = await confirm({
      title: t("Delete booking?"),
      message: t("Delete {{place}}? The place becomes free for others.", { place: r.place.name }),
      confirmLabel: t("Delete"),
      cancelLabel: t("Keep"),
      danger: true,
    });
    if (!ok) return;
    await runAs("deleted", () => desksApi.cancelReservation(r.id), t("Booking deleted."));
  }

  function saveLate() {
    // Recompute at click time: the options are relative to "now", which may
    // have moved since the panel was rendered.
    const option = pickLate(lateOptions(r.start, r.end, new Date()), selectedLate);
    if (!option) {
      toast.error(t("The request failed."));
      return;
    }
    return runAs("late", () => desksApi.later(r.id, option.until), t("Noted. We keep your place."));
  }

  return {
    busy,
    run,
    checkIn,
    remove,
    late: { open: lateOpen, setOpen: setLateOpen, options, selected: selectedLate, select: setLateMinutes, save: saveLate },
  };
}

export type ReservationActions = ReturnType<typeof useReservationActions>;

/** "I'll be late": the clock toggle and, when open, the time chips and Save. */
export function LateControls({ actions, onToggle }: { actions: ReservationActions; onToggle?: (open: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const { busy, late } = actions;
  if (late.options.length === 0) return null;
  const label = (o: LateOption) => lateOptionLabel(o, t, i18n.language);
  return (
    <>
      <button
        type="button"
        aria-expanded={late.open}
        aria-label={t("I'll be late")}
        title={t("I'll be late")}
        onClick={() => {
          late.setOpen(!late.open);
          onToggle?.(!late.open);
        }}
        className={btnIcon}
      >
        <Clock aria-hidden className="h-5 w-5" />
      </button>
      {late.open && (
        <>
          {late.options.map((o) => (
            <button
              key={o.minutes}
              type="button"
              aria-pressed={o.minutes === late.selected}
              onClick={() => late.select(o.minutes)}
              className={`${btn} ${o.minutes === late.selected ? "!border-brand-500 !bg-brand-100 dark:!bg-brand-900/50" : ""}`}
            >
              {label(o)}
            </button>
          ))}
          <button type="button" disabled={busy} onClick={late.save} className={btnPrimary}>
            {t("Save")}
          </button>
        </>
      )}
    </>
  );
}
