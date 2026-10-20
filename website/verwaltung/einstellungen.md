---
title: Einstellungen
description: Für Admins — Sperrtage und Feiertage, die Haltezeit des Warenkorbs, eigene Texte und Versandzeiten der Mails, Inhaltsseiten, Import und Export des Katalogs und der Papierkorb.
---

# Einstellungen

Administration → **Einstellungen** bündelt alles, was für die ganze
Installation gilt.

## Sperrtage und Feiertage

An einem **Sperrtag** sind keine Buchungen möglich: keine Abholung, keine
Rückgabe, keine Nutzung. Ausleihende sehen ihn im Kalender mit einem
Schloss.

![Seite „Sperrtage“: oben „Gesetzliche Feiertage“ mit Land DE, Bundesland NI und dem Knopf „Speichern & Feiertage laden“, darunter das Formular mit Von, Bis (optional), Geltungsbereich „Alle Pools (systemweit)“ und Grund sowie die Liste: Betriebsausflug und Inventur im Medienlabor, Erster und Zweiter Weihnachtstag in allen Pools](../bilder/admin-sperrtage.png)

**Gesetzliche Feiertage**
:   Trage **Land** und **Bundesland / Region** ein (z. B. DE und NI) und
    klicke **Speichern & Feiertage laden**. Ausleihbar trägt die
    gesetzlichen Feiertage als systemweite Sperrtage für den ganzen
    Buchungshorizont ein — so weit, wie der Pool mit dem längsten Horizont
    Buchungen erlaubt. Zum Aktualisieren erneut speichern. Einzelne
    Feiertage kannst du in der Liste entfernen, wenn ihr trotzdem öffnet.

**Eigene Sperrtage**
:   **Von**, optional **Bis**, der **Geltungsbereich** — **Alle Pools
    (systemweit)** oder ein einzelner Pool — und optional ein **Grund**,
    z. B. „Betriebsferien“. Dann **Sperrtag hinzufügen**. Vergangene
    Sperrtage blendet die Liste aus; du kannst sie wieder einblenden.

!!! warning "Was mit bestehenden Buchungen passiert"
    Fällt ein neuer Sperrtag auf vorhandene Buchungen, passt Ausleihbar sie
    an: Eine Abholung am Sperrtag rückt auf den nächsten offenen Tag, eine
    Rückgabe am Sperrtag ebenso. Passt der verschobene Zeitraum nicht mehr
    auf den Gegenstand, nimmt Ausleihbar einen freien gleichen Gegenstand,
    sonst wird die Buchung storniert. Eintägige und stundenweise Buchungen
    am Sperrtag werden storniert. Die Betroffenen bekommen eine Mail, und
    du siehst, wie viele Buchungen umgebucht und storniert wurden.

