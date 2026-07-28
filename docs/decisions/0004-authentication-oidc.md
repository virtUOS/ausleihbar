# 0004. Authentifizierung über OIDC (Keycloak)

- **Status:** Accepted (backend implemented against local Keycloak; SPA login button pending)
- **Date:** 2026-06-01

## Context
Anmeldung erfolgt über **OIDC (Keycloak)**, in Teilen später über **Shibboleth**.
Nutzerdatensätze entstehen **bei der ersten Anmeldung** (Just-in-Time). Eine
Selbstregistrierung ist optional und im MVP zurückgestellt. Pool-Berechtigung
(Eligibility) soll auf **Claims** beruhen — OIDC wurde an der Uni Osnabrück erst
kürzlich eingeführt, der konkrete Claim-Umfang ist noch zu verifizieren.

## Decision
- Bibliothek **`mozilla-django-oidc`** für den OIDC-Authorization-Code-Flow
  gegen Keycloak.
- **JIT-Provisionierung:** Beim ersten Login wird der `accounts.User` aus den
  Claims angelegt; `subject` (`sub`) wird als stabile, eindeutige Kennung gespeichert.
- **Claim-Mapping konfigurierbar** (Settings/Env): welche Claims auf welche
  User-Felder und auf Eligibility-Kriterien abgebildet werden — so lässt sich der
  reale Claim-Umfang nachträglich ohne Codeänderung anpassen. ⚠️ Vor dem
  Scharfschalten der Eligibility den tatsächlichen Claim-Umfang verifizieren.
- **Pluggable Auth-Layer:** so gekapselt, dass Shibboleth später als zusätzlicher
  Backend ergänzt werden kann, ohne den Kern zu ändern.
- **Lokale Entwicklung:** Djangos lokale Authentifizierung als Dev-Fallback
  (Superuser/Login) bleibt aktiv, damit ohne laufenden Keycloak entwickelt und
  getestet werden kann. Ein Keycloak-Container mit importiertem Realm liegt in
  der Compose-Datei.

## Configuration (implementiert)
Alles über Env-Variablen, damit ein Provider-Wechsel **keine** Codeänderung braucht:
- **Endpoints:** entweder explizit, oder via `OIDC_OP_ISSUER` aus dem
  Discovery-Dokument (`/.well-known/openid-configuration`) abgeleitet. Explizite
  Werte haben Vorrang (nötig für den lokalen Browser/Backchannel-Split).
- **Claim-Namen:** `OIDC_CLAIM_USERNAME` / `_EMAIL` / `_FIRST_NAME` / `_LAST_NAME`
  (Defaults = Standard-OIDC-Claims). `sub` ist immer der Subject-Schlüssel.
- **Admin-Festlegung:** Ein lokales **`createsuperuser`**-Konto dient als
  Bootstrap und Break-Glass-Zugang. Zusätzlich mappt `OIDC_ADMIN_GROUP` (über den
  `OIDC_GROUPS_CLAIM`) eine IdP-Gruppe auf Django-Admin: Mitgliedschaft setzt beim
  Login `is_staff`/`is_superuser`, Austritt entzieht sie (Gruppe ist für
  OIDC-Nutzende maßgeblich). *Verleihende* werden in-App über `PoolMembership`
  (ADR-0002) oder analog per Gruppen-Claim vergeben.

## Consequences
- Abhängig von einer Keycloak-Realm-/Client-Konfiguration (Client-ID/Secret,
  Redirect-URIs) — als Env-Variablen geführt.
- Eligibility-Logik ist erst belastbar, wenn die Claims verifiziert sind;
  bis dahin trägt die explizite Allowlist (ADR-Konzept §3.4).
- Sitzungs-/Token-Handling und Logout (inkl. IdP-Logout) sind zu berücksichtigen.

## Alternatives considered
- **django-allauth:** mächtiger, aber schwergewichtiger als nötig für reines OIDC.
- **python-social-auth:** breit, aber mehr Konfigurations-Overhead.
- **Eigene OIDC-Implementierung:** verworfen — sicherheitskritisch, kein Mehrwert.
