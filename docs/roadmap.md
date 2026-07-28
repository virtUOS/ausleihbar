# Roadmap & Scope — Ausleihbar

Dieses Dokument schneidet das Konzept (`docs/concept.md`) in lieferbare Stufen:
**MVP** (erste lauffähige Version), **v2** (kurz danach) und **Ausblick**
(später / optional). Es ist die Grundlage für die Fundament-ADRs in
`docs/decisions/`.

> Lebendiges Dokument — wird beim Fortschreiten angepasst. Bei Konflikten
> zwischen Roadmap und Konzept gewinnt das Konzept als Vision; die Roadmap
> sagt nur, *wann* etwas gebaut wird.

## Festgelegte Grundsatzentscheidungen

Diese drei Weichen sind gestellt und werden je in einem ADR ausgearbeitet:

1. **Single-Tenant, tenant-ready.** v1 läuft für *eine* Einrichtung. Die
   Modelle werden aber so entworfen, dass eine Mandanten-Zuordnung später
   ohne großen Umbau ergänzt werden kann (z. B. optionale `tenant`-Relation
   von Beginn an mitdenken). → ADR „Multi-Tenancy-Strategie".
2. **OIDC/Keycloak ab v1.** Authentifizierung läuft von Anfang an über OIDC
   (Keycloak). Shibboleth und Selbstregistrierung kommen später.
   → ADR „Authentifizierung & Identitäten".
3. **Tages- und stundenweise Buchung ab v1.** Beide Ausleiharten sind im MVP,
   inklusive Öffnungszeiten-Prüfung für stundenweise Buchungen.
   → ADR „Verfügbarkeits- & Buchungs-Engine".

## MVP-Ziel (der durchgängige Loop)

> Eine ausleihende Person meldet sich per OIDC an, durchsucht auf dem Handy
> den Katalog des Ressourcenpools, sieht tages- oder stundenweise
> Verfügbarkeit, legt Geräte in den Warenkorb und reserviert sie. Eine
> verleihende Person sieht die Tagesübersicht, bestätigt die Reservierung,
> gibt aus und nimmt zurück. Admins/Verleihende pflegen Pools, Produktarten,
> Produkte und Kategorien/Sparten.

Wenn dieser Loop sauber funktioniert, ist die erste Version sinnvoll nutzbar.

## Feature-Bereiche

| Bereich | MVP (v1) | v2 / Ausblick |
|---|---|---|
| **A — Katalog & Shop** | Sparten/Kategorien/Produkte/Produktarten, Produkt-Detailseite, Browsing nach Sparte/Kategorie, einfache Suche | Fehlertolerante Fuzzy-Suche, A-Z-Liste mit localStorage, Verfügbarkeits-Farbcodes in der Liste |
| **B — Verfügbarkeit & Buchung** | Tages- **und** stundenweise Buchung, Verfügbarkeitsberechnung über Zeit, Warenkorb, unbestätigte Reservierung, Öffnungszeiten-Prüfung (Stunden) | Sets, „spontane Sets" im Warenkorb, komplexe Blockzeiten-Regeln (Verlängern/Verkürzen der max. Dauer) |
| **C — Accounts & Auth** | OIDC/Keycloak-Login, Custom User Model, Rollen (Ausleihende/Verleihende/Admin) | Shibboleth, Selbstregistrierung + Verifizierung, Strikes-System inkl. Sperrlogik |
| **D — Verleih-Betrieb** | Reservierung bestätigen, Tagesübersicht (Ausgaben/Rückgaben), Ausgabe & Rückgabe markieren, Defekt-Markierung | QR-Ausgabeseite + digitale Unterschrift, automatische Umbuchung bei Defekt, Überfälligkeits-/Nicht-Abhol-Archivierung, spontane Ausleihen |
| **E — Verwaltung/Admin** | CRUD für Ressourcenpools, Produktarten, Produkte, Kategorien/Sparten; Inventar-Liste | Produkt-als-Vorlage klonen, Set-Verwaltung, erweiterte Inventar-Filter/-Sortierung |
| **F — Multi-Tenancy** | *zurückgestellt* (ein Tenant), Modelle aber tenant-ready | Echte Mandantenfähigkeit unter eigenen URLs, getrennte Sichtbarkeit |
| **G — Benachrichtigungen** | Basis-Email bei Reservierung und Bestätigung (mit Pool-Infos/Öffnungszeiten) | Kalendereinträge (.ics), Erinnerungs-Intervalle, Defekt-Nachfragen an Verleihende |
| **H — Statistiken** | *zurückgestellt* | Auslastung pro Ressource/Produkt/Pool, Defektquoten |
| **I — i18n & Mobile-first** | Mobile-first Ausleih-Views, i18n-Infrastruktur (DE zuerst) | Vollständige EN-Übersetzung, weitere Sprachen leicht ergänzbar |

## Bewusst NICHT im MVP

Damit der Fokus klar ist — diese Punkte sind erkannt, aber vertagt:
Multi-Tenancy, Shibboleth, Selbstregistrierung & Verifizierung, Strikes,
Sets, automatische Defekt-Umbuchung, digitale Unterschrift, Kalendereinträge,
Statistiken, fehlertolerante Suche, A-Z-Liste, Verfügbarkeits-Farbcodes.

## Klärungsbedarf im Konzept (vor Umsetzung beantworten)

- **Begriff „Sparte":** im Code aktuell `Department` — auf `Section`
  vereinheitlichen? (Konzept nutzt durchgehend „Sparte".)
- **Set-Semantik:** entschieden — ein Set ist eine *Liste von Produkten*
  (obere Konzept-Definition gewinnt). Das aktuelle Modell (`ProductSet` als M2M
  auf `Product`) passt bereits.
- **Produktart-Attribute:** brauchen pro Eigenschaft Key + Value-**Typ**
  (Kurztext/Langtext/Datum/Zeit/Zahl/URL/Medien/Bild) + Default-Wert + zwei
  Booleans (sichtbar, Pflichtfeld). Schema-Definition in `ProductType`
  entsprechend ausarbeiten.
- **Nutzendenverifizierung:** vereinfacht — nur Account-Bestätigung durch
  Verleihende beim Erstkontakt, keine Ausweisdaten. (Betrifft erst die
  Selbstregistrierung, Ausblick.)
- **Kalendereintrag bei mehreren Terminen (Z. 205):** offene Frage aus dem
  Konzept; betrifft Benachrichtigungen (Ausblick).

## Nächste Schritte

1. Diese Roadmap gegenlesen / anpassen.
2. **Fundament-ADRs** schreiben: Multi-Tenancy, Auth (OIDC/Keycloak),
   Verfügbarkeits-/Buchungs-Engine, App-Struktur, Custom User Model.
3. Erst danach Code: Custom User Model + App-Struktur, dann Domäne pro
   Bereich (Katalog → Buchung) mit Migration, Tests und `/code-review`.
