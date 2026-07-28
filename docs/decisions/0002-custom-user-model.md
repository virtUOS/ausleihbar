# 0002. Eigenes (Custom) User Model

- **Status:** Accepted (implemented)
- **Date:** 2026-06-01

## Context
Das System braucht Rollen (Ausleihende / Verleihende / Admin, nicht exklusiv),
Anbindung an externe Identitäten (OIDC/Keycloak, später Shibboleth), eine
Account-Verifizierung beim Erstkontakt sowie später Strikes/Sperren. Django
empfiehlt **dringend**, ein eigenes User-Model **vor der ersten Migration**
festzulegen — ein späterer Wechsel ist sehr aufwändig. Das initiale Scaffold hat
bereits mit dem Standard-User migriert; es gibt aber **noch keine echten Daten**.

## Decision
- Ein eigenes Model **`accounts.User`** auf Basis von `AbstractUser` einführen
  und `AUTH_USER_MODEL = "accounts.User"` setzen.
- Zusätzliche Felder u. a.: `subject` (OIDC `sub`, eindeutig), `is_self_registered`,
  `verified_at` (Erstkontakt-Bestätigung), Stammdaten aus Claims.
- **Rollenmodell:**
  - *Admin* → globales Flag (`is_staff`/`is_superuser`).
  - *Verleihende* → **pro Pool** über ein Through-Model `PoolMembership`
    (User ↔ ResourcePool, Rolle `manager`); jemand ist „verleihend", wenn er
    mindestens einen Pool verwaltet.
  - *Ausleihende* → Default jeder angemeldeten Person (keine eigene Tabelle nötig).
- Da `AUTH_USER_MODEL` rückwirkend gesetzt wird, wird die **Dev-Datenbank neu
  aufgesetzt** (Volume verwerfen, neu migrieren). Unkritisch, da keine echten Daten.

## Consequences
- Zukunftssicher für OIDC, Rollen, Strikes; saubere Erweiterbarkeit.
- Einmaliger Reset des Dev-DB-Volumes nötig (`docker compose down -v`), danach
  frische Migrationen. Wird zusammen mit der App-Umstrukturierung (ADR-0003)
  erledigt, um nur einmal zurückzusetzen.
- Strikes/Sperren werden als eigenes Model später ergänzt (Ausblick).

## Alternatives considered
- **Standard-User + separates Profile-Model:** verworfen — späteres Erweitern
  des Auth-Kerns bleibt umständlich; OIDC-`sub` gehört an den User.
- **Proxy-Model:** unzureichend, da keine zusätzlichen Felder möglich.
