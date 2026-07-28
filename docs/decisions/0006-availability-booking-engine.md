# 0006. Verfügbarkeits- & Buchungs-Engine

- **Status:** Proposed
- **Date:** 2026-06-01

## Context
Dies ist das **technische Herzstück** und trägt direkt die Shop-/Lending-UX.
Anforderungen: Verfügbarkeit über Zeit berechnen für **tages- und stundenweise**
Buchungen, **poolübergreifend** aggregiert, unter Beachtung von Blockzeiten
(System/Pool/Produkt/Ressource), Reservierungen (unbestätigte Halte) vs.
bestätigten Buchungen, Defekten, Vorlaufzeit, Min/Max-Dauer und — bei
Stundenbuchungen — Öffnungszeiten inkl. Pausen. Sind mehrere Ressourcen möglich,
wird die am längsten zurückgegebene gewählt. Bei Sets zählt die knappste Ressource.
Die Antworten müssen **schnell** sein (Verfügbarkeits-Farbcodes in Listen).

## Decision
- **Datenmodell:** Buchungen als Zeitintervalle je Ressource.
  - `Booking` (Status: `pending`/`confirmed`/`handed_out`/`returned`/`cancelled`),
    gehört zu einer ausleihenden Person.
  - `BookingItem` referenziert genau eine **Ressource** und einen Zeitraum.
- **Zeit-Repräsentation:** PostgreSQL **`tstzrange`** (halb-offene Intervalle),
  Zeitzone `Europe/Berlin`. Doppelbuchungen werden auf DB-Ebene durch eine
  **Exclusion-Constraint** je Ressource für belegende Status verhindert
  (`btree_gist`) — harte Integritätsgarantie.
- **Verfügbarkeit** einer Ressource in einem Intervall = Status `available`
  **und** keine Überlappung mit belegenden Buchungen **und** keine Überlappung
  mit einem Block (sofern der Block die Nutzung ausschließt).
  Produkt-/Kategorie-Verfügbarkeit = Aggregation über die Ressourcen der
  zugänglichen Pools.
- **Reservierung:** legt einen `pending`-Halt mit **Ablaufzeit** an, der die
  Verfügbarkeit sofort reduziert (verhindert Doppel-Reservierung); läuft die
  Bestätigung nicht rechtzeitig, verfällt der Halt.
- **Ressourcenauswahl:** unter den verfügbaren die zuletzt **am längsten
  zurückgegebene**; Verleihende können bei Ausgabe eine andere identische wählen.
- **Stundenbuchung:** Start/Ende müssen in Öffnungszeiten (minus Pausen) liegen.
- **Blockzeiten:** je Block konfigurierbar, ob er die Buchung unterbricht
  (muss vorher enden) oder überbrückbar ist.
- **Performance:** Intervall-Indizes; für die Listen-Farbcodes eine schlanke,
  ggf. gecachte Verfügbarkeits-Abfrage je Produkt/Zeitfenster.

## Consequences
- Komplexere Queries, aber DB-seitige Garantie gegen Überlappungen.
- Sorgfältiges Zeitzonen-/Öffnungszeiten-Handling nötig.
- `btree_gist`-Extension in PostgreSQL aktivieren (per Migration).
- Klare, schnelle Verfügbarkeits-API als Basis für eine erstklassige Shop-UX.

## Alternatives considered
- **Naive Überlappungsprüfung in der App pro Request:** verworfen — fehleranfällig
  bei Nebenläufigkeit, schlechter skalierbar; keine DB-Garantie.
- **Externe Scheduling-Bibliothek:** verworfen — passt nicht zum Ressourcen-/
  Intervallmodell, unnötige Abhängigkeit.
