# 0005. Multi-Tenancy — Single-Tenant, aber tenant-ready

- **Status:** Proposed
- **Date:** 2026-06-01

## Context
Das System soll später mehrere Mandanten unterstützen: unter vordefinierten URLs
werden jeweils nur ausgewählte Ressourcenpools angezeigt. Für das MVP wurde
**ein Mandant** festgelegt, die Architektur soll aber einen späteren Ausbau ohne
großen Umbau erlauben. Die genaue Tenant-Grenze (reiner Pool-Filter vs. echte
Isolation) ist bewusst auf viel später vertagt.

## Decision
- **Shared Database, Shared Schema** mit einem optionalen `tenancy.Tenant`-Model.
- Tenant-Scoping hängt primär am **`ResourcePool`** (ein Pool gehört zu einem
  Tenant); alle anderen Entitäten sind über ihren Pool bzw. Katalog scopebar.
  Die `tenant`-Relation wird so modelliert, dass sie additiv schärfbar ist.
- Im **MVP** existiert ein impliziter Default-Tenant; Queries werden **noch nicht**
  nach Tenant gefiltert, und es gibt noch kein URL-/Host-Routing.
- Tenant-Grenze (Konzept-Review C6) = ein Tenant ist die **Menge der unter einer
  URL angezeigten Pools**, keine harte DB-Isolation. Durchsetzung später.

## Consequences
- Minimaler MVP-Overhead, klarer späterer Pfad.
- Beim Aktivieren echter Tenancy sind Query-Filter, URL-/Host-Routing und
  Sichtbarkeitsregeln nachzurüsten — durch das Vorsehen der Relation aber additiv.
- Keine Tenant-übergreifende Daten-Vermischung „by accident", weil Scoping am Pool
  klar verankert ist.

## Alternatives considered
- **Schema-per-Tenant (z. B. `django-tenants`):** verworfen — erhöht Betriebs-
  und Installationskomplexität, steht dem Open-Source-Ziel „einfach installierbar"
  entgegen, im MVP nicht nötig.
- **Datenbank-pro-Tenant:** verworfen — höchster Betriebsaufwand.
