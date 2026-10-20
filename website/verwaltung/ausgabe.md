---
title: Ausgabe, Rücknahme und QR-Codes
description: Gegenstände an der Verleihtheke aushändigen und zurücknehmen — per Knopf in der Tagesübersicht oder per Scan auf der QR-Seite, mit Rückgabeprüfung und Defektmeldung.
---

# Ausgabe, Rücknahme und QR-Codes

Ausgeben und zurücknehmen kannst du auf zwei Wegen: mit einem Klick in der
[Tagesübersicht](tagesuebersicht.md) oder in [Alle Buchungen](buchungen.md),
oder per Scan auf der Seite **QR-Codes**. Beides führt zum selben Ergebnis;
der Scan prüft zusätzlich, ob du wirklich die richtigen Gegenstände in der
Hand hast.

## Aushändigen per Knopf

In den Abschnitten **Abholungen** und **⚠ Überfällig** steht an jedem
Zeitraum einer bestätigten Buchung der Knopf **Aushändigen**.

1. Such die Buchung heraus, z. B. über den Namen oder die Buchungsnummer
   (R-…), die die Person nennt.
2. Gib die aufgeführten Gegenstände heraus — die Bestandsnummer steht hinter
   dem Produkt, z. B. „Zoom H6 · MED-0015“.
3. Klicke **Aushändigen**. Alle noch offenen Gegenstände dieses Zeitraums
   gelten jetzt als ausgegeben; die Buchung hat den Status **Abgeholt**.

![Abschnitt „Abholungen (2)“ im Medienlabor: Alex Beispiel mit R-00537, Status „Bestätigt“, Zeitraum 20.10.2026 – 22.10.2026, Zoom H6 · MED-0015 und der Knopf „Aushändigen“; bei der zweiten Buchung von Jona Muster ist das Menü der Buchungsaktionen mit „Strike vergeben“ und „Buchung stornieren“ geöffnet](../bilder/theke-ausgabe.png)

Im Menü **⋮** der Buchung findest du **Strike vergeben** und, solange
nichts ausgegeben ist, **Buchung stornieren**. Das kleinere Menü **⋮** an
einem einzelnen Gegenstand bietet **Als defekt markieren** bzw. **Als
repariert markieren**.

