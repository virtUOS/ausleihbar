# 0023. Check-in für Selbstbedienungs-Gegenstände und Türschilder für Gegenstände

- **Status:** Accepted (ergänzt ADR-0022: wer Türschilder koppelt)
- **Date:** 2026-11-26

## Context
Selbstbedienungs-Gegenstände (Nutzung vor Ort ohne Ausgabe, ADR-0013), etwa
ein Podcast-Raum oder ein 3D-Drucker, werden stundenweise gebucht, aber nie
an der Theke ausgegeben. Wer nicht erscheint, blockiert den Zeitraum bis zu
dessen Ende. Desksharing löst das mit Check-in und automatischer Freigabe
(ADR-0014); die Ausleihe hatte dafür nichts. Zugleich sollen die E-Ink-
Türschilder (ADR-0022) auch an einem einzelnen Gegenstand hängen können, nicht
nur an Räumen (Spec
`docs/superpowers/specs/2026-11-25-item-checkin-displays-design.md`).

## Decision
- **Check-in lebt im Ausleihkern (`lending.checkin`), nicht in Desksharing.**
  `Product.checkin_required` (nur Selbstbedienung, stundenweise) und
  `checkin_release_minutes` (Standard 30). Beim Anlegen einer Position wird
  `BookingItem.checkin_required` als **Momentaufnahme** festgehalten; spätere
  Produktänderungen wirken nicht rückwirkend. Wird die Einstellung am Produkt
  ausgeschaltet, verlieren noch nicht begonnene Positionen die Pflicht.
- **Frist.** Check-in öffnet 15 Minuten vor Beginn und ist ab Periodenende
  abgelehnt. Frist = min(max(Beginn, `Booking.submitted_at`) + Freigabeminuten,
  Ende). `submitted_at` verhindert, dass kurzfristige Buchungen sofort
  verfallen.
- **Freigabe.** `release_unstarted_items` (Cron, alle 5 Minuten) gibt
  Positionen ohne Check-in nach der Frist frei: „Nicht wahrgenommen",
  inaktiv, nie ausgegeben (`released_at`); eine Buchung, deren Positionen
  alle freigegeben sind, wird storniert; der Ausleihende bekommt eine
  Mail. **Kein automatischer Strike.**
- **Check-in per QR-Aufkleber und Theke.** Die Seite `/r/<qr_id>` bietet dem
  Angemeldeten für *seine* Buchung dieses Gegenstands Check-in bzw. „Nutzung
  beenden" (`GET/POST /api/resources/by-qr/<qr_id>/checkin/`); Verleihende
  können einchecken (`POST /api/manage/bookings/<id>/check-in/`).
- **Türschilder für Gegenstände.** `Display.resource` ergänzt `room`; genau
  eines von beiden ist gesetzt. Zulässig sind Gegenstände von
  Selbstbedienungs-Produkten. Zustände: Frei, Reserviert, Verspätet, In
  Benutzung, Geschlossen, Außer Betrieb. **Keine Namen** auf dem Schild, es
  zeigt den Buchungscode (die Person identifiziert sich damit beim
  Aufkleber-Check-in). Ein Pool ohne Öffnungszeiten gilt als geöffnet, außer
  an seinen Schließtagen; eine Sperre auf dem Gegenstand selbst ergibt
  „Außer Betrieb"; wird der Gegenstand ausgemustert, wird das Schild
  entkoppelt. Die Tasten aktualisieren nur das Bild.
- **Verwaltung nur für App-Admins** unter `/admin/displays` (Admin-Gruppe
  „Verbindungen" mit Türschilder und LMS-Plattformen); `/desks/manage/displays`
  leitet dorthin um. Das **ändert ADR-0022**: Kopplung, Umbenennen, Zuordnen
  und Entfernen sind nicht mehr Sache der Abteilungsadmins. Diese behalten
  die Raumvorschau (`door-preview.png`). API unter
  `/api/desks/manage/displays/` (+ `resources/`-Suche).
- **Kein neuer Dienst, keine neue Umgebungsvariable**; neuer Cron
  `release_unstarted_items` (siehe `docs/INSTALL.md`).

## Consequences
- Nicht wahrgenommene Selbstbedienungs-Zeitfenster werden frei, ohne dass
  die Theke eingreift. Preis: Ausleihende müssen aktiv einchecken, und die
  Freigabe kommt je nach Cron-Takt bis zu 5 Minuten verzögert.
- Neu gespeichert werden `BookingItem.checked_in_at`, `released_at` und
  `Booking.submitted_at`; öffentliche Schilder zeigen den Buchungscode. Die
  Datenschutzseite ist zu prüfen.
- Das zentrale Koppeln ist ein Verwaltungsaufwand für App-Admins, schließt
  aber aus, dass Abteilungsadmins Schilder an Gegenständen fremder Pools
  anbringen.

## Alternatives considered
- **Check-in in Desksharing wiederverwenden:** Desksharing kennt Plätze und
  Abteilungen, nicht Produkte, Pools und Perioden; die Ausleihe bliebe
  ohne eigene Freigabe. Verworfen.
- **Automatischer Strike bei Nichterscheinen:** zu hart bei technischen
  oder kurzfristigen Verhinderungen; Verleihende können weiter manuell
  Strikes vergeben.
- **Namen auf dem Schild:** Flur-Aushang ohne Datenschutznutzen; der
  Buchungscode genügt.
