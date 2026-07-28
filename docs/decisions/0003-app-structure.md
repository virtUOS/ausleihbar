# 0003. App-Struktur (Django) — Shop/Lending als Herzstück

- **Status:** Accepted (implemented)
- **Date:** 2026-06-01

## Context
Das Domänenmodell ist groß (Katalog, Ressourcen, Buchung, Accounts, Tenancy).
Eine einzige `core`-App würde schnell zum Monolithen. **Leitsatz:** Der
**Shop/Lending-Pfad ist das Herzstück** — er muss exzellent bedienbar sein und
ist der erste Berührungspunkt aller Nutzenden. Die Struktur muss diesen Pfad
bevorzugen und darf ihn nicht hinter Verwaltungs-/Admin-Belangen vergraben.

## Decision
`core` wird in fokussierte Apps aufgeteilt:

- **`accounts`** — User, Rollen, `PoolMembership`, OIDC, Verifizierung,
  später Strikes.
- **`catalog`** — Stammdaten: `ProductType`, `Product`, `Category`,
  **`Section`** (vormals `Department`, entspricht „Sparte"), `ProductSet`,
  `ResourcePool`, `Resource`.
- **`lending`** — **das Herzstück**: Verfügbarkeit, Warenkorb, Buchung/
  Reservierung, Ausgabe/Rückgabe, Blockzeiten (Engine in ADR-0006).
- **`tenancy`** — Tenant-Model + Scoping; im MVP minimal (ADR-0005).
- **`common`** — geteilte Basisklassen/Utilities (z. B. Timestamp-Mixin).

Architektur-Prinzipien für das Herzstück:
- Die **Ausleihenden-API** (Katalog-Browsing, Verfügbarkeit, Buchung) ist
  first-class: klar geschnitten, schnell, von Admin-/Verwaltungslogik entkoppelt.
- Das Frontend ist **mobile-first**; der Shop ist die Default-Landing.
- Verwaltung/Administration sind eigene Module/Routen, die den Shop-Pfad nicht
  verkomplizieren.

Umbenennung **`Department` → `Section`** (Konsistenz mit „Sparte") erfolgt im
Zuge dieser Umstrukturierung.

## Consequences
- Klare Grenzen, bessere Testbarkeit, der Shop bleibt schlank und schnell
  weiterentwickelbar.
- Bestehende `core`-Modelle wandern nach `catalog`/`accounts`. Da wegen ADR-0002
  ohnehin die Dev-DB neu aufgesetzt wird, ist **jetzt** der richtige Zeitpunkt —
  es wird nur einmal zurückgesetzt und frisch migriert.
- Importpfade ändern sich (`core.models` → `catalog.models` etc.).

## Alternatives considered
- **Eine `core`-App behalten:** verworfen — wird zum Monolithen, der den
  kritischen Shop-Pfad mit allem anderen vermischt.
- **Microservices:** für den Umfang/Open-Source-Anspruch deutlich überdimensioniert.
