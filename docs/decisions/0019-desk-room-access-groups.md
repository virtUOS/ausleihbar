# 0019. Räume vererben Zugriffsgruppen an ihre Plätze

- **Status:** Accepted (ergänzt ADR-0018; folgt dem Muster der Pool-Vererbung aus ADR-0017)
- **Date:** 2026-11-19

## Context
Zugriffsgruppen („Wer darf buchen“, ADR-0018) hingen bisher nur am Platz.
Sollen alle Plätze eines Raums denselben Personenkreis haben, musste man jede
Gruppe an jedem Platz einzeln setzen – und neue Plätze des Raums vergaß man
leicht. Der Pool eines Platzes kommt seit ADR-0017 schon vom Raum, mit
bewusster Abweichung am Platz.

## Decision
- Ein Raum hat **Standard-Zugriffsgruppen** (`Room.access_groups`). Seine
  Plätze **folgen** ihnen: die Gruppen des Platzes sind genau die des Raums.
  Ein Platz mit `groups_overridden` hat eigene Gruppen und behält sie.
  Variante „ersetzen“, nicht „ergänzen“: ein abweichender Platz hat genau
  seine Gruppen, die des Raums gelten dort nicht zusätzlich – wie beim Pool
  (ADR-0017).
- Die Gruppen eines folgenden Platzes werden gespeichert (nicht zur Laufzeit
  vom Raum gelesen), damit alle Rechteprüfungen und das Signal für den
  Verlust von Rechten unverändert an `Place.access_groups` hängen. Ändern sich
  die Gruppen eines Raums, schreibt `desksharing.place_groups.hand_down` sie
  an die folgenden Plätze, nur wo sich der Satz wirklich ändert.
- Weitergegeben wird nur an Plätze **derselben Abteilung** wie der Raum
  (`place.pool_id == room.pool_id`). Ein Platz, der einem anderen Pool
  zugeordnet ist (`pool_overridden`), wird dort verwaltet
  (`rights.can_admin_place`); die Admins des Raums ändern seine Gruppen
  nicht.
- Ein neuer Platz folgt seinem Raum; ein verschobener folgender Platz
  übernimmt die Gruppen des neuen Raums. Das Platzformular hat „Wie der
  Raum“; schickt es die Gruppen des alten oder neuen Raums zurück, bleibt der
  Platz folgend.
- Die Migration markiert vorhandene Plätze mit Gruppen als
  `groups_overridden` (sie behalten genau ihre Gruppen); Räume starten ohne
  Gruppen, Plätze ohne Gruppen folgen.
- Im Django-Admin sind `access_groups` (Raum und Platz) und
  `groups_overridden` nur lesbar, damit dort niemand die Gleichheit
  „folgender Platz = Raum“ bricht. Geändert wird nur in der App.
- Sammelaktion `POST /api/desks/manage/place-groups/` (`room_ids`,
  `place_ids`, `add_ids`, `remove_ids`, `follow_room`), alles oder nichts:
  Räume bekommen Gruppen hinzu/entfernt und geben sie weiter; ausgewählte
  Plätze werden abweichend (eigener Satz ± Gruppen) oder folgen mit
  `follow_room` wieder ihrem Raum. Ein ausgewählter folgender Platz eines
  ebenfalls ausgewählten Raums folgt einfach dem neuen Raumsatz. Nur
  gewöhnliche Gruppen, keine System- oder Admin-Gruppen.
- Rechte: App-Admins dürfen alles; Abteilungsadmins nur Räume
  (`can_admin_room`) und Plätze (`can_admin_place`), die sie verwalten. Enthält
  die Auswahl etwas Fremdes, wird die ganze Anfrage mit 403 abgelehnt.

## Consequences
- Gruppen für einen ganzen Raum sind ein Handgriff; neue Plätze sind sofort
  richtig eingeschränkt.
- Entfernt man Gruppen am Raum, verlieren Personen an allen folgenden Plätzen
  den Zugriff; ihre künftigen Buchungen enden wie bei einer Änderung am Platz.
- Plätze anderer Abteilungen in einem Raum behalten ihre Gruppen, auch wenn
  sie nicht als abweichend markiert sind; sie folgen erst wieder, wenn ihr
  Platz geändert oder dem Pool des Raums zugeordnet und neu gesetzt wird.

## Alternatives considered
- **„Ergänzen“** (Platz = Raumgruppen ∪ eigene Gruppen): ein Platz könnte den
  Kreis des Raums nie enger fassen; anders als beim Pool (ADR-0017).
- **Gruppen nur zur Laufzeit vom Raum lesen:** jede Rechteprüfung und das
  Signal für den Verlust von Rechten müssten Raum und Platz kombinieren.
