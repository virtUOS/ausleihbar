// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { formatPeriod } from "../manage";
import { formatTime } from "../dates";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";
import { checkinErrorMessage } from "../components/CheckinBadge";
import { EndUseButton, useConfirmEndUse } from "../components/EndUseButton";
import { useToast } from "../components/Toast";
import type { QrCheckinState } from "../types";

/**
 * Landing page for a device QR sticker (`/r/<qr_id>`). A normal QR reader opens
 * this; we resolve the unit to its product and forward to the product page so
 * the borrower finds details / manuals (concept §6.2). Signed-in borrowers with
 * a booking for an item that needs a check-in see the check-in card instead.
 */
export function ResourceRedirectPage() {
  const { t } = useTranslation();
  const { qrId } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading, login } = useAuth();
  const signedIn = !!user?.authenticated;
  const { data, error } = useFetch(
    () => api.resolveResourceByQr(qrId!),
    [qrId],
  );
  const [version, setVersion] = useState(0);
  // Own booking state at this unit (signed-in only); a failure falls back to the redirect.
  const checkin = useFetch<QrCheckinState | null>(
    () => (signedIn ? api.qrCheckinState(qrId!).catch(() => null) : Promise.resolve(null)),
    [qrId, signedIn, version],
  );

  const showCard =
    signedIn && !!checkin.data && (!!checkin.data.item || !!checkin.data.other_unit);
  const showLogin = !authLoading && !signedIn && !!data?.checkin_required;
  const ready = !!data && !authLoading && (!signedIn || !checkin.loading);

  useEffect(() => {
    if (ready && data && !showCard && !showLogin) {
      navigate(`/products/${data.product}`, { replace: true });
    }
  }, [ready, data, showCard, showLogin, navigate]);

  if (error)
    return (
      <div className="py-10 text-center">
        <ErrorBox message={t("This item QR code isn't recognized.")} />
        <Link to="/" className="text-sm text-slate-600 dark:text-slate-300 underline">
          {t("Go to lending")}
        </Link>
      </div>
    );
  if (!ready) return <Loading />;
  if (showLogin && data)
    return (
      <div className="mx-auto max-w-md py-10 text-center">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {data.product_title}
        </h1>
        <button
          type="button"
          onClick={login}
          className="mt-4 rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500"
        >
          {t("Sign in to check in")}
        </button>
        <div>
          <Link
            to={`/products/${data.product}`}
            className="mt-4 inline-block text-sm text-slate-600 underline dark:text-slate-300"
          >
            {t("To the product page")}
          </Link>
        </div>
      </div>
    );
  if (showCard && checkin.data)
    return (
      <CheckinCard
        qrId={qrId!}
        state={checkin.data}
        onChanged={() => setVersion((v) => v + 1)}
      />
    );
  return <Loading />;
}

function CheckinCard({
  qrId,
  state,
  onChanged,
}: {
  qrId: string;
  state: QrCheckinState;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const confirmEndUse = useConfirmEndUse();
  const [busy, setBusy] = useState(false);
  const item = state.item;

  async function checkIn() {
    if (!item) return;
    setBusy(true);
    try {
      await api.qrCheckIn(qrId, item.id);
      toast.success(t("Checked in."));
    } catch (e) {
      toast.error(checkinErrorMessage(e, t));
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function endUse() {
    if (!item || !(await confirmEndUse(state.product_title))) return;
    setBusy(true);
    try {
      await api.endBookingUse(item.booking_id, item.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  const status = item?.checkin_state;
  return (
    <div className="mx-auto max-w-md py-10">
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {state.product_title}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">{state.inventory_number}</p>
        {item ? (
          <div className="mt-3 space-y-2 text-sm text-slate-700 dark:text-slate-200">
            <p>{formatPeriod(item.start, item.end, "hours")}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t("Booking {{code}}", { code: item.code })}
            </p>
            {status === "late" && (
              <p role="status" className="font-medium text-amber-700 dark:text-amber-300">
                {t("Not started for {{count}} min – release at {{time}}", {
                  count: item.late_minutes ?? 0,
                  time: formatTime(item.checkin_deadline),
                })}
              </p>
            )}
            {status === "upcoming" && (
              <p role="status">{t("Check-in opens 15 minutes before the start.")}</p>
            )}
            {(status === "released" || status === "expired") && (
              <p role="status" className="font-medium text-red-700 dark:text-red-300">
                {t("Not used")}
              </p>
            )}
            {(status === "open" || status === "late") && !item.can_check_in && (
              <p role="status">
                {item.checkin_error === "not_confirmed"
                  ? t("Your booking is not confirmed yet.")
                  : t("Check-in is not possible right now.")}
              </p>
            )}
            {status === "checked_in" && (
              <p role="status" className="font-medium text-green-700 dark:text-green-300">
                {t("Checked in.")}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3 pt-1">
              {(status === "open" || status === "late") && item.can_check_in && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={checkIn}
                  className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
                >
                  {t("Check in")}
                </button>
              )}
              {item.can_end_use && <EndUseButton disabled={busy} onClick={endUse} />}
            </div>
          </div>
        ) : (
          state.other_unit && (
            <p role="status" className="mt-3 text-sm text-slate-700 dark:text-slate-200">
              {t("Your booking is for {{number}}.", { number: state.other_unit.inventory_number })}
            </p>
          )
        )}
        <Link
          to={`/products/${state.product}`}
          className="mt-4 inline-block text-sm text-slate-600 underline dark:text-slate-300"
        >
          {t("To the product page")}
        </Link>
      </div>
    </div>
  );
}
