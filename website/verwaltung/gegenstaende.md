---
title: Gegenstände, Defekte und QR-Etiketten
description: Den Bestand pflegen — Produkte und ihre Gegenstände, Status und Eigenschaften, Defekte mit optionalen GitLab-Tickets und druckbare QR-Etiketten.
---

# Gegenstände, Defekte und QR-Etiketten

Ein **Produkt** ist der Katalogeintrag, etwa „Sony Alpha 7 IV“. Ein
**Gegenstand** ist ein einzelnes Exemplar davon, mit eigener
Bestandsnummer (z. B. MED-0001), eigenem Pool und eigenem Status. Gebucht
wird das Produkt; Ausleihbar teilt dabei einen freien Gegenstand zu.

## Die Seite Gegenstände

Verleihtheke → Bestand → **Gegenstände** listet die Produkte. Ein Klick auf
den Pfeil klappt ein Produkt auf und zeigt seine Gegenstände.

![Seite „Gegenstände“ mit den Filtern Alle Pools, Alle Status, Alle Produkttypen und Kein Eigenschaftsfilter, den Knöpfen „+ Neues Produkt“ und „+ Neuer Gegenstand“ und der Produktliste mit Etiketten wie „2 verfügbar“, „1 überfällig · fällig am 16.10.2026“, „1 verliehen · bis 20.10.2026“ und „1 defekt“; die Sony Alpha 7 IV ist aufgeklappt und zeigt MED-0001 und MED-0002 als Verfügbar und MED-0003 als Defekt mit Notiz](../bilder/theke-gegenstaende.png)

An jedem Produkt zeigen Etiketten auf einen Blick, wie viele Gegenstände
**verfügbar**, **verliehen** (mit dem Rückgabetag), **überfällig**,
**gesperrt**, **defekt** oder **ausgemustert** sind. Im Menü **⋮** des
Produkts: **Produkt bearbeiten**, **Gegenstand hinzufügen**, **Löschen**.

In der aufgeklappten Tabelle stehen je Gegenstand Bestandsnummer, Pool,
Status, Zustand und — wenn er draußen ist — „verliehen bis …“ bzw.
„überfällig (fällig am …)“. Die Spalten lassen sich sortieren. Im Menü **⋮**
des Gegenstands: **Bearbeiten**, **Duplizieren** (für weitere gleiche
Exemplare) und **Löschen**.

!!! info "Alle Produkte, deine Gegenstände"
    Produkte gehören zum gemeinsamen Katalog, deshalb siehst du alle — auch
    solche, von denen dein Pool keine Exemplare hat („0 Gegenstände“).
    Gegenstände siehst und bearbeitest du nur in deinen Pools.

### Filtern

- **Pool**, **Status** und **Produkttyp**,
- das Suchfeld für Produkt, Bestands- oder Seriennummer,
- der **Eigenschaftsfilter** für Datums-Eigenschaften, die am Gegenstand
  gepflegt werden, etwa „letzte Wartung“: **älter als** ein Datum oder
  **leer**. So findest du z. B. alle Gegenstände, deren Prüfung fällig ist.
  Die gewählte Eigenschaft erscheint dann auch als sortierbare Spalte.

### Status

