---
title: Zugriffsgruppen
description: An der Verleihtheke selbst pflegen, wer die Gegenstände deiner Pools sehen und buchen darf – die Mitglieder der Zugriffsgruppen deiner Pools.
---

# Zugriffsgruppen

Ist einer deiner Pools auf bestimmte Personen beschränkt, regelt das eine
**Zugriffsgruppe**: Nur ihre Mitglieder sehen und buchen die Gegenstände
des Pools (dazu das Verleihteam und alle Admins). Die Mitglieder dieser
Gruppen pflegst du selbst – unter Verleihtheke → **Buchungen & Ausgabe** →
**Zugriffsgruppen**. Du musst also nicht für jede neue Person die
Administration fragen.

## Welche Gruppen du hier siehst

Hier erscheinen nur **reine Zugriffsgruppen**, die mindestens einen deiner
Pools freischalten. Gruppen, die **Rechte** vergeben – Verleiher für einen
Pool, Administrator – sowie die [Systemgruppen](personen.md#systemgruppen)
fehlen hier bewusst: Rechte vergibt nur die Administration. Neue Gruppen
anlegen, umbenennen oder ihre Pools ändern kann ebenfalls nur die
Administration ([Personen und Zugriff](personen.md#zugriffsgruppen)).

Jede Gruppe steht auf einer eigenen Karte:

- **Name** und Beschreibung der Gruppe.
- Die **Pools** der Gruppe in ihrer Pool-Farbe. Schaltet die Gruppe auch
  einen Pool frei, den du nicht betreust, steht dort **(nicht dein Pool)**.
- Hat die Gruppe eine **Claim-Regel**, eine Zeile wie „Zusätzlich
  automatisch Mitglied: alle mit `eduPersonAffiliation ∈ {faculty}`“.
- Die **Mitglieder** mit Name und E-Mail.

!!! warning "Eine Gruppe, mehrere Pools"
    Schaltet eine Gruppe auch Pools anderer Verleihteams frei, gilt jede
    Änderung dort ebenfalls. Wen du aufnimmst, darf dann auch diese Pools
    sehen und buchen.

## Mitglieder hinzufügen und entfernen

1. Tipp im Feld **Person hinzufügen** mindestens drei Zeichen von Name,
   Benutzername oder E-Mail.
2. Wähle die Person aus der Liste. Sie ist sofort Mitglied und darf die
   Pools der Gruppe sehen und buchen.

Mit dem **✕** neben einem Mitglied nimmst du es nach einer Rückfrage wieder
heraus; die Person kann die Pools der Gruppe dann nicht mehr sehen.

Gefunden werden nur Personen, die sich schon einmal angemeldet haben. Ein
deaktiviertes Konto kannst du nicht aufnehmen.

!!! note "Mitglieder mit „automatisch“"
    Wer über die Claim-Regel Mitglied ist, trägt das Etikett
    **automatisch** und hat kein ✕: Die Mitgliedschaft ergibt sich bei jeder
    Anmeldung neu aus den Angaben des Single Sign-on. Soll so jemand
    keinen Zugriff haben, muss die Administration die Regel ändern.

## Keine Gruppe für deine Pools?

Dann steht dort „Für deine Pools gibt es keine Zugriffsgruppe.“ Deine Pools
sind in dem Fall offen für alle Angemeldeten – oder die Administration legt
eine Gruppe an, wenn der Zugang beschränkt werden soll. Admins finden auf
der Seite einen Link zur Verwaltung der Zugriffsgruppen.

!!! info "Datenschutz"
    Auf dieser Seite siehst du Name und E-Mail aller Mitglieder der
    Zugriffsgruppen deiner Pools – auch derer, die nur über die Claim-Regel
    dazugehören. Nutze die Angaben nur für den Verleih.
