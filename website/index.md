---
title: Gegenstände der Hochschule online ausleihen
description: Ausleihbar ist ein Verleihsystem für Hochschulen — Kameras, Mikrofone, Laptops oder Räume online finden, im Kalender buchen und an der Verleihtheke abholen. Open Source von virtUOS, Universität Osnabrück.
hide:
  - navigation
  - toc
---

<div class="al-hero" markdown>

<div class="al-hero__text" markdown>

<p class="al-eyebrow">Open Source · virtUOS, Universität Osnabrück</p>

<h1 class="al-hero__title">Gegenstände der Hochschule <span>einfach online ausleihen.</span></h1>

<p class="al-hero__lead">
Ausleihbar funktioniert wie ein Onlineshop für alles, was eure Hochschule
verleiht: Kamera, Mikrofon, Laptop oder Podcast-Studio suchen, freie Tage im
Kalender sehen, in den Warenkorb legen und abschicken. Das Verleihteam
bestätigt die Buchung, gibt die Gegenstände an der Verleihtheke aus und nimmt
sie wieder zurück.
</p>

<div class="al-hero__actions" markdown>
[Anleitung für Ausleihende](anleitung/index.md){ .md-button .md-button--primary }
[Für Verleihende & Admins](verwaltung/index.md){ .md-button }
[:fontawesome-brands-github: Quellcode auf GitHub](https://github.com/virtUOS/ausleihbar){ .md-button }
</div>

</div>

<figure class="al-shot al-shot--hero" markdown>
![Startseite von Ausleihbar: Begrüßung „Moin, Alex!“, die Karte „Meine Buchungen“ mit einem Hinweis auf einen überfälligen Gegenstand, Kacheln der Sparten Medientechnik und Räume & Arbeitsplätze sowie die Reihe „Gerade beliebt“](bilder/start.png)
</figure>

</div>

<ul class="al-facts">
  <li><strong>Single Sign-on</strong><span>Anmeldung per OIDC mit der Hochschulkennung</span></li>
  <li><strong>Open Source</strong><span>Apache-Lizenz 2.0, auf GitHub</span></li>
  <li><strong>Deutsch &amp; Englisch</strong><span>Oberfläche, Inhalte und E-Mails</span></li>
  <li><strong>Import aus leihs</strong><span>Bestand aus einem leihs-CSV-Export übernehmen</span></li>
  <li><strong>Barrierearm</strong><span>orientiert an WCAG 2.1 AA und BITV 2.0</span></li>
</ul>

## Was Ausleihbar kann { .al-section-title }

<p class="al-section-lead">Ein Werkzeug für beide Seiten der Theke: Ausleihende finden und buchen selbst, Verleihteams behalten den Überblick über Ausgaben, Rückgaben und den Bestand.</p>

<div class="al-features" markdown>

<div class="al-feature" markdown>
![Kategorie „Foto & Video“ mit Brotkrümelpfad, den Unterkategorien Kameras und Stative, Filterchips und den Produkten, getrennt nach tageweiser und stundenweiser Ausleihe](bilder/kategorie.png)

### Katalog und Suche

Sparten, Kategorien und Unterkategorien führen zum passenden Gegenstand. Die
Suche findet Produkte, Kategorien und Sparten; Favoriten merken sich, was du
öfter brauchst.

[:octicons-arrow-right-24: Gegenstände finden](anleitung/finden.md)
</div>

<div class="al-feature" markdown>
![Verfügbarkeitskalender der Sony Alpha 7 IV für Oktober 2026: Zahl der freien Einheiten je Tag, ein gewählter Zeitraum vom 23. bis 25. und ein geschlossener Tag mit Schloss-Symbol](bilder/produkt-kalender.png)

### Verfügbarkeit im Kalender

Tageweise Produkte zeigen freie Einheiten pro Tag, stundenweise Produkte die
Auslastung pro Tag und freie Stunden. Geschlossene Tage und
Ausleihdauern sind gleich eingerechnet.

[:octicons-arrow-right-24: Produktseite und Verfügbarkeit](anleitung/produkt.md)
</div>

<div class="al-feature" markdown>
![Warenkorb mit zwei Pools, Medienlabor und Podcast-Studio, je einem Gegenstand, der Haltezeit „reserviert bis“, dem Nachrichtenfeld an das Verleihteam und dem Knopf „Buchung abschicken“](bilder/warenkorb.png)

### Warenkorb über mehrere Pools

Gegenstände aus verschiedenen Ausleihstellen landen in einem Warenkorb und
sind dort für dich reserviert. Beim Absenden entsteht je Pool eine Buchung,
die jedes Verleihteam für sich bestätigt.

[:octicons-arrow-right-24: Warenkorb und Buchung absenden](anleitung/warenkorb.md)
</div>

<div class="al-feature" markdown>
![Set-Seite „Interview-Set“ mit Beschreibung, dem Hinweis „Verfügbar in Medienlabor“ und den drei enthaltenen Produkten Kamera, Funkmikrofon und Stativ](bilder/set.png)

### Sets

Was oft zusammen gebraucht wird, liegt als Set bereit — etwa Kamera,
Funkmikrofon und Stativ für ein Interview. Ein Klick bucht alles gemeinsam,
oder gar nichts, wenn etwas fehlt.

[:octicons-arrow-right-24: Sets](anleitung/sets.md)
</div>

<div class="al-feature" markdown>
![„Meine Buchungen“ mit dem Abschnitt „Überfällig“ oben und einer anstehenden, noch nicht bestätigten Buchung darunter, jeweils mit Pool, Adresse und Öffnungszeiten](bilder/meine-buchungen.png)

### Ausleihe oder Nutzung vor Ort

Neben der Ausleihe gibt es die Nutzung vor Ort, etwa für ein Podcast-Studio
oder einen 3D-Drucker — mit oder ohne Ausgabe an der Theke. „Meine
Buchungen“ zeigt jederzeit, was ansteht, was du hast und was überfällig ist.

[:octicons-arrow-right-24: Abholung, Rückgabe und Nutzung vor Ort](anleitung/abholung.md)
</div>

<div class="al-feature" markdown>
![Tagesübersicht der Verleihtheke mit Pool-Filter, Datum und Zählern für Abholungen, Rückgaben, Überfällige, zu Bestätigende und aktuell Verliehene, darunter zwei Buchungen zum Bestätigen](bilder/theke-tagesuebersicht.png)

### Verleihtheke

Die Tagesübersicht bündelt Abholungen, Rückgaben, Überfälliges und neue
Buchungen. Ausgegeben wird per QR-Code: Abhol-Code aus der Mail scannen,
Gegenstände scannen, fertig. Spontane Ausleihen gehen direkt an der Theke.

[:octicons-arrow-right-24: Tagesübersicht](verwaltung/tagesuebersicht.md) ·
[QR-Ausgabe](verwaltung/ausgabe.md) · [Direktausleihe](verwaltung/direktausleihe.md)
</div>

<div class="al-feature" markdown>
![Verwaltung der Zugriffsgruppen: Administratoren, die Gruppe Lehrende mit dem Pool Makerspace und einer Claim-Regel sowie drei Verleiher-Systemgruppen mit ihren Mitgliedern](bilder/admin-zugriffsgruppen.png)

### Zugriffsgruppen und Rollen

Pools lassen sich auf Gruppen beschränken, auch automatisch über Angaben aus
der Anmeldung. Wer verleiht und wer administriert, regeln ebenfalls Gruppen:
je Pool ein Verleihteam, dazu die Administration.

[:octicons-arrow-right-24: Personen und Zugriff](verwaltung/personen.md)
</div>

<div class="al-feature" markdown>
![Statistik der Verleihtheke für 90 Tage: Kacheln zu Ausleihen, Nutzern, verspäteten Rückgaben und Ausleihdauer, darunter der Vergleich der Pools](bilder/theke-statistik.png)

### Statistik

Ausleihen, verspätete Rückgaben, durchschnittliche Ausleihdauer und der
Vergleich der Pools über einen frei wählbaren Zeitraum — mit Anzahlen,
nie mit Namen.

[:octicons-arrow-right-24: Statistik](verwaltung/statistik.md)
</div>

</div>

<div class="grid cards al-more" markdown>

-   :material-cellphone: __Fürs Smartphone gemacht__

    Katalog, Kalender und Warenkorb funktionieren auf dem Handy genauso gut
    wie am Rechner — ganz ohne App.

-   :material-email-outline: __E-Mails mit Kalendereintrag__

    Eingangs- und Bestätigungsmail mit Abhol-QR-Code und `.ics`-Datei, eine
    Erinnerung am Tag vor der Abholung. [Mehr zu den Mails](anleitung/mails.md)

-   :material-calendar-lock-outline: __Sperrtage und Feiertage__

    Feiertage und Schließtage sind keine Abhol- oder Rückgabetage. Kommt
    ein Sperrtag dazu, werden betroffene Buchungen umgebucht oder storniert
    — mit E-Mail an die Ausleihenden.

-   :material-alert-octagon-outline: __Strikes__

    Läuft bei einer Buchung etwas schief, etwa eine verpasste Abholung, kann
    das Verleihteam einen Strike vergeben; ab einer Schwelle wird das Konto
    für neue Buchungen gesperrt.
    [Mehr zu Strikes](anleitung/strikes.md)

</div>

## Für wen { .al-section-title }

<div class="grid cards al-audience" markdown>

-   :material-account-outline: __Ausleihende__

    ---

    Studierende und Beschäftigte, die etwas für Seminar, Projekt oder
    Abschlussarbeit brauchen: anmelden, suchen, buchen, abholen.

    [:octicons-arrow-right-24: Zur Anleitung](anleitung/index.md)

-   :material-handshake-outline: __Verleihteams__

    ---

    Medienlabor, Bibliothek, Makerspace: Buchungen bestätigen, ausgeben und
    zurücknehmen, Bestand pflegen, Defekte verfolgen, QR-Etiketten drucken.

    [:octicons-arrow-right-24: Für Verleihende & Admins](verwaltung/index.md)

-   :material-server-network: __Hochschulen und Rechenzentren__

    ---

    Selbst betreiben mit Docker Compose, Anmeldung über den eigenen Identity
    Provider (OIDC), bestehenden Bestand aus leihs importieren.

    [:octicons-arrow-right-24: Zur Installation](installation.md)

</div>

<div class="al-cta" markdown>

<div markdown>

## Open Source · selbst betreiben { .al-cta__title }

Ausleihbar steht unter der Apache-Lizenz 2.0 und läuft als
Docker-Compose-Stack aus PostgreSQL, Django und der React-Oberfläche, im
Betrieb hinter Caddy mit automatischem HTTPS. Die Installationsanleitung
führt Schritt für Schritt bis zum eigenen Server. Den Quellcode findest du
auf GitHub — zum Prüfen, Betreiben und Mitentwickeln.

</div>

<div class="al-cta__actions" markdown>
[Zur Installationsanleitung](installation.md){ .md-button .md-button--primary }
[:fontawesome-brands-github: virtUOS/ausleihbar](https://github.com/virtUOS/ausleihbar){ .md-button }
</div>

</div>
