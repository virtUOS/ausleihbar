// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAuth } from "../auth";
import { useFetch } from "../useFetch";
import { AdminTabs } from "../components/AdminTabs";
import { SortToggle } from "../components/SortToggle";
import { FormActionBar, sameFormValue } from "../components/FormActionBar";
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
  | "defect"
  | "missing"
  | "pickup";

type Form = Record<string, string>;

// The single-paragraph mails (each gets one optional admin paragraph).
const NOTE_FIELDS = [
  "rescheduled_note",
  "cancellation_note",
  "reminder_note",
  "defect_note",
  "pickup_reminder_note",
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
  const [previewLang, setPreviewLang] = useState<MailLang>(
    user?.content_default_language === "en" ? "en" : "de",
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  // Last loaded/saved form, for the "Unsaved changes" hint.
  const [savedForm, setSavedForm] = useState<Form>(EMPTY);
  const [pickupEnabled, setPickupEnabled] = useState(true);
  const [savedPickupEnabled, setSavedPickupEnabled] = useState(true);

  useEffect(() => {
    if (!setting.data) return;
    const data = setting.data as unknown as Record<string, string | null>;
    const loaded: Form = {
      ...Object.fromEntries(
        ALL_FIELDS.flatMap((f) => [
          [`${f}_de`, data[`${f}_de`] ?? ""],
          [`${f}_en`, data[`${f}_en`] ?? ""],
        ]),
      ),
      confirmation_send_time: (data.confirmation_send_time ?? "17:00:00").slice(0, 5),
    };
    setForm(loaded);
    setSavedForm(loaded);
    const enabled = setting.data.pickup_reminder_enabled ?? true;
    setPickupEnabled(enabled);
    setSavedPickupEnabled(enabled);
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
      await api.updateNotificationSetting({
        ...payload,
        pickup_reminder_enabled: pickupEnabled,
      });
      // Form and baseline both take the sent values (the send-time may have
      // fallen back), so the form is clean right after a save.
      setForm(payload);
      setSavedForm(payload);
      setSavedPickupEnabled(pickupEnabled);
      setMessage({ ok: true, text: t("Saved.") });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : t("Save failed.") });
    } finally {
      setBusy(false);
    }
  }

  const dirty = !sameFormValue(form, savedForm) || pickupEnabled !== savedPickupEnabled;

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

  // Where each note lands mirrors backend/lending/notifications.py: the
  // closure notes give the reason right after the salutation; the others
  // stand before the contact request, or before the bookings link.
  const reasonLabel = t("Reason (shown right after the salutation)");
  const beforeLinkLabel = t("Additional paragraph (shown before the bookings link)");
  const sectionMeta: {
    field: (typeof NOTE_FIELDS)[number];
    title: string;
    label: string;
    placeholder: string;
  }[] = [
    {
      field: "rescheduled_note",
      title: t("When a booking is rescheduled (closure)"),
      label: reasonLabel,
      placeholder: t("e.g. Due to a high sickness rate we unfortunately have to close."),
    },
    {
      field: "cancellation_note",
      title: t("When a booking is cancelled (closure)"),
      label: reasonLabel,
      placeholder: t("e.g. Due to a high sickness rate we unfortunately have to close."),
    },
    {
      field: "reminder_note",
      title: t("Overdue reminder"),
      label: beforeLinkLabel,
      placeholder: t("e.g. Late returns may lead to a strike."),
    },
    {
      field: "defect_note",
      title: t("When a reserved device is unavailable"),
      label: t("Additional paragraph (shown before the request to get in touch)"),
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
          "Custom text for the borrower emails. The personal salutation, the booking number, the booking details and the link are always kept — your text is woven in around them. All fields are optional; an empty language uses the other language's text, or the built-in default if both are empty. Pool-specific hints (e.g. eligibility) are set per pool and appear in that pool's section.",
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
                {noteField(s.field, s.label, s.placeholder)}
              </fieldset>
            ))}

            <fieldset className="space-y-4 border-t border-slate-100 pt-4 dark:border-slate-800">
              <legend className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {t("Reminder before pickup")}
              </legend>
              <div className="space-y-1">
                <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                  <input
                    type="checkbox"
                    checked={pickupEnabled}
                    onChange={(e) => setPickupEnabled(e.target.checked)}
                  />
                  {t("Send a pickup reminder one day before")}
                </label>
                <p className="text-xs text-slate-600 dark:text-slate-300">
                  {t(
                    "Sent automatically the day before pickup, with address, opening hours and directions.",
                  )}
                </p>
              </div>
              {noteField(
                "pickup_reminder_note",
                beforeLinkLabel,
                t("e.g. Please bring your student ID."),
              )}
            </fieldset>

            <FormActionBar
              saving={busy}
              dirty={dirty}
              surface="card"
            >
              {message && !(message.ok && dirty) && (
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
            </FormActionBar>
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
                  ["missing", t("Item missing")],
                  ["pickup", t("Pickup reminder")],
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
            <div className="mb-2 flex items-center gap-2 text-xs">
              <span className="font-medium text-slate-600 dark:text-slate-300">
                {t("Preview language")}
              </span>
              <SortToggle
                value={previewLang}
                onChange={setPreviewLang}
                label={t("Preview language")}
                options={[
                  { value: "de", label: "DE" },
                  { value: "en", label: "EN" },
                ]}
              />
            </div>
            <MailPreview
              variant={preview}
              form={form}
              lang={previewLang}
              defaultLang={user?.content_default_language === "en" ? "en" : "de"}
            />
          </div>
        </div>
      )}
    </div>
  );
}

