# 0021. Systemgruppe „Alle Angemeldeten“: Offenheit wird explizit

- **Status:** Accepted
- **Date:** 2026-11-22
- **Ändert:** ADR-0007 (Regel „Pool ohne Gruppe = offen“), ADR-0020
  (`is_personal` entscheidet nicht mehr über Offenheit)

## Context
Nach ADR-0007 ist ein Pool offen, solange er *keine* Zugriffsgruppe hat. Die
Regel ist unsichtbar: Wer die letzte Gruppe entfernt, öffnet den Pool
stillschweigend. Mit den LTI-Kursgruppen (ADR-0020) kamen Ausnahmen dazu –
Kursgruppen öffnen und schließen nichts, persönliche Pools sind immer
eingeschränkt –, die sich kaum noch erklären lassen. Zugleich sollen im
Desksharing einzelne Räume für alle buchbar werden (z. B. Arbeitsräume für
studentische Arbeitsgruppen), ohne die Zusage an den Personalrat zu brechen,
dass es keine hochschulweite Namensliste gibt.

## Decision
- **Systemgruppe „Alle Angemeldeten“** (`AccessGroup.system_all`, genau eine,
  bei Bedarf angelegt wie „Administratoren“). Jede angemeldete Person ist
  implizit Mitglied (`eligibility.user_group_ids`); Mitglieder werden nicht
  gespeichert. Nicht löschbar; Name, Claim-Regel, Mitglieder, Admin- und
  Verleihrechte gesperrt; nur Beschreibung und Pools bearbeitbar.
- **Ein Pool ist genau dann offen, wenn er diese Gruppe hat.** Offene Pools
  bleiben auch für nicht angemeldete Besucher im Shop sichtbar (wie bisher).
  Ein Pool ohne jede Gruppe ist nur noch für seine Verleihenden und Admins
  zugänglich. Kursgruppen gewähren weiterhin nur zusätzlichen Zugang.
- **Migration:** Jeder heute offene Pool (kein `is_personal`, keine
  gewöhnliche Gruppe) bekommt die Gruppe; das Verhalten bleibt gleich.
- **Default:** Neu angelegte Pools bekommen die Gruppe (Pool-API ohne
  `access_group_ids`, leihs-Import, Demo-Daten); persönliche LTI-Pools nicht –
  ein Admin kann sie aber hinzufügen. `is_personal` steuert nur noch den
  Default.
- **Desksharing:** Die Gruppe am *Pool* öffnet nur den Verleih, nicht die
  Arbeitsplätze, und zählt weder für die Abteilungsmitgliedschaft noch für das
  Einschalten von Desksharing. Für alle buchbar werden Plätze nur über die
  Gruppen von Räumen oder Plätzen (Gastzugang nach ADR-0018/0019); dort ist
  sie nie vorausgewählt. Sie gibt nie Rollen (keine Assistenzgruppe).
- **Datenschutz:** Wer einen Platz nur über „Alle Angemeldeten“ erreicht,
  sieht keine Personendaten anderer (Namen, Kommentare, feste Inhaber), nur
  „belegt“, und stellt keine Tausch- oder Freigabeanfragen. Die Regel lebt in
  `desksharing.privacy`.

## Consequences
- Offenheit ist sichtbar und wählbar; das Entfernen der letzten Gruppe schließt
  einen Pool, statt ihn zu öffnen.
- Eine Regel für alle Pools; die LTI-Sonderfälle in `eligible_pool_ids`
  entfallen.
- Desksharing kann offene Räume anbieten, ohne eine hochschulweite
  Namensliste zu erzeugen.
- Gruppenlisten zeigen die Gruppe ohne Mitgliederliste.

## Alternatives considered
- **Schalter „offen für alle“ an Pool, Raum und Platz:** verworfen – drei
  Felder und eine Sonderregel in jeder Auswahl und Rechteprüfung, also genau
  die versteckte Regel, die entfallen soll.
- **Desksharing frei mit Namen für alle:** verworfen – bräche die Zusage an
  den Personalrat.
- **Gruppe am Pool öffnet auch die Arbeitsplätze:** verworfen – nach der
  Migration wäre das faktisch der Default für jede Abteilung.
