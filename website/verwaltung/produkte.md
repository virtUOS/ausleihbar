---
title: Produkte anlegen
description: Ein Produkt im Katalog anlegen und bearbeiten – Produkttyp, Texte, Bilder, Ausleihart, Nutzung vor Ort, Ausleihdauer, Kategorien, ergänzende Gegenstände und die Rücknahme-Information.
---

# Produkte anlegen

Produkte sind der Katalog, den Ausleihende im Verleih sehen. Ein Produkt
gehört keinem Pool; welche Pools es verleihen, ergibt sich aus seinen
[Gegenständen](gegenstaende.md). Alle Verleihenden können Produkte anlegen
und bearbeiten.

Du öffnest das Formular unter Verleihtheke → Bestand → Gegenstände mit
**+ Neues Produkt** oder am Produkt über **⋮** → **Produkt bearbeiten**.
Gespeichert wird mit **Speichern** in der Leiste am unteren Rand.

![Produktformular „Sony Alpha 7 IV bearbeiten“, Abschnitt „Allgemein“: Produkttyp Kamera, Titel und Kurzbeschreibung jeweils mit den Sprachumschaltern DE und EN, Produktdetails mit Textformatierung und darunter das Feld für Bilder; unten die Leiste mit Speichern und Abbrechen](../bilder/produktformular.png)

## Allgemein

- **Produkttyp:** Pflicht. Der Typ legt fest, welche
  [Eigenschaften](#eigenschaften) das Produkt hat. Produkttypen pflegt die
  Administration ([Produkttypen](katalog.md#produkttypen)).
- **Titel** (Pflicht) und **Kurzbeschreibung** – ein kurzer Satz, was
  das Produkt ist.
- **Produktdetails:** formatierter Text mit Überschriften, Listen, Links
  und Bildern, z. B. was zum Lieferumfang gehört.
- **Bilder:** Bilder hierher ziehen oder klicken, mehrere sind möglich.
  Die Reihenfolge änderst du durch Ziehen; das erste ist das **Titelbild**.

!!! info "Deutsch und Englisch"
    Texte haben die Umschalter **DE** und **EN**. Ein Punkt zeigt, ob die
    Sprache ausgefüllt ist. Fehlt eine Sprache, sehen Ausleihende die
    andere. Ist bei deiner Installation eine **maschinelle Übersetzung**
    eingerichtet, kannst du einen Text mit „Aus … übersetzen“ aus der
    anderen Sprache übernehmen.

!!! tip "Aus PDF ausfüllen (KI) – nur, wenn eingerichtet"
    Ist bei deiner Installation ein KI-Dienst angebunden, steht nach der Wahl
    des Produkttyps **Aus PDF ausfüllen (KI)** zur Verfügung. Du lädst ein
    Handbuch oder Datenblatt hoch (max. 20 MB), und Ausleihbar füllt Titel,
    Beschreibungen und Eigenschaften aus – nur leere Felder, vorhandene
    Einträge bleiben. Der Text des PDFs wird dafür an den KI-Dienst
    geschickt, das PDF selbst wird nicht gespeichert. Prüfe das Ergebnis vor
    dem Speichern. Die KI-Unterstützung ist immer optional.

## Ausleihe

**Art der Nutzung**
:   **Ausleihe** – der Gegenstand wird mitgenommen.
    **Nutzung vor Ort** – der Gegenstand oder Raum wird im gebuchten
    Zeitraum vor Ort genutzt, etwa ein Studio oder ein 3D-Drucker. Dann
    gibt es zusätzlich **Ausgabe an der Theke nötig**:
    angehakt läuft die Buchung über Ausgabe und Rücknahme wie eine
    Ausleihe; ohne Haken ist sie nur ein Zeitfenster und wird nach ihrem
    Ende automatisch abgeschlossen. Wie das für Ausleihende aussieht,
    steht in [Nutzung vor Ort](../anleitung/abholung.md#nutzung-vor-ort).

**Ausleihart**
:   **Tage** oder **Stunden** – ob im Kalender ganze Tage oder einzelne
    Stunden gebucht werden.

### Ausleihdauer

**Mindestdauer** und **Maximaldauer** begrenzen, wie kurz oder lang eine
Buchung sein darf, in der Einheit der Ausleihart. Ohne eigenen Wert
(**Vom Pool übernehmen**) gilt die Vorgabe des Pools. Die Grenze wird von
unten nach oben gesucht:

1. ein eigener Wert am **Gegenstand**,
2. sonst der Wert am **Produkt**,
3. sonst die Standard-Ausleihdauer des **Pools**,
4. sonst keine Grenze.

Im Verleih lässt sich ein Zeitraum außerhalb der Grenzen nicht in den
Warenkorb legen; an der Theke ist er nur eine
[Warnung](direktausleihe.md#warnungen-statt-verbote). Passt eine
Mindestdauer nicht zur Höchstdauer eines Pools, warnt das Formular, dass
die Gegenstände dort nicht buchbar wären.

**Pufferzeit zwischen zwei Ausleihen**
:   Mindestzeit zwischen zwei Ausleihen desselben Gegenstands, etwa zum
    Prüfen, Laden oder Reinigen. Gilt nicht für die Direktausleihe.

**Benachrichtigung, wenn Gegenstand fehlt – Vorlauf**
:   Ist ein Gegenstand so lange vor einer Abholung noch nicht zurück
    (überfällig), bucht Ausleihbar die kommende Buchung auf einen freien
    Gegenstand um – oder schreibt der Person, wenn keiner frei ist.
    0 = aus.

## Einordnung im Shop

- **Kategorien:** wo das Produkt in der Shop-Navigation erscheint. Ein
  Produkt kann in mehreren Kategorien stehen. Den Kategorienbaum pflegt die
  Administration ([Kategorien](katalog.md#kategorien)).
  Ist KI eingerichtet, schlägt **Kategorien vorschlagen** bis zu drei
  passende vorhandene Kategorien vor; übernommen wird erst, was du
  auswählst.
- **Ergänzende Gegenstände:** Produkte, die gut dazu passen, etwa ein
  Stativ zur Kamera. Sie erscheinen auf der Produktseite mit ihren Pools.
  Die Verknüpfung gilt in beide Richtungen: Das andere Produkt zeigt dieses
  ebenfalls an. Die Reihenfolge lässt sich ändern.

## Eigenschaften

Hier füllst du die Eigenschaften des Produkttyps aus, etwa Sensor oder
Auflösung bei einer Kamera. Pflichtfelder sind markiert. Ob eine
Eigenschaft im Shop sichtbar ist, legt die Administration im Produkttyp
fest. Eigenschaften, die am einzelnen Gegenstand gepflegt werden (z. B.
„letzte Wartung“), stehen nicht hier, sondern im
[Formular des Gegenstands](gegenstaende.md#einen-gegenstand-anlegen).

## Für Verleihende

**Rücknahme-Information**
:   Ein Hinweis, der nur dem Verleihteam bei der Rückgabe angezeigt wird,
    z. B. „Akku, Ladegerät und Speicherkarte vollständig? Sucher auf
    Kratzer prüfen.“ Ist er ausgefüllt, öffnet jede Rückgabe des Produkts
    den Dialog [Rückgabe prüfen](ausgabe.md#zurücknehmen). Für Ausleihende
    unsichtbar.

!!! tip "Nach dem Speichern"
    Ein neues Produkt ist erst buchbar, wenn es mindestens einen
    verfügbaren Gegenstand in einem aktiven Pool hat. Leg also gleich
    über **⋮** → **Gegenstand hinzufügen** die Exemplare an.