type Seg = { kind: "auto" | "yours" | "pool" | "perConfirm"; text: string };

type MailLang = "de" | "en";

/** Fixed (automatic) parts of the borrower mails per mail language — the
 *  wording mirrors backend/lending/notifications.py (English msgids) and its
 *  German translations in backend/locale/de/LC_MESSAGES/django.po, with sample
 *  data. Deliberately data, not i18n keys: the preview follows the DE|EN
 *  toggle, not the UI language. Keep in sync when the mail texts change. */
interface MailTexts {
  greeting: string;
  receivedIntro: string;
  bookingNumber: string;
  confirmedIntro: string;
  lenderNote: string;
  pickupLine: string;
  rescheduledIntro: string;
  rescheduledItem: string;
  cancelledIntro: string;
  reminderIntro: string;
  reminderPickups: string;
  pickupIntro: string;
  defectIntro: string;
  missingIntro: string;
  contactAlternative: string;
  contactBeforeVisit: string;
  itemLine: string;
  poolBlock: string;
  poolShortBlock: string;
  poolNote: string;
  link: string;
  signature: string;
}

const CODE = "R-00123";
const ITEM = "Sony Alpha 7 IV (DigiLab-0101)";
const ADDRESS = "  {address}\n    Musterstraße 1\n    49074 Osnabrück";

function poolBlock(heading: string, labels: Record<string, string>, items: string) {
  const address = ADDRESS.replace("{address}", labels.address);
  return (
    `${heading}\n\n${items}\n\n${address}\n\n` +
    `  ${labels.hours}\n    ${labels.mon}: 09:00–12:00\n    ${labels.thu}: 13:00–16:00\n\n` +
    `  ${labels.directions}\n    ${labels.directionsText}\n\n` +
    `  ${labels.contact} 0541 969-0 / digilab@uni.example`
  );
}

function makeTexts(
  l: Record<string, string> & { period: string; periodNew: string; room: string },
  t: Omit<MailTexts, "itemLine" | "poolBlock" | "poolShortBlock" | "rescheduledItem">,
): MailTexts {
  const heading = `${l.pickupAt} · ${l.room}`;
  const full = poolBlock(heading, l, `  • ${ITEM}\n      ${l.period}`);
  return {
    ...t,
    itemLine: `  - ${ITEM}: ${l.period}`,
    rescheduledItem:
      `  - ${ITEM}:\n      ${l.before} ${l.period}\n      ${l.now} ${l.periodNew}`,
    // Full block: with items (received/confirmed); the rescheduled mail and
    // the reminder repeat it without the item lines.
    poolBlock: full,
    poolShortBlock:
      `DigiLab · ${l.room}\n\n${ADDRESS.replace("{address}", l.address)}\n\n` +
      `  ${l.contact} 0541 969-0 / digilab@uni.example`,
  };
}

