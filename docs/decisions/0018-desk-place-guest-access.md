# 0018. Zugriffsgruppen am Platz öffnen den Platz auch für Nicht-Mitglieder

- **Status:** Accepted (ändert in ADR-0014 die Bedeutung der Zugriffsgruppen eines Platzes)
- **Date:** 2026-11-19

## Context
Manche Arbeitsplätze teilen sich zwei Institute. Bisher konnten die eigenen
Zugriffsgruppen eines Platzes das Buchen innerhalb seiner Abteilung nur
*einschränken*: Wer buchen wollte, musste zuerst Mitglied der Abteilung sein.
Ein zweites Institut hätte man nur zulassen können, indem man es zur ganzen
Abteilung hinzufügt – damit wären alle Plätze offen gewesen.

## Decision
- Hat ein Platz eigene Zugriffsgruppen, dürfen genau deren Mitglieder und die
  Admins der Abteilung ihn buchen – **ohne** Mitglied der Abteilung zu sein.
  Ohne eigene Gruppe gilt weiter: alle Mitglieder der Abteilung. Die
  Abteilung muss Desksharing eingeschaltet haben.
- Wer so an einen Platz kommt, ohne Mitglied zu sein, ist **Gast** der
  Abteilung (`rights.guest_pool_ids`; `visible_pool_ids` = Mitglied ∪ Gast).
  Gäste sehen die Abteilung in der Auswahl, aber in jeder Ansicht (Übersicht,
  Etagen, Ausstattung, „Jetzt frei“, Buchen, Tage eines Platzes, Plan) nur
  ihre Plätze (`rights.guest_place_ids`).
- Für Gäste gelten Buchungsfenster, Kontingent, Check-in, Freigabe und der
  Verlust von Rechten der Abteilung des Platzes wie für Mitglieder. Wechselt
  der Platz die Abteilung, behält ein Gast seine Buchung, solange er noch in
  einer Gruppe des Platzes ist.
- Gäste sehen keine Raumnachbarn; Assistenzen buchen nicht für Gäste,
  Personensuche, fester Inhaber und Abwesenheiten bleiben bei Mitgliedern.

## Consequences
- Eine Gruppe am Platz bedeutet jetzt „wer darf buchen“, nicht mehr „nur
  diese Mitglieder“. Eine breite Gruppe (z. B. über Claims) öffnet den Platz
  hochschulweit für alle ihre Mitglieder. Da Desksharing noch nirgends
  ausgerollt war, gibt es keine Bestandsdaten mit der alten Bedeutung.
- Gäste sehen an ihren Plätzen dieselben Angaben wie Mitglieder (Name bei
  Arbeitsplätzen außer Opt-out, bei Besprechungsräumen Name und Kommentar).
