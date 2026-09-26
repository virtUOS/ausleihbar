// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { ErrorBox, Loading } from "../components/Status";
import { TranslatableField } from "@basicbar/ui";
import type { NotificationSetting } from "../types";

const inputClass =
  "block w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100";

type Variant =
  | "received"
  | "confirmed"
  | "rescheduled"
  | "cancellation"
  | "reminder"
  | "defect";

type Form = Record<string, string>;

// The single-paragraph mails (each gets one optional "additional paragraph").
const NOTE_FIELDS = [
  "rescheduled_note",
  "cancellation_note",
  "reminder_note",
  "defect_note",
] as const;

const ALL_FIELDS = [
  "reservation_intro",
  "reservation_footer",
  ...NOTE_FIELDS,
] as const;

const EMPTY: Form = {
  ...Object.fromEntries(
    ALL_FIELDS.flatMap((f) => [
      [`${f}_de`, ""],
      [`${f}_en`, ""],
    ]),
  ),
  confirmation_send_time: "17:00",
};

export function AdminNotificationsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const setting = useFetch<NotificationSetting>(() => api.getNotificationSetting(), []);
  const [form, setForm] = useState<Form>(EMPTY);
  const [preview, setPreview] = useState<Variant>("received");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!setting.data) return;
    const data = setting.data as unknown as Record<string, string | null>;
    setForm({
      ...Object.fromEntries(
        ALL_FIELDS.flatMap((f) => [
          [`${f}_de`, data[`${f}_de`] ?? ""],
          [`${f}_en`, data[`${f}_en`] ?? ""],
        ]),
      ),
      confirmation_send_time: (data.confirmation_send_time ?? "17:00:00").slice(0, 5),
    });
  }, [setting.data]);

  if (user && !user.is_staff) {
    return (
      <div className="py-10 text-center text-slate-600 dark:text-slate-300">
        {t("Not authorized.")}
      </div>
    );
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      // Guard against sending "" for the send-time (M5): a cleared/invalid
      // time input must fall back to the last known value rather than wipe
      // the setting (the `required` attribute below also blocks this in
      // supporting browsers).
      const fallback = (setting.data?.confirmation_send_time ?? "17:00:00").slice(0, 5);
      const payload = {
        ...form,
        confirmation_send_time: form.confirmation_send_time || fallback,
      };
      await api.updateNotificationSetting(payload);
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Save failed.") });
    } finally {
      setBusy(false);
    }
  }

  const set = (field: string, lang: string, v: string) =>
    setForm((f) => ({ ...f, [`${field}_${lang}`]: v }));

  const noteField = (
    field: string,
    label: string,
    placeholder: string,
  ) => (
    <TranslatableField
      key={field}
      label={label}
      values={{ de: form[`${field}_de`], en: form[`${field}_en`] }}
      onChange={(lang, v) => set(field, lang, v)}
      inputClass={inputClass}
      renderInput={({ value, onChange, id }) => (
        <textarea
          id={id}
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={inputClass}
        />
      )}
    />
  );

  const sectionMeta: { field: (typeof NOTE_FIELDS)[number]; variant: Variant; title: string; placeholder: string }[] = [
    {
      field: "rescheduled_note",
      variant: "rescheduled",
      title: t("When a booking is rescheduled (closure)"),
      placeholder: t("e.g. Sorry for the short notice — reply if the new date doesn't work."),
    },
    {
      field: "cancellation_note",
      variant: "cancellation",
      title: t("When a booking is cancelled (closure)"),
      placeholder: t("e.g. We're happy to help you find another slot."),
    },
    {
      field: "reminder_note",
      variant: "reminder",
      title: t("Overdue reminder"),
      placeholder: t("e.g. Late returns may lead to a strike."),
    },
    {
      field: "defect_note",
      variant: "defect",
      title: t("When a reserved device is unavailable"),
      placeholder: t("e.g. We apologise for the inconvenience."),
    },
  ];

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
        {t("Administration")}
      </h1>
      <AdminTabs />
      <h2 className="mb-1 mt-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {t("Notifications")}
      </h2>
      <p className="mb-4 max-w-2xl text-xs text-slate-600 dark:text-slate-300">
        {t(
          "Custom text for the borrower emails. The personal salutation, the booking number, the booking details and the link are always kept — your text is woven in around them. All fields are optional; leave a language empty to use the built-in default. Pool-specific hints (e.g. eligibility) are set per pool and appear in that pool's section.",
        )}
      </p>

      {setting.loading && <Loading />}
      {setting.error && <ErrorBox message={setting.error} />}

      {setting.data && (
        <div className="grid items-start gap-5 lg:grid-cols-2">
          <form
            onSubmit={save}
            className="space-y-5 rounded-xl border border-slate-200 p-4 dark:border-slate-800 dark:bg-slate-900"
          >
            <fieldset className="space-y-1">
              <label
                htmlFor="confirmation_send_time"
                className="text-sm font-semibold text-slate-900 dark:text-slate-100"
              >
                {t("Send time for held confirmations")}
              </label>
              <p className="text-xs text-slate-600 dark:text-slate-300">
                {t(
                  "Orders with several pools: partial confirmations are collected and sent at this time.",
                )}
              </p>
              <input
                id="confirmation_send_time"
                type="time"
                required
                value={form.confirmation_send_time}
                onChange={(e) =>
                  setForm((f) => ({ ...f, confirmation_send_time: e.target.value }))
                }
                className={`mt-1 w-32 ${inputClass}`}
              />
            </fieldset>

            <fieldset className="space-y-4 border-t border-slate-100 pt-4 dark:border-slate-800">
              <legend className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {t("When a reservation is submitted")}
              </legend>
              {noteField(
                "reservation_intro",
                t("Intro text (replaces the default opening line)"),
                t("e.g. Thank you for your reservation — we'll be in touch soon."),
              )}
              {noteField(
                "reservation_footer",
                t("Closing text (shown before the signature)"),
                t("e.g. If you have any questions, just reply to this email."),
              )}
            </fieldset>

            {sectionMeta.map((s) => (
              <fieldset
                key={s.field}
                className="space-y-4 border-t border-slate-100 pt-4 dark:border-slate-800"
              >
                <legend className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {s.title}
                </legend>
                {noteField(
                  s.field,
                  t("Additional paragraph (shown before the signature)"),
                  s.placeholder,
                )}
              </fieldset>
            ))}

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={busy}
                className="rounded-full bg-brand-400 px-4 py-2 text-sm font-bold text-slate-900 transition-colors duration-150 hover:bg-brand-500 disabled:opacity-40"
              >
                {busy ? t("Saving…") : t("Save")}
              </button>
              {message && (
                <span
                  className={`text-sm ${
                    message.ok
                      ? "text-green-700 dark:text-green-300"
                      : "text-red-600 dark:text-red-400"
                  }`}
                >
                  {message.text}
                </span>
              )}
            </div>
          </form>

          <div>
            <div className="mb-2 flex flex-wrap gap-1" role="tablist" aria-label={t("Preview")}>
              {(
                [
                  ["received", t("Reservation received")],
                  ["confirmed", t("Confirmation")],
                  ["rescheduled", t("Rescheduled")],
                  ["cancellation", t("Cancelled")],
                  ["reminder", t("Reminder")],
                  ["defect", t("Device defective")],
                ] as [Variant, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={preview === key}
                  onClick={() => setPreview(key)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    preview === key
                      ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                      : "border border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <MailPreview variant={preview} de={form} />
          </div>
        </div>
      )}
    </div>
  );
}

type Seg = { kind: "auto" | "yours" | "pool" | "perConfirm"; text: string };

const SALUTATION = "Hallo Erika Mustermann,";
const POOL_BLOCK =
  "Abholung bei DigiLab · Raum 1.01\n\n  • Sony Alpha 7 IV (DigiLab-0101)\n      Di 15. Juli 2026\n\n  Adresse:\n    Musterstraße 1\n    49074 Osnabrück\n\n  Kontakt: 0541 969-0";
const POOL_NOTE = "Dieser Pool steht nur Studierenden des Fachs XY zur Verfügung.";
const LINK = "Deine Buchungen ansehen: https://ausleihbar.example.org/bookings";
const SIGN = "— Ausleihbar";
const CONTACT_BLOCK =
  "Bitte kontaktiere den Verleih-Pool, um eine Alternative zu vereinbaren:\n  DigiLab — 0541 969-0";

/** Illustrative German preview of a borrower email. `de` holds the German form
 *  values; the preview colour-codes where each part comes from. Not byte-exact. */
function MailPreview({ variant, de }: { variant: Variant; de: Form }) {
  const { t } = useTranslation();
  const styles: Record<Seg["kind"], string> = {
    auto: "text-slate-600 dark:text-slate-300",
    yours:
      "rounded bg-brand-100 px-1 text-slate-900 dark:bg-brand-400/25 dark:text-slate-100",
    pool: "rounded bg-sky-100 px-1 text-sky-900 dark:bg-sky-500/25 dark:text-sky-100",
    perConfirm:
      "rounded bg-violet-100 px-1 text-violet-900 dark:bg-violet-500/25 dark:text-violet-100",
  };
  // Solid legend dots (not the inline highlight styles, which look like boxes).
  const dot: Record<Seg["kind"], string> = {
    auto: "bg-slate-300 dark:bg-slate-600",
    yours: "bg-brand-400",
    pool: "bg-sky-400 dark:bg-sky-500",
    perConfirm: "bg-violet-400 dark:bg-violet-500",
  };
  const yours = (field: string): Seg | null => {
    const v = (de[`${field}_de`] ?? "").trim();
    return v ? { kind: "yours", text: v } : null;
  };

  const segs: (Seg | null)[] = (() => {
    switch (variant) {
      case "received":
        return [
          { kind: "auto", text: SALUTATION },
          yours("reservation_intro") ?? {
            kind: "auto",
            text: "wir haben deine Reservierung erhalten. Sie ist vorgemerkt und das Verleihteam bestätigt sie in Kürze.",
          },
          { kind: "auto", text: "Reservierungsnummer: R-00123" },
          { kind: "auto", text: POOL_BLOCK },
          { kind: "pool", text: POOL_NOTE },
          { kind: "auto", text: LINK },
          yours("reservation_footer"),
          { kind: "auto", text: SIGN },
        ];
      case "confirmed":
        return [
          { kind: "auto", text: SALUTATION },
          {
            kind: "auto",
            text: "deine Reservierung R-00123 ist bestätigt. Bitte hol deine Artikel während der unten genannten Öffnungszeiten ab.",
          },
          { kind: "auto", text: POOL_BLOCK },
          { kind: "pool", text: POOL_NOTE },
          {
            kind: "perConfirm",
            text: "Nachricht des Verleihteams:\n[individuelle Nachricht aus „Zu bestätigen“, falls eingegeben]",
          },
          {
            kind: "auto",
            text: "Zeig bei der Abholung deinen Code R-00123 – der beigefügte QR-Code kann am Verleihschalter gescannt werden.",
          },
          { kind: "auto", text: LINK },
          { kind: "auto", text: SIGN },
        ];
      case "rescheduled":
        return [
          { kind: "auto", text: SALUTATION },
          {
            kind: "auto",
            text: "wegen einer Schließung am 15. Juli 2026 mussten wir deine Reservierung R-00123 verschieben:",
          },
          {
            kind: "auto",
            text: "  - Sony Alpha 7 IV (DigiLab-0101):\n      Di 15. Juli 2026  →  Di 22. Juli 2026",
          },
          { kind: "pool", text: POOL_NOTE },
          { kind: "auto", text: LINK },
          yours("rescheduled_note"),
          { kind: "auto", text: SIGN },
        ];
      case "cancellation":
        return [
          { kind: "auto", text: SALUTATION },
          {
            kind: "auto",
            text: "wegen einer Schließung am 15. Juli 2026 musste deine Reservierung R-00123 storniert werden:",
          },
          { kind: "auto", text: "  - Sony Alpha 7 IV (DigiLab-0101): Di 15. Juli 2026" },
          { kind: "auto", text: CONTACT_BLOCK },
          { kind: "pool", text: POOL_NOTE },
          { kind: "auto", text: LINK },
          yours("cancellation_note"),
          { kind: "auto", text: SIGN },
        ];
      case "reminder":
        return [
          { kind: "auto", text: SALUTATION },
          { kind: "auto", text: "das ist eine Erinnerung an deine Reservierung R-00123." },
          {
            kind: "auto",
            text: "Noch nicht abgeholt (überfällig):\n  - Sony Alpha 7 IV (DigiLab-0101): Di 15. Juli 2026",
          },
          { kind: "pool", text: POOL_NOTE },
          { kind: "auto", text: LINK },
          yours("reminder_note"),
          { kind: "auto", text: SIGN },
        ];
      case "defect":
        return [
          { kind: "auto", text: SALUTATION },
          {
            kind: "auto",
            text: "ein auf deiner Buchung R-00123 reserviertes Gerät ist defekt und konnte nicht auf ein anderes Exemplar umgebucht werden:",
          },
          { kind: "auto", text: "  - Sony Alpha 7 IV (DigiLab-0101): Di 15. Juli 2026" },
          { kind: "auto", text: CONTACT_BLOCK },
          { kind: "pool", text: POOL_NOTE },
          { kind: "auto", text: LINK },
          yours("defect_note"),
          { kind: "auto", text: SIGN },
        ];
    }
  })();

  const hasYours = variant !== "confirmed";
  const isConfirmed = variant === "confirmed";

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center gap-3 text-xs">
        <span className="font-medium text-slate-600 dark:text-slate-300">
          {t("Example preview (German)")}
        </span>
        {hasYours && (
          <span className="flex items-center gap-1">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot.yours}`} />
            {t("Your text")}
          </span>
        )}
        <span className="flex items-center gap-1">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot.pool}`} />
          {t("From the pool")}
        </span>
        {isConfirmed && (
          <span className="flex items-center gap-1">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot.perConfirm}`} />
            {t("Message from “to confirm”")}
          </span>
        )}
        <span className="flex items-center gap-1 text-slate-400 dark:text-slate-300">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot.auto}`} />
          {t("Automatic")}
        </span>
      </div>
      <div className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-relaxed dark:border-slate-800 dark:bg-slate-950">
        {segs
          .filter((s): s is Seg => s !== null)
          .map((seg, i) => (
            <div key={i} className={i > 0 ? "mt-3" : ""}>
              {seg.kind === "auto" ? (
                <span className={styles.auto}>{seg.text}</span>
              ) : (
                <span className={styles[seg.kind]}>{seg.text}</span>
              )}
            </div>
          ))}
      </div>
    </div>
  );
}
