# 0015. Gebäude als hochschulweite Liste

- **Status:** Accepted
- **Date:** 2026-11-16

## Context
Im Desksharing war das Gebäude bisher ein freier Text an jeder Etage, pro
Bereich. Hochschulen nennen ihre Gebäude meist mit einem kurzen Kürzel
(Zahlen wie „15“, anderswo Buchstaben wie „AX“), haben dazu aber eine
Beschreibung („EW-Gebäude“, „Bohnenkamp-Haus“) und eine Adresse. Ein Campus
kann rund hundert Gebäude haben. Die Auswahl von Gebäude und Etage soll auf
allen Desksharing-Seiten platzsparend sein und sich die zuletzt genutzte
Etage merken.

## Decision
- **Eigenes Modell `desksharing.Building`, hochschulweit:** `code` (kurz,
  eindeutig ohne Groß-/Kleinschreibung), `description`, `address`.
  `Floor.building` wird ein optionaler Fremdschlüssel (`PROTECT`).
- **Rechte:** Bereichs-Admins lesen die Liste und dürfen fehlende Gebäude
  anlegen (auch direkt im Etagenformular); ändern und löschen dürfen nur
  App-Admins. Gebäude mit Etagen lassen sich nicht löschen (409).
- **API-Ausgaben bleiben Strings:** `building` ist überall weiter das Kürzel
  (`Floor.building_code`), ergänzt um `building_id`, `building_description`
  und (Übersicht) `building_address`. Mitglieder sehen über
  `GET /api/desks/floors/?pool=` nur die Gebäude ihrer Bereiche.
- **Auswahl im Frontend:** Gebäude als eigene Auswahlliste mit Suche
  (Kürzel fett, Beschreibung darunter), Etagen als Pills (`LocationPicker`).
  Die gewählte Etage wird je Bereich im Browser gemerkt; ohne Wahl gilt die
  Etage der letzten eigenen Buchung. Ein Textfilter auf „Jetzt frei“ und
  „Buchen“ durchsucht alle Gebäude und Etagen.
- **Migration 0017:** je unterschiedlichem bisherigen Text ein Gebäude; der
  Text wird zum Kürzel (über 20 Zeichen: gekürzt, voller Text als
  Beschreibung). Kürzel und Beschreibung müssen danach von Hand gepflegt
  werden.

## Consequences
Adresse und Beschreibung werden einmal gepflegt und gelten für alle Bereiche.
Gleiche Freitexte verschiedener Bereiche werden bei der Migration zu einem
Gebäude zusammengeführt. Ein Bereichs-Admin kann einen Tippfehler in einem
selbst angelegten Gebäude nicht selbst korrigieren.

## Alternatives considered
- **Gebäude pro Bereich:** einfacher in den Rechten, aber gemeinsam genutzte
  Gebäude würden doppelt gepflegt.
- **Gebäude und Etagen nur als Pills:** bei vielen Gebäuden keine Option.