!!! tip "Lieber scannen"
    Bei Buchungen mit mehreren Gegenständen oder wenn mehrere gleiche
    Gegenstände im Regal liegen, ist die [QR-Seite](#die-qr-seite) sicherer:
    Sie merkt, wenn du einen anderen Gegenstand greifst als den reservierten,
    und trägt dann den richtigen ein.

## Zurücknehmen

In **Fällige Rückgaben** und **⚠ Überfällig** steht an ausgegebenen
Gegenständen der Knopf **Rückgabe**.

- Ohne Prüfhinweis wird sofort zurückgebucht.
- Hat mindestens ein Produkt eine **Rücknahme-Information** (siehe
  [Produkte anlegen](produkte.md#für-verleihende)), öffnet sich der Dialog
  **Rückgabe prüfen**. Er zeigt zu jedem Gegenstand den Hinweis, etwa
  welches Zubehör dazugehört. Wähle je Gegenstand **Alles in Ordnung** oder
  **Defekt melden** (mit kurzer Beschreibung, „Was ist das Problem?“) und
  schließe mit **Rückgabe abschließen** ab. **Abbrechen** bricht die ganze
  Rückgabe ab, es wird nichts gebucht.

Ist alles zurück, hat die Buchung den Status **Zurückgegeben**.

## Defekte melden

Einen Gegenstand als defekt markieren kannst du bei der Rückgabe, über das
Menü **⋮** am Gegenstand, auf der QR-Seite oder auf der Seite
[Gegenstände](gegenstaende.md). Dann passiert Folgendes:

- Der Gegenstand hat den Status **Defekt** und wird nicht mehr verliehen.
- Spätere Buchungen dieses Gegenstands bucht Ausleihbar auf einen freien
  gleichen Gegenstand im selben Pool um. Gibt es keinen, bekommt die
  betroffene Person eine Mail, und du siehst einen Hinweis, wie viele
  Buchungen nicht verschoben werden konnten.
- Ist es im Pool eingestellt, bekommt die Kontaktadresse des Pools eine
  Mail, und — wenn GitLab verbunden ist — entsteht ein Ticket
  ([Defekte und GitLab](gegenstaende.md#defekte)).

Ist der Gegenstand wieder heil, wähle **Als repariert markieren**.

## Die QR-Seite

Die Seite **QR-Codes** (Bereichsmenü oben rechts) ist für die Arbeit an
der Theke gemacht. Scanne mit der Kamera deines Tablets oder Handys (**Kamera verwenden**)
oder mit einem Handscanner, oder tippe den Code ein. Sie versteht zwei Arten
von Codes:

- den **Abhol-QR-Code** aus der Bestätigungsmail der Person oder ihre
  Buchungsnummer (R-…),
- das **QR-Etikett** eines Gegenstands ([QR-Etiketten](gegenstaende.md#qr-etiketten)).

Je nachdem, was du scannst, entscheidet die Seite selbst, was zu tun ist:

| Du scannst … | Die Seite … |
| --- | --- |
| einen Abhol-Code | lädt die Buchung zum Ausgeben („R-… für … geladen.“) |
| einen Gegenstand, der gerade verliehen ist | öffnet die Rücknahme seiner Buchung |
| einen Gegenstand, dessen bestätigte Abholung schon begonnen hat | lädt diese Buchung zum Ausgeben |
| einen anderen Gegenstand | zeigt seinen **Lagerort** und lässt dich ihn als defekt oder verfügbar markieren |

### Ausgeben per Scan

1. Scanne den Abhol-Code der Person.
2. Scanne unter **Gegenstände scannen** nacheinander die Etiketten der
   Gegenstände, die du herausgibst. Jeder passende Gegenstand wird mit
   „✓ … zugeordnet“ bestätigt und als **Bereit** markiert.
3. Klicke **… gescannten Gegenstand ausgeben**.

![QR-Seite nach dem Scan: „✓ MED-0015 zugeordnet“, darunter die Buchung R-00721 von Alex Beispiel im Medienlabor mit Status „Bestätigt“, der Zoom H6 (MED-0015) als „Bereit“ und der Knopf „1 gescannten Gegenstand ausgeben“](../bilder/theke-qr.png)

Scannst du etwas, das nicht genau passt, fragt die Seite nach:

- **Gleiches Produkt, anderer Gegenstand:** „… gescannt — gebuchter
  Gegenstand ist …“. Mit **Gegenstand tauschen** wird der gescannte
  Gegenstand in die Buchung eingetragen.
- **Gegenstand gehört nicht zur Buchung:** Mit **Als Extra hinzufügen**
  kommt er zusätzlich in die Buchung, z. B. ein Ersatzakku, den die Person
  spontan mitnimmt.

Gegenstände zur Nutzung vor Ort ohne Ausgabe stehen nur zur Information da;
scannst du einen, meldet die Seite, dass er ohne Ausgabe vor Ort genutzt
wird.

### Zurücknehmen per Scan

Scanne das Etikett eines verliehenen Gegenstands; die Seite öffnet die
Rücknahme seiner Buchung. Wähle die zurückkommenden Gegenstände durch Tippen
oder Scannen aus und klicke **… Gegenstand zurücknehmen**. Gegenstände mit
Rücknahme-Information sind mit „bei Rückgabe prüfen“ markiert; für sie
öffnet sich der Dialog **Rückgabe prüfen** wie oben. So kannst du auch nur
einen Teil einer Buchung zurücknehmen.

!!! info "Codes für Ausleihende"
    Scannt jemand ohne Verleihrechte ein Gegenstands-Etikett mit dem Handy,
    landet er auf der Produktseite im Verleih. Der Abhol-QR-Code und der
    Kalendereintrag kommen nur als Anhang der
    [Bestätigungsmail](../anleitung/mails.md#bestätigungsmail); die
    Buchungsseite im Verleih zeigt keinen QR-Code.

Wie die Ausgabe aus Sicht der Ausleihenden aussieht, steht in
[Abholung, Rückgabe und Nutzung vor Ort](../anleitung/abholung.md).