Sperrtage für einen einzelnen Pool kannst du auch direkt im
[Pool-Formular](katalog.md#pools) pflegen.

## Warenkorb

Legt jemand ein Produkt in den Warenkorb, ist ein Gegenstand für ihn
reserviert. Die **Warenkorb-Haltedauer (Minuten)** bestimmt, wie lange
(ohne eigene Einstellung 30 Minuten). Jede Aktion im Warenkorb erneuert die
Frist; läuft sie ab, ist der Gegenstand wieder frei. Abgeschickte Buchungen
betrifft das nicht. Wie das für Ausleihende aussieht, steht in
[Reserviert — aber nicht ewig](../anleitung/warenkorb.md#reserviert--aber-nicht-ewig).

## Benachrichtigungen

Hier passt du die Mails an Ausleihende an. Die persönliche Anrede, die
Buchungsnummer, die Buchungsdetails und der Link bleiben immer drin; dein
Text wird darum herum eingefügt.

![Seite „Benachrichtigungen“: links die Versandzeit für gesammelte Bestätigungen (17:00) und die Felder für Einleitungs- und Schlusstext bei eingehenden Reservierungen, jeweils DE/EN; rechts die Auswahl der Mails (Reservierung eingegangen, Bestätigung, Umbuchung, Storniert, Erinnerung, Gegenstand defekt, Gegenstand fehlt, Abholerinnerung), die Vorschausprache und die Live-Vorschau mit Musterdaten](../bilder/admin-benachrichtigungen.png)

**Versandzeit für gesammelte Bestätigungen**
:   Bei Bestellungen über mehrere Pools sammelt Ausleihbar
    Teilbestätigungen und verschickt sie zu dieser Uhrzeit
    ([mehr dazu](tagesuebersicht.md#buchungen-bestätigen)).

**Eigene Texte**
:   Je Mail gibt es passende Felder, etwa Einleitungs- und Schlusstext bei
    eingehenden Reservierungen, eine Begründung und einen zusätzlichen
    Absatz bei Umbuchung oder Stornierung wegen eines Sperrtags, einen
    Absatz in der Überfällig-Erinnerung (z. B. „Verspätete Rückgaben können
    zu einem Strike führen.“) und in der Mail, wenn ein reservierter
    Gegenstand ausfällt. Alle Felder sind optional und haben Deutsch und
    Englisch. Ist eine Sprache leer, nimmt Ausleihbar die andere; sind
    beide leer, den eingebauten Standardtext.

**Erinnerung vor der Abholung**
:   **Abholerinnerung einen Tag vorher senden** schaltet die Mail am Vortag
    der Abholung ein oder aus. Sie enthält Adresse, Öffnungszeiten und
    Wegbeschreibung. Die **Versandzeit** legt fest, ab wann am Vortag sie
    rausgeht; dazu kommt ein optionaler eigener Text, etwa „Bitte bring
    deinen Studierendenausweis mit.“

**Vorschau**
:   Rechts siehst du jede Mail mit Musterdaten, auf Deutsch oder Englisch.
    Farben zeigen, was von dir kommt (**Dein Text**), was aus dem Pool
    (**Aus dem Pool**) und was automatisch eingesetzt wird.

Hinweise, die nur einen Pool betreffen, pflegst du am Pool
(**Hinweis in Bucher-Mails**, siehe [Pools](katalog.md#pools)). Welche Mails
Ausleihende bekommen, steht in
[E-Mails und Erinnerungen](../anleitung/mails.md).

## Seiten

Unter **Seiten** pflegst du Inhaltsseiten wie Impressum oder Datenschutz.
Jede Seite hat einen **Titel**, ein **URL-Kürzel**, einen formatierten
**Inhalt** (Deutsch und Englisch) und ist **Veröffentlicht** oder
**Entwurf**. Mit **In Fußzeile anzeigen** erscheint sie als Link in der
Fußzeile; die Reihenfolge stellst du mit **Neu anordnen** ein.

Zwei eingebaute Seiten haben eigene Formulare:

- **Startseite** — Begrüßungstext und **Verleih-Logo** für Besucher, die
  nicht angemeldet sind. Darunter listet Ausleihbar automatisch die Pools
  mit ihren Bildern.
- **Verleih-Startseite** — was Angemeldete auf der Startseite sehen:
  ob die Zeilen **„Gerade beliebt“** und **„Neu dazugekommen“** erscheinen
  und wie viele Tage neue Produkte das Label „Neu“ tragen.

!!! note "Datenschutzerklärung pflegen"
    Die Datenschutzseite schreibt ihr selbst; Ausleihbar erzeugt sie nicht.
    Prüft sie, wenn sich ändert, welche Daten ihr speichert, etwa bei einer
    neuen Datenaufbewahrungsregel ([Datenaufbewahrung](personen.md#datenaufbewahrung)).

## Import und Export

**Import / Export** sichert den Katalog als ZIP-Archiv oder überträgt ihn
in eine andere Installation: Sparten, Kategorien, Produkttypen, Produkte,
Sets, Pools und Inventar, mit Bildern. **Buchungen, Benutzer und andere
personenbezogene Daten sind nie enthalten.**

- **Export:** **Gesamtsystem exportieren** oder einen einzelnen Pool mit den
  Produkten, die seine Gegenstände brauchen (**Pool exportieren**).
- **Import:** Archiv bis 2 GB wählen und zuerst **Probelauf (Vorschau)**
  ausführen — er zeigt, was neu angelegt, aktualisiert oder umgewandelt
  würde, ohne etwas zu speichern. Vorhandene Einträge erkennt Ausleihbar an
  ihrem Schlüssel (Name, Inventarnummer …) und aktualisiert sie; fehlende
  legt es neu an.

!!! warning "Kein Ersatz für eine Datensicherung"
    Das Archiv enthält nur den Katalog. Für eine vollständige Sicherung
    braucht ihr ein Backup von Datenbank und Mediendateien (siehe
    [Installation](../installation.md)).

Den Bestand aus **leihs** übernimmt ein Kommandozeilenbefehl der
Installation; Details stehen in der
[leihs-Anleitung im Repository](https://github.com/virtUOS/ausleihbar/blob/main/docs/leihs-import.md).
Das Archivformat beschreibt
[data-transfer.md](https://github.com/virtUOS/ausleihbar/blob/main/docs/data-transfer.md).

## Papierkorb

Gelöschte Sparten, Kategorien, Produkttypen, Produkte, Gegenstände, Sets
und Pools landen zuerst im **Papierkorb**. Dort siehst du, wer sie wann
gelöscht hat und wann sie automatisch endgültig gelöscht werden.

- **Wiederherstellen** holt einen Eintrag zurück.
- **Endgültig löschen** bzw. **Papierkorb leeren** entfernt Einträge sofort —
  das lässt sich nicht rückgängig machen.
- Unter **Aufbewahrung** legst du fest, wie viele Tage gelöschte Einträge
  aufbewahrt werden (ohne eigene Einstellung 30).
