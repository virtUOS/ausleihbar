# 0012. Rollen über Gruppen

- **Status:** Accepted (ersetzt den Verleiher-Teil von ADR-0002, erweitert ADR-0007)
- **Date:** 2026-10-13

## Context
ADR-0002 legte fest: Admin über `is_staff`/`is_superuser`, Verleihende über
`PoolMembership` (eine Zeile je Nutzer und Pool), Ausleihende = jeder
angemeldete Nutzer. Mit den Access Groups (ADR-0007) gab es daneben eine
zweite Mitgliedschaftsverwaltung, die über OIDC-Claims automatisch befüllt
werden kann. Issue #80: Verleiher- und Admin-Rechte sollen sich ebenfalls
über Gruppen (auch claim-basiert) vergeben lassen, statt jede Person einzeln
pro Pool einzutragen.

## Decision
- **`accounts.AccessGroup` vergibt Rechte:** `lender_pools` (M2M auf
  `catalog.ResourcePool`; effektive Mitglieder sind Verleihende dieser Pools)
  und `is_admin` (nur **manuelle** Mitglieder sind App-Admins).
- **Claims vergeben nie Admin-Rechte.** Eine Gruppe mit `is_admin` darf keine
  Claim-Regel haben — erzwungen im Code (Serializer-Validierung, Rollenfunktionen
  zählen nur manuelle Mitglieder) und in der Datenbank (`CheckConstraint`).
- **Systemgruppen:** Jeder Pool hat die Gruppe „Verleiher ‹Pool›"
  (`system_pool`, ersetzt `PoolMembership`; Name folgt dem Poolnamen, nicht
  löschbar, Name/Claims/Rechte gesperrt, nur Mitglieder und Zugangs-Pools
  editierbar) sowie genau eine Gruppe „Administratoren" (`system_admin`).
  Pool-Formular (Verleiher-Auswahl, `/api/manage/pools/<id>/lenders/`) und
  Nutzerseite bearbeiten die manuellen Mitglieder der Pool-Systemgruppe.
- **Admin-Quellen:** `is_staff`/`is_superuser` (Nutzer-Schalter und
  `OIDC_ADMIN_GROUP`-Zuordnung beim Login) **oder** manuelles Mitglied einer
  `is_admin`-Gruppe. `is_staff` wird nicht in die Gruppe migriert; die
  Mitgliederansicht der „Administratoren" zeigt die Quelle („manuell" /
  „Systemrecht"). Der Zugang zur Django-Admin-Oberfläche bleibt `is_staff`.
  Der Admin-Schalter im Nutzerformular (`is_admin` bei
  `PATCH /api/manage/users/<id>/`) setzt `is_staff` **und** `is_superuser`
  und bildet nur diese Flags ab (`admin_via_flag`; Admin über Gruppen meldet
  `admin_groups`); ändern dürfen ihn nur Admins, die selbst
  `is_staff`/`is_superuser` haben — reine Gruppen-Admins erhalten 403 und
  vergeben Admin-Rechte über die Gruppe „Administratoren".
- **Zentrale Funktionen** in `backend/accounts/roles.py` (`managed_pool_ids`,
  `is_app_admin`, `is_lender`, `pool_lender_ids`, …), mit Memoisierung je
  Nutzerobjekt; alle früheren Prüfungen über `PoolMembership` bzw.
  `is_staff or is_superuser` laufen darüber.
- **Migrationen:** `accounts` 0007 (Felder), 0008 (Datenmigration: je Pool eine
  Systemgruppe mit den bisherigen Verleihenden als manuellen Mitgliedern,
  Gruppe „Administratoren"), 0009 (entfernt `PoolMembership`).
- **API:** `/api/manage/access-groups/` um die neuen Felder erweitert;
  `GET …/<id>/members/` listet effektive Mitglieder mit Quelle
  (`manual`/`claim`/`system_admin`); `managed_pools` der Nutzer enthält
  `via` (welche Gruppe gewährt den Pool).

## Consequences
- Verleiher-Rechte lassen sich per Claim (z. B. Fachbereich) oder manuell über
  beliebige Gruppen vergeben; die Rechtevergabe hat eine einzige Quelle.
- **Sicherheit:** Verleiher-Rechte über Claims setzen voraus, dass das
  IdP-Attribut, das als `claim_key` dient, **nicht durch Nutzende selbst
  änderbar** ist. Das muss im IdP geprüft werden, bevor eine Gruppe mit
  Verleiher-Rechten eine Claim-Regel erhält. Admin-Rechte sind davon nicht
  betroffen (nie über Claims).
- `review_defects` mailt, wenn ein Pool keine Verleihenden hat, ersatzweise
  an alle App-Admins (inkl. Admins über Gruppen).
- Selbstaussperrung wird verhindert (Prüfungen beim Ändern/Löschen von
  Admin-Gruppen und -Mitgliedschaften des Anfragenden).
- `member_count` zählt nur manuelle Mitglieder; die Mitgliederansicht zeigt
  alle effektiven (Claim-Treffer werden aus dem gespeicherten `User.claims`
  berechnet, also erst nach dem nächsten Login aktuell).
- **Rollback ist verlustbehaftet:** Das Rückwärtsmigrieren von 0009/0008 legt
  `PoolMembership` nur aus den manuellen Mitgliedern der Pool-Systemgruppen
  an. Mitglieder von „Administratoren" und Rechte, die über andere
  (Nicht-System-)Gruppen vergeben wurden, gehen verloren. Vor dem Update ein
  `pg_dump` anlegen.

## Alternatives considered
- **`PoolMembership` behalten und Gruppen nur ergänzen:** zwei Quellen für
  dieselbe Aussage, doppelte Pflege und unklare Rechte-Anzeige.
- **Admin auch über Claim-Gruppen:** ein änderbares oder falsch konfiguriertes
  IdP-Attribut würde Vollzugriff geben; bewusst ausgeschlossen.
- **`is_staff` in die Admin-Gruppe migrieren:** kollidiert mit der
  `OIDC_ADMIN_GROUP`-Zuordnung, die diese Flags beim Login setzt.
