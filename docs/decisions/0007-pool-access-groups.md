# 0007. Pool-Berechtigung über Access Groups

- **Status:** Accepted (implemented)
- **Date:** 2026-06-04

## Context
Konzept §1.5/§3.4 verlangt, pro Ressourcenpool einschränken zu können, *wer ihn
sieht und nutzt* — über **OIDC/Shibboleth-Claims** (z. B. Fachbereich)
**und/oder eine explizite Allowlist**. Welche Claims der Uni-IdP tatsächlich
liefert, ist laut Auth-ADR (0004) noch unverifiziert, eine claim-only-Lösung
wäre also heute nicht voll funktionsfähig. Gleichzeitig soll der bestehende
offene Shop nicht plötzlich leer sein.

## Decision
- Ein Model **`accounts.AccessGroup`** mit:
  - **manuellen Mitgliedern** (`members`, M2M auf User, von Admins gepflegt),
  - **Claim-Matching** (`claim_key` + `claim_values`): wer im OIDC-Claim einen
    der Werte hat, ist automatisch Mitglied. Dafür wird beim Login ein Snapshot
    der Claims in `User.claims` (JSON) abgelegt.
  - **`pools`** (M2M auf `catalog.ResourcePool`): die Pools, die die Gruppe
    freischaltet.
- **Default offen:** Ein Pool *ohne* zugeordnete Gruppe ist für alle (auch
  anonyme) sichtbar und für angemeldete Personen buchbar. Sobald ein Pool in
  mindestens einer Gruppe steht, ist er nur noch für Mitglieder dieser Gruppen
  zugänglich — plus die **Verleihenden** dieses Pools und **Admins**.
- Durchsetzung an einer Stelle: `accounts.eligibility.eligible_pool_ids(user)`
  und `visible_products(qs, user)`. Der Katalog (Produktliste/-detail/-suche,
  Sparten-/Kategorie-Produkte, „Verfügbar in"-Pools) filtert darüber; die
  Verfügbarkeits- und Warenkorb-Services bekommen die erlaubten `pool_ids`
  durchgereicht, sodass Zählungen und Buchung nur nutzbare Pools berücksichtigen.

## Consequences
- Voll funktionsfähig ohne IdP-Abhängigkeit (manuelle Gruppen); Claim-Matching
  ist vorbereitet und greift, sobald die Claims feststehen — ohne Code-Änderung.
- Eine einzige Berechtigungslogik (`eligibility.py`) ist Quelle der Wahrheit für
  Sichtbarkeit *und* Buchbarkeit; Tests decken offen/Mitglied/claim/Verleihende/
  Admin sowie 404 für nicht Berechtigte ab.
- Die verschachtelte Produktfilterung pro Kategorie kostet zusätzliche Queries
  (akzeptabel für die aktuelle Größe; bei Bedarf später per Prefetch/Annotation
  optimierbar).
- `User.claims` speichert einen Claim-Snapshot — bewusst nur Userinfo-Claims,
  keine Tokens.

## Alternatives considered
- **Nur Claims (keine manuellen Gruppen):** verworfen — Claims des Uni-IdP noch
  unverifiziert, wäre heute nicht nutzbar.
- **Django-`auth.Group` wiederverwenden:** verworfen — kein Platz für
  Claim-Regeln und Pool-Zuordnung; eigenes Model ist klarer.
- **Default geschlossen:** verworfen (bewusste Produktentscheidung) — würde jeden
  Pool ohne explizite Freigabe aus dem Shop entfernen; offen-als-Default bewahrt
  das heutige Verhalten und schränkt nur dort ein, wo es gewollt ist.