const TEXTS: Record<MailLang, MailTexts> = {
  de: makeTexts(
    {
      pickupAt: "Abholung bei DigiLab",
      room: "Raum 1.01",
      address: "Adresse:",
      hours: "Öffnungszeiten:",
      mon: "Mo",
      thu: "Do",
      directions: "Wegbeschreibung:",
      directionsText: "Eingang Nord, 1. OG",
      contact: "Kontakt:",
      period: "Do., 15.10.2026 → Sa., 17.10.2026",
      periodNew: "Do., 22.10.2026 → Sa., 24.10.2026",
      before: "vorher:",
      now: "jetzt:",
    },
    {
      greeting: "Hallo Erika Mustermann,",
      receivedIntro:
        "wir haben deine Reservierung erhalten. Sie ist vorgemerkt und wird vom Verleihteam in Kürze bestätigt.",
      bookingNumber: `Buchungsnummer: ${CODE}`,
      confirmedIntro: `deine Buchung ${CODE} ist bestätigt. Bitte hole deine Gegenstände innerhalb der unten genannten Öffnungszeiten ab.`,
      lenderNote:
        "Eine Nachricht vom Verleihteam:\n[individuelle Nachricht aus „Zu bestätigen“, falls eingegeben]",
      pickupLine: `Zeige bei der Abholung deine Buchungsnummer ${CODE} — der angehängte QR-Code kann an der Verleihtheke gescannt werden. Mit dem angehängten Kalendereintrag (.ics) übernimmst du den Ausleihzeitraum in deinen Kalender.`,
      rescheduledIntro: `aufgrund einer Schließung am Do., 15.10.2026 mussten wir deine Buchung ${CODE} umbuchen:`,
      cancelledIntro: `aufgrund einer Schließung vom Do., 15.10.2026 bis Fr., 16.10.2026 musste deine Buchung ${CODE} storniert werden:`,
      reminderIntro: `dies ist eine Erinnerung an deine Buchung ${CODE}.`,
      reminderPickups: "Noch nicht abgeholt (überfällig):",
      pickupIntro: `deine Buchung ${CODE} kann morgen abgeholt werden:`,
      defectIntro: `ein für deine Buchung ${CODE} reservierter Gegenstand ist nicht mehr verfügbar (defekt) und konnte nicht auf ein anderes Exemplar umgebucht werden:`,
      missingIntro: `ein für deine Buchung ${CODE} reservierter Gegenstand ist bei der Abholung möglicherweise nicht verfügbar: er wurde noch nicht zurückgegeben und deine Buchung konnte nicht auf ein anderes Exemplar umgebucht werden:`,
      contactAlternative: "Bitte kontaktiere das Verleihteam, um eine Alternative zu vereinbaren:",
      contactBeforeVisit: "Bitte kontaktiere das Verleihteam, bevor du vorbeikommst:",
      poolNote: "  Dieser Pool steht nur Studierenden des Fachs XY zur Verfügung.",
      link: "Deine Buchungen ansehen: https://ausleihbar.example.org/bookings",
      signature: "— Ausleihbar",
    },
  ),
  en: makeTexts(
    {
      pickupAt: "Pickup at DigiLab",
      room: "Room 1.01",
      address: "Address:",
      hours: "Opening hours:",
      mon: "Mon",
      thu: "Thu",
      directions: "Directions:",
      directionsText: "North entrance, 1st floor",
      contact: "Contact:",
      period: "Thu 15 Oct 2026 → Sat 17 Oct 2026",
      periodNew: "Thu 22 Oct 2026 → Sat 24 Oct 2026",
      before: "before:",
      now: "now:",
    },
    {
      greeting: "Hi Erika Mustermann,",
      receivedIntro:
        "we received your reservation. It is on hold and the lending team will confirm it shortly.",
      bookingNumber: `Booking number: ${CODE}`,
      confirmedIntro: `your booking ${CODE} is confirmed. Please pick up your item(s) during the opening hours below.`,
      lenderNote:
        "A note from the lending team:\n[individual message from “to confirm”, if entered]",
      pickupLine: `At pickup, show your booking number ${CODE} — the attached QR code can be scanned by the lending desk. The attached calendar entry (.ics) adds the lending period to your calendar.`,
      rescheduledIntro: `because of a closure on Thu 15 Oct 2026 we had to reschedule your booking ${CODE}:`,
      cancelledIntro: `because of a closure from Thu 15 Oct 2026 to Fri 16 Oct 2026 your booking ${CODE} had to be cancelled:`,
      reminderIntro: `this is a reminder about your booking ${CODE}.`,
      reminderPickups: "Not yet picked up (overdue):",
      pickupIntro: `your booking ${CODE} can be picked up tomorrow:`,
      defectIntro: `an item reserved on your booking ${CODE} has become unavailable (defect) and we could not move it to another unit:`,
      missingIntro: `an item reserved on your booking ${CODE} may not be available at pickup: it has not yet been returned and we could not move your booking to another unit:`,
      contactAlternative: "Please contact the lending team to arrange an alternative:",
      contactBeforeVisit: "Please contact the lending team before you come by:",
      poolNote: "  This pool is only available to students of subject XY.",
      link: "View your bookings: https://ausleihbar.example.org/bookings",
      signature: "— Ausleihbar",
    },
  ),
};

