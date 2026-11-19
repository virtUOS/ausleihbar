# 0017. Hochschulweite Etagen, Abteilungen an Räumen und Plätzen

- **Status:** Accepted (ersetzt in ADR-0014 den Teil „eine Etage gehört einer Abteilung“)
- **Date:** 2026-11-19

## Context
Bisher gehörte jede Etage (`Floor`) genau einer Abteilung (`ResourcePool`);
Räume und Plätze hingen darunter. Eine Etage, die sich zwei Abteilungen
teilen, gab es dadurch zweimal, mit zwei Grundrissen, und ein Gebäude ließ
sich nicht so einrichten, wie es tatsächlich ist. Gewünscht ist: Gebäude und
Etage wählen, Grundriss, Räume und Plätze sehen, Fehlendes ergänzen (auch
viele auf einmal, mit sinnvollen Namen) und dann Räume oder einzelne Plätze
einer Abteilung zuordnen. Ausstattung soll wie Gebäude (ADR-0015) ein
gemeinsamer Katalog werden. Desksharing war noch nirgends ausgerollt; das
Datenmodell durfte sich frei ändern, die lokalen Demodaten wurden migriert.

## Decision
- **Etagen und Grundrisse sind hochschulweit:** `Floor` verliert die
  Abteilung und besteht aus Gebäude + Name mit genau einem Grundriss (Formen,
  Maßstab, Vorlage).
- **Abteilung an Raum und Platz (Variante 1):** `Room.pool` ist die
  Standard-Abteilung des Raums. `Place.pool` ist die *wirksame* Abteilung,
  am Platz gespeichert und indiziert; `Place.pool_overridden` markiert einen
  Platz, der bewusst vom Raum abweicht. Ein Raum gibt seine Abteilung beim
  Zuordnen an alle nicht abweichenden Plätze weiter (ein Dienst,
  `desksharing.assignment`, eine Transaktion); ein neuer Platz erbt die
  Abteilung seines Raums. Ein Platz ohne Abteilung ist nicht zugeordnet:
  nicht buchbar, für Mitglieder unsichtbar, in keiner Statistik. Hebt man die
  Zuordnung eines Raums auf, verlieren nur die ihm folgenden Plätze ihre
  Abteilung; abweichende behalten ihre.
- **Jede Abfrage und Rechteprüfung nutzt `Place.pool`** statt
  `room.floor.pool` (Buchung, Übersicht, Rechte, Statistik, Datenschutz,
  Freigabe, Serien, Anfragen, Check-in, Zyklen, Abwesenheiten, Favoriten).
- **Buchungen laufen weiter („let them run“):** `Reservation.pool` hält fest,
  in welcher Abteilung eine Buchung entstand (bei der Anlage aus
  `place.pool`; Altbestand aus der früheren Etagen-Abteilung). Wird ein Platz
  umgehängt oder seine Zuordnung aufgehoben, bleiben künftige Buchungen und
  Serien bis zu ihrem Ende bestehen; nichts wird storniert oder gemailt.
  Alles, was eine bestehende Buchung beurteilt, nutzt `Reservation.pool`:
  Statistik, Aufbewahrungsfrist, Rechteentzug (eine Person behält die
  Buchung, solange sie Mitglied der Abteilung der Buchung ist),
  Admin-Aktionen und Sichtbarkeit für Abteilungsadmins, Zyklen und
  Kontingent. Neue Buchungen, Verfügbarkeit und Mitgliederansichten nutzen
  `Place.pool`. Eine feste Inhaberin bzw. ein fester Inhaber bleibt
  eingetragen, bis ein App-Admin sie oder ihn bewusst entfernt.
- **Rechte:** App-Admins dürfen alles (Gebäude, Etagen, Grundrissformen,
  Maßstab, Vorlage, Räume anlegen und löschen, Zuordnung, Einstellungen,
  Ausstattung ändern und löschen). Abteilungsadmins sehen die Etagen mit
  Räumen oder Plätzen ihrer Abteilungen, bearbeiten Räume mit ihrer
  Standard-Abteilung und alle Plätze ihrer Abteilung (Name, Ausstattung,
  feste Inhaber, Zugriffsgruppen, Symbole im Grundriss), legen Plätze in
  ihren Räumen an und dürfen – wie bei Gebäuden – Ausstattung anlegen. Sie
  legen weder Etagen noch Räume an und ordnen nichts zu.