| Status | Bedeutung |
| --- | --- |
| **Verfügbar** | kann gebucht und ausgegeben werden |
| **Gesperrt** | vorübergehend aus dem Verleih genommen |
| **Defekt** | kaputt, wird nicht verliehen ([Defekte](#defekte)) |
| **Ausgemustert** | dauerhaft außer Betrieb |

Den Status änderst du direkt in der Tabelle über die Auswahl. Wählst du
**Defekt**, fragt Ausleihbar nach einer kurzen Beschreibung des Problems.

### Ein Gegenstand im Detail

Ein Klick auf die Bestandsnummer öffnet die Detailseite des Gegenstands:
Produkt, Pool, QR-Code, Lagerort, Wert, Beschaffungsdatum, Garantieende,
Seriennummer, Einrichtung und die Eigenschaften, die am Gegenstand gepflegt
werden. Dazu:

- **Zustand (nur für Verleiher):** eine Bewertung von 1 bis 5 Sternen mit
  optionalen Details — für Ausleihende unsichtbar.
- **Aktueller Defekt** mit **Als defekt markieren** bzw. **Defekt beheben
  (als verfügbar markieren)**.
- **Defekthistorie** und **Ausleihhistorie**.

Mit dem Stift bearbeitest du den Gegenstand.

### Einen Gegenstand anlegen

**+ Neuer Gegenstand** (oder **Gegenstand hinzufügen** am Produkt) öffnet
das Formular. Pflicht sind **Produkt** und **Pool**; die **Bestandsnummer**
schlägt Ausleihbar aus dem Pool vor. Weitere Felder: Seriennummer, Status,
Lagerort, Wert, Beschaffungsdatum, Garantieende, beschaffende und
besitzende Einrichtung und die Eigenschaften des Produkttyps, die am
Gegenstand gepflegt werden.

Unter **Ausleihdauer** kann ein einzelner Gegenstand eigene Mindest- und
Höchstdauern bekommen; sonst übernimmt er die des Produkts
([Ausleihdauer](produkte.md#ausleihdauer)). Unter **Erweitert** steht die
**QR-Code-ID** — sie wird automatisch vergeben. Ändere sie nur, wenn du ein
schon gedrucktes Etikett weiterverwenden willst.

!!! tip "Löschen landet im Papierkorb"
    Gelöschte Produkte und Gegenstände kommen in den
    [Papierkorb](einstellungen.md#papierkorb) und lassen sich dort
    wiederherstellen, bis sie automatisch endgültig entfernt werden.

## Defekte

Verleihtheke → Bestand → **Defekte** sammelt alle Gegenstände deiner Pools,
die als defekt markiert sind (**Aktuell defekt**) oder es schon einmal
waren (**Früher defekt**) — mit Datum, Notiz, wie oft der Gegenstand schon
ein Problem hatte, und gegebenenfalls dem GitLab-Ticket. Ein Klick auf den
Gegenstand öffnet seine Detailseite, wo du ihn reparierst oder ausmusterst.

![Seite „Defekte“: der Knopf „GitLab verbinden“, darunter „Aktuell defekt (1)“ mit MED-0003 · Sony Alpha 7 IV im Medienlabor, defekt seit 26.09.2026 mit der Notiz „Sucher zeigt Pixelfehler, Reparatur angefragt.“, Verlauf „1× Problem“ und ohne Ticket; „Früher defekt (0)“ ist leer](../bilder/theke-defekte.png)

Was beim Markieren als defekt mit den Buchungen passiert, steht in
[Defekte melden](ausgabe.md#defekte-melden). Je nach Einrichtung erinnert
Ausleihbar das Verleihteam außerdem regelmäßig per Mail an Gegenstände, die
schon länger defekt sind, damit sie repariert oder ausgemustert werden.

### GitLab verbinden (optional)

Führt dein Team Reparaturen in GitLab, kann Ausleihbar für jeden neuen
Defekt automatisch ein Issue anlegen. **GitLab verbinden** richtest du je
Pool ein:

1. **GitLab-Projekt-URL:** die vollständige Adresse des Projekts samt
   Server, z. B. `https://gitlab.example.org/team/devices`.
2. **Zugriffstoken:** In GitLab unter Einstellungen → Zugriffstoken einen
   Projekt-Zugriffstoken mit der Rolle „Reporter“ und nur dem Scope „api“
   erstellen und hier einfügen.
3. **Speichern.** Der Token wird danach nie wieder angezeigt, nur ob einer
   hinterlegt ist.

Jedes Ticket verlinkt zurück zu Ausleihbar. Ist GitLab einmal nicht
erreichbar, wird der Defekt trotzdem gespeichert. Zum Abschalten die URL
leeren oder **Token entfernen**.

## QR-Etiketten

Jeder Gegenstand hat einen eigenen QR-Code. Verleihtheke → Bestand →
**QR-Etiketten** druckt sie als Aufkleber. An der Theke scannst du sie bei
Ausgabe und Rücknahme ([QR-Seite](ausgabe.md#die-qr-seite)); Ausleihende,
die sie mit dem Handy scannen, landen auf der Produktseite.

![Seite „QR-Etiketten“: Pool Medienlabor, Feld „Erstellt seit“, Format „Band · 36 mm (Brother P-touch PT-E920BT)“, der Knopf „18 Etiketten drucken“, die Auswahlliste mit MED-0001 bis MED-0009 und darunter die Vorschau der Etiketten mit QR-Code, Bestandsnummer, Produkt und Pool](../bilder/theke-qr-etiketten.png)

1. Wähle den **Pool**. Mit **Erstellt seit** beschränkst du die Liste auf
   neu angelegte Gegenstände, etwa nach einer Lieferung.
2. Wähle das **Format** passend zu deinem Drucker: Bänder für Brother
   P-touch (24 oder 36 mm), Rollen für Brother QL und DYMO oder ein
   A4-Blatt zum Ausschneiden.
3. Hake die Gegenstände an (**Alle auswählen** / **Keine auswählen**) und
   klicke **… Etiketten drucken**.

Jedes Etikett zeigt QR-Code, Bestandsnummer, Produkt und Pool.
