---
title: Personen und Zugriff
description: Für Admins — Benutzer und ihre Rollen, Zugriffsgruppen mit Claim-Regeln und Systemgruppen, die Strike-Regeln und die automatische Datenaufbewahrung.
---

# Personen und Zugriff

Administration → **Personen & Zugriff** regelt, wer was sehen, buchen,
verleihen und verwalten darf. Konten entstehen bei der ersten Anmeldung
über das Single Sign-on; anlegen musst du niemanden.

## Benutzer

Die Liste zeigt alle Konten mit Benutzername, Name, E-Mail und ihren
**Rollen** als Etiketten: **Entleiher**, **Verleiher · n** (für n Pools),
**Admin**, dazu **… Strike** und **Gesperrt**. Ein Klick auf ein Etikett
filtert die Liste danach, ebenso **Inaktiv**; das Suchfeld findet Name oder
E-Mail.

![Benutzerliste: alex · Alex Beispiel (Entleiher), jona · Jona Muster (Entleiher, 1 Strike), kim · Kim Verleih (Verleiher · 2), lea · Lea Lernfeld und mika · Mika Probe (Entleiher), robin · Robin Gesperrt (Entleiher, Gesperrt) und sam · Sam Admin (Admin), jeweils mit E-Mail und Stift zum Bearbeiten](../bilder/admin-nutzer.png)

Der Stift öffnet die Details eines Kontos:

- **Admin (voller Zugriff auf alle Pools und die Verwaltung)** — dieses
  Häkchen dürfen nur Admins mit vollen Systemrechten setzen. Sonst vergibst
  du Adminrechte über die Gruppe **Administratoren**. Kommt die Admin-Rolle
  aus einer Gruppe des Identity Providers, ist sie hier nicht änderbar.
- **Konto aktiv** — abwählen sperrt die Anmeldung.
- **Mitglied von Zugriffsgruppen** — die manuellen Mitgliedschaften.
- **Verleiher für … Pool** — die Pools, die die Person betreut. Kommt das
  Recht über eine andere Gruppe, steht „über Gruppe(n) …“ dabei.
- **Strikes & Sperrung** — alle Strikes mit Grund und Ablauf. Hier kannst
  du einen Strike **löschen**, selbst einen **vergeben** und eine Sperre mit
  **Entsperren** aufheben.
- **Buchungsverlauf** der Person.

!!! note "Keine Selbstaussperrung"
    Deinen eigenen Admin-Status kannst du nicht ändern, und du kannst dich
    nicht selbst deaktivieren — auch nicht auf Umwegen über eine Gruppe.

## Zugriffsgruppen

Zugriffsgruppen bündeln Personen und geben ihnen Rechte. Eine Gruppe kann
drei Dinge gewähren:

1. **Zugriff auf Pools:** Ein Pool ohne Zugriffsgruppe ist für alle
   Angemeldeten offen. Sobald ein Pool in mindestens einer Gruppe steht,
   können ihn nur noch Mitglieder dieser Gruppen sehen und buchen — sowie
   seine Verleiher und alle Admins.
2. **Verleiher für Pools** (unter **Erweiterte Einstellungen**): Alle
   Mitglieder arbeiten an der Verleihtheke dieser Pools.
3. **Administrator** (ebenfalls unter Erweiterte Einstellungen): Alle
   Mitglieder sind Admins.

![Liste der Zugriffsgruppen: Administratoren (System, Recht Administrator, Mitglied Sam Admin), Lehrende (Pool Makerspace, Claim-Regel eduPersonAffiliation ∈ {faculty, employee}, Mitglied Alex Beispiel) und die Systemgruppen Verleiher Makerspace, Verleiher Medienlabor und Verleiher Podcast-Studio mit Kim Verleih](../bilder/admin-zugriffsgruppen.png)

### Mitglieder: manuell oder per Claim-Regel

Mitglieder fügst du einzeln hinzu (**Mitglied hinzufügen**) — oder
automatisch über eine **Claim-Regel**. Ein Login-Claim ist eine Angabe, die
das Single Sign-on bei der Anmeldung mitschickt, etwa Abteilung,
Studiengang oder Statusgruppe.

- **Claim-Schlüssel:** z. B. `eduPersonAffiliation`, `groups` oder
  `department`.
- **Passende Werte (kommagetrennt):** z. B. `faculty, employee`.

Wer bei der Anmeldung einen dieser Werte im Claim hat, ist automatisch
Mitglied, zusätzlich zu den manuell eingetragenen. Im Beispiel oben dürfen
so alle Lehrenden und Beschäftigten den Makerspace buchen. Unter **Alle
anzeigen** siehst du alle Mitglieder samt Herkunft: **manuell**, **per
Regel** oder **Systemrecht**.

!!! warning "Adminrechte nie per Regel"
    Eine Gruppe mit Claim-Regel kann keine Administratorrechte geben.
    Adminrechte bekommt nur, wer manuell eingetragen ist.

### Systemgruppen

Zwei Arten von Gruppen legt Ausleihbar selbst an. Sie tragen das Etikett
**System** und lassen sich nicht löschen; Name, Regel und Rechte verwaltet
Ausleihbar, bearbeiten kannst du nur Mitglieder, Beschreibung und Pools:

- **Administratoren** — wer hier Mitglied ist, ist Admin.
- **Verleiher ‹Pool›** — je Pool eine Gruppe, angelegt und umbenannt mit dem
  Pool. Ihre Mitglieder sind das Verleihteam; du pflegst sie auch im
  [Pool-Formular](katalog.md#pools) unter „Verleiher“.

## Strike-Regeln

Hier legst du fest, wie lange ein Strike zählt und ab wann Strikes sperren.
Vergeben werden Strikes an der Verleihtheke
([Strikes vergeben](buchungen.md#strikes-vergeben)).

- **Ein Strike zählt für (Tage):** Danach zählt er nicht mehr zur Sperrung.
- **Eskalation:** Stufen der Form „Von *n* Strikes: sperren für *x* Tage“
  oder „dauerhaft“, z. B. ab 3 aktiven Strikes 30 Tage, ab 5 dauerhaft.
  Mit **+ Stufe hinzufügen** kommen weitere dazu. Ohne Stufen sperren
  Strikes nie automatisch.
- **Regeln speichern.**

Erreicht jemand eine Stufe, sperrt Ausleihbar das Konto automatisch für
neue Buchungen. Was Gesperrte sehen, steht in
[Strikes und Sperren](../anleitung/strikes.md).

## Datenaufbewahrung

Ausleihbar kann Konten automatisch **anonymisieren**, die lange nicht
genutzt wurden und keine offenen Ausleihen mehr haben (DSGVO).

- **Automatische Anonymisierung aktivieren** — an oder aus (ohne
  Einschalten wird nichts anonymisiert).
- **Nach so vielen Jahren Inaktivität anonymisieren** — der Zeitraum.
  Darunter siehst du, wie viele Konten mit dieser Einstellung jetzt
  anonymisiert würden.

Dabei werden alle personenbezogenen Daten entfernt; die Buchungs- und
Gegenstandshistorie bleibt unter dem Platzhalter „Gelöschter Nutzer“
erhalten. Admin-Konten sind nie betroffen.
Die Anonymisierung läuft als geplanter Job der Installation und **lässt
sich nicht rückgängig machen**.

!!! tip "Datenschutzerklärung"
    Ändert ihr die Aufbewahrung, prüft auch eure Datenschutzseite
    ([Seiten](einstellungen.md#seiten)).