- **Ausstattung ist hochschulweit:** `Feature` ohne Abteilung, mit
  übersetzbarer Beschreibung und Bildergalerie (Mechanik der
  Produktgalerie); löschen nur, solange kein Platz sie nutzt (409).
- **Eindeutige Namen, ohne Groß-/Kleinschreibung:** Etagen je Gebäude,
  Räume je Etage, Ausstattung hochschulweit (jeweils auch als
  Datenbank-Constraint), Plätze je Gebäude (in Serializer und Diensten, weil
  die Regel über einen Join reicht).
- **Namensmuster für Plätze:** eine hochschulweite Einstellung
  (`DeskAdminSetting`, App-Admins): „Raum + Buchstabe“ (`15/201 A`, `B`, …;
  Standard) oder „Raum + Zahl“ (`15/201-1`, `-2`, …). Vorschläge liefern den
  nächsten freien Namen je Raum.
- **Sammelanlage und Zuordnung:** Räume per Präfix und Nummernbereich, Plätze
  als Anzahl je Raum, jeweils mit Vorschau; vorhandene Namen werden
  übersprungen. Beim Zuordnen können Zugriffs- und Admin-Gruppen der
  Abteilung nur *ergänzt* werden (Entfernen bleibt im Pool-Formular, weil die
  Ausleihe dieselben Gruppen nutzt). Die erste Zuordnung schaltet
  Desksharing für die Abteilung ein, sofern dann eine Zugriffsgruppe
  existiert; sonst wird sie abgelehnt. Eine Abteilung mit eingeschaltetem
  Desksharing bleibt nie ohne Zugriffsgruppe.
- **Grundriss-Editor:** ein Grundriss je Etage; Abteilungsadmins verschieben
  darin nur die Symbole ihrer eigenen Plätze, Formen, Maßstab und Vorlage
  bearbeiten App-Admins.

## Consequences
- Ein Gebäude wird einmal eingerichtet; geteilte Etagen haben einen
  Grundriss, Abteilungen bekommen Räume oder einzelne Plätze darin.
- Die Abfragen werden einfacher (eine Spalte am Platz statt eines Joins über
  die Etage); dafür muss der Zuordnungsdienst `Room.pool` und `Place.pool`
  synchron halten – Zuordnungen laufen deshalb nur über ihn.
- Umhängen ist folgenlos für laufende Buchungen; eine frühere Abteilung
  verwaltet ihre noch laufenden Buchungen weiter, bis sie enden. Statistik
  und Aufbewahrung zählen eine Buchung immer für die Abteilung, in der sie
  entstand.
- Abteilungsadmins können keine Räume mehr anlegen; Etagen und Räume
  richten App-Admins ein.
- `Reservation.pool` und die Ausstattungsbeschreibung/-bilder sind keine
  personenbezogenen Daten; die Datenschutzseite ändert sich nicht.

## Alternatives considered
- **Abteilung bei jeder Abfrage berechnen** (Platz-Abweichung, sonst Raum):
  keine Synchronisation, aber eine ODER-Bedingung an rund 56 Stellen, von
  denen leicht eine vergessen wird – ein Rechte- und Datenschutzrisiko.
- **Etagen bleiben je Abteilung:** genau das, was abgeschafft werden sollte
  (doppelte Etagen und Grundrisse).
- **Buchungen beim Umhängen stornieren:** überrascht Inhaber/innen mitten in
  einer Planung; „weiterlaufen lassen“ ist ohne Mails und ohne Verluste.
- **Abteilungsadmins legen auch Räume an:** bewusst nicht – Gebäude werden
  zentral eingerichtet und zugeordnet (Annahme analog zu den Gebäuden).