/** The full pool block without its item lines (rescheduled mail, reminder). */
function withoutItems(block: string): string {
  const [heading, , ...rest] = block.split("\n\n");
  return [heading, ...rest].join("\n\n");
}

/** Illustrative preview of a borrower email in German or English, with
 *  sample data. `form` holds the admin's `*_de` / `*_en` values; the preview
 *  colour-codes where each part comes from. An approximation, not byte-exact. */
function MailPreview({
  variant,
  form,
  lang,
  defaultLang,
}: {
  variant: Variant;
  form: Form;
  lang: MailLang;
  defaultLang: MailLang;
}) {
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
  // Mirrors the backend (modeltranslation): an empty value in the mail's
  // language falls back to the content default language, then the other
  // language; only when all are empty is the built-in text used.
  const order: MailLang[] = [lang, defaultLang, lang === "de" ? "en" : "de"];
  const yours = (field: string): Seg | null => {
    for (const l of order) {
      const v = (form[`${field}_${l}`] ?? "").trim();
      if (v) return { kind: "yours", text: v };
    }
    return null;
  };
  const x = TEXTS[lang];
  const auto = (text: string): Seg => ({ kind: "auto", text });
  const note: Seg = { kind: "pool", text: x.poolNote };

  // "Please get in touch" mails: a closure reason (`lead`) follows the
  // greeting; any other note stands before the contact request.
  const contactMail = (
    intro: string,
    contactLine: string,
    { lead, beforeContact }: { lead?: string; beforeContact?: string },
  ): (Seg | null)[] => [
    auto(x.greeting),
    lead ? yours(lead) : null,
    auto(intro),
    auto(x.itemLine),
    beforeContact ? yours(beforeContact) : null,
    auto(contactLine),
    auto(x.poolShortBlock),
    note,
    auto(x.link),
    auto(x.signature),
  ];

  const segs: (Seg | null)[] = (() => {
    switch (variant) {
      case "received":
        return [
          auto(x.greeting),
          yours("reservation_intro") ?? auto(x.receivedIntro),
          auto(x.bookingNumber),
          auto(x.poolBlock),
          note,
          auto(x.link),
          yours("reservation_footer"),
          auto(x.signature),
        ];
      case "confirmed":
        return [
          auto(x.greeting),
          auto(x.confirmedIntro),
          auto(x.poolBlock),
          note,
          { kind: "perConfirm", text: x.lenderNote },
          auto(x.pickupLine),
          auto(x.link),
          auto(x.signature),
        ];
      case "rescheduled":
        return [
          auto(x.greeting),
          yours("rescheduled_note"),
          auto(x.rescheduledIntro),
          auto(x.rescheduledItem),
          auto(withoutItems(x.poolBlock)),
          note,
          auto(x.link),
          auto(x.signature),
        ];
      case "cancellation":
        return contactMail(x.cancelledIntro, x.contactAlternative, {
          lead: "cancellation_note",
        });
      case "reminder":
        return [
          auto(x.greeting),
          auto(x.reminderIntro),
          auto(`${x.reminderPickups}\n${x.itemLine}`),
          auto(withoutItems(x.poolBlock)),
          note,
          yours("reminder_note"),
          auto(x.link),
          auto(x.signature),
        ];
      case "defect":
        return contactMail(x.defectIntro, x.contactAlternative, {
          beforeContact: "defect_note",
        });
      case "missing":
        return contactMail(x.missingIntro, x.contactBeforeVisit, {
          beforeContact: "defect_note",
        });
      case "pickup":
        return [
          auto(x.greeting),
          auto(x.pickupIntro),
          auto(x.poolBlock),
          note,
          yours("pickup_reminder_note"),
          auto(x.link),
          auto(x.signature),
        ];
    }
  })();

  const hasYours = variant !== "confirmed";
  const isConfirmed = variant === "confirmed";

  return (
    <div>
      <p className="mb-1.5 text-xs text-slate-600 dark:text-slate-300">
        {t("Example with sample data — an approximation, not byte-exact.")}
      </p>
      <div className="mb-1.5 flex flex-wrap items-center gap-3 text-xs">
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
      <div
        lang={lang}
        className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-relaxed dark:border-slate-800 dark:bg-slate-950"
      >
        {segs
          .filter((s): s is Seg => s !== null)
          .map((seg, i) => (
            <div key={i} className={i > 0 ? "mt-3" : ""}>
              <span className={styles[seg.kind]}>{seg.text}</span>
            </div>
          ))}
      </div>
    </div>
  );
}
