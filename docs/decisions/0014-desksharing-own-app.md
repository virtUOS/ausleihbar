# 0014. Desksharing als eigene App

- **Status:** Accepted
- **Date:** 2026-11-13

## Context
Ausleihbar 2.0 bekommt neben der Ausleihe einen zweiten Bereich
„Desksharing": Arbeitsplätze und Besprechungsräume einer Abteilung werden
stundenweise gebucht, ungenutzte Buchungen werden abhängig von der
Knappheit freigegeben, und es entstehen anonyme Nutzungsstatistiken.
Die Regeln (Knappheit, Karenzzeiten, Check-in, Tausch, Abwesenheit, Opt-out)
haben mit der Ausleihe nichts gemeinsam. Gleichzeitig dürfen
`release/1.0`-Fixes weiterhin sauber nach `main` gemergt werden, und
Anwesenheitsdaten sind personenbezogen (Personalrat).

## Decision
**Ansatz B:** eine eigene Django-App `desksharing` (Frontend
`frontend/src/desks/`) mit eigenen Modellen für Plätze, Buchungen
(`Reservation`), Serien, Abwesenheiten, Tausch-/Freigabeanfragen,
Profile (Opt-out) und Benachrichtigungseinstellungen.
- Eine Abteilung ist ein `ResourcePool`; Desksharing wird je Pool
  eingeschaltet (`DeskSettings.enabled`, nur mit mindestens einer
  Zugriffsgruppe). Abteilungsadmins sind die Verleiher des Pools.
- Geteilt werden nur Dinge, die wirklich gemeinsam sind: Pools,
  Zugriffsgruppen und Berechtigung (`accounts.eligibility`, `accounts.roles`),
  Sperrtage und Feiertage (`lending.Block`), Mail-Helfer und die
  Zeitraum-/Statistik-Oberfläche.
- Die Buchungslogik (inkl. Sperre gegen Doppelbuchung per
  Datenbank-Constraint) liegt vollständig in `desksharing`; die Ausleihe
  wird nicht verändert.
- Zeitgesteuerte Arbeit über zwei Management-Commands (`desks_tick`,
  `desks_daily`) im bestehenden Cron-Ansatz.
- Alle Benachrichtigungen laufen durch einen Dienst (`notify`) mit
  Kanal je Person und Ereignis; Mail ist der einzige ausgelieferte Kanal,
  Push kann später als zweiter Kanal angeschlossen werden.

## Consequences
- Die neuen Regeln stehen an einer Stelle; Ausleihe und Merge-Ups von
  `release/1.0` bleiben unberührt.
- Ein Platz gehört genau einem Bereich: Plätze sind keine Katalog-
  `Resource`s, Statistiken und QR-Codes sind getrennt von der Ausleihe.
- Verbindlicher Datenschutz an einer Stelle (`desksharing.privacy`):
  Opt-out, Aufbewahrung und Anonymisierung. Neue personenbezogene Daten
  (Buchungen mit Inhaber, Abwesenheiten, Opt-out) – Datenschutzseite und
  Personalrats-Zusammenfassung (`docs/desksharing-personalrat.md`) pflegen.
- Zwei zusätzliche Cron-Jobs und die Umgebungsvariable
  `DESKS_SUMMARY_HOUR` (siehe `docs/INSTALL.md`).
- Mehr Code (eigene Modelle, Admin, Tests), dafür keine Bedingungen quer
  durch die Ausleihe.

## Alternatives considered
- **A – in der Buchungs-Engine der Ausleihe** (Plätze als Produkte/
  Gegenstände, Buchungen als `Booking`/`BookingItem` mit Sofortmodus):
  eine Verfügbarkeitsprüfung, Sperrtage/Statistik/Mails wiederverwendbar.
  Aber die Ausleihe hat bereits drei Nutzungsarten; eine vierte mit
  eigenen Regeln streut Bedingungen durch jeden Ausleihpfad und erschwert
  Merge-Ups von `release/1.0`.
- **C – gemeinsames Inventar, getrennte Buchungen** (Plätze bleiben
  Katalog-`Resource`s, Buchungen in neuer App): ein Inventar- und
  QR-Pfad, aber jede Verfügbarkeitsprüfung müsste beide Buchungsarten
  kennen und Plätze würden Ausleihfelder (Garantie, Inventarnummer)
  tragen. Engste Kopplung für wenig Gewinn gegenüber B.
