# Konsistenz-Review des Konzepts

Befund der Durchsicht von `docs/concept.md` (Original-Fassung, Commit `ec89952`).
Ziel: uneinheitliche Begriffe/Rollen, Redundanzen und Widersprüche sichtbar
machen und eine **kanonische** Sprachregelung vorschlagen. Die neu
strukturierte Fassung in `docs/concept.md` wendet diese Regelungen bereits an;
mit ⚠️ markierte Punkte sind **Annahmen, die du bestätigen solltest**, weil sie
das Datenmodell beeinflussen.

## 1. Begriffsvereinheitlichung (kanonische Terme)

| Uneinheitlich verwendet | Fundstellen | Kanonisch |
|---|---|---|
| Set / **Paket** | Set: Z. 21, 183, 190, 233 ff.; Paket: Z. 82 | **Set** |
| Verleihende / **Verleiher** | Verleiher: Z. 123 | **Verleihende** |
| Admin / **Administrator(en)** | Administratoren: Z. 123 | **Admin** |
| Ressource / **Gerät** | Gerät: Z. 84, 123, 125 | **Ressource** ("Gerät" nur als umgangssprachliches Beispiel) |
| Produktseite / Produkt(-)Detailseite | Z. 151 vs. 155/189 | **Produkt-Detailseite** |
| Bestellseite / **Bestellungsseite** | Z. 168 vs. 170 | **Buchungsseite** |
| ID / Inventarnummer / **Inventarisierungscode** | Z. 43, 53, 230, 248 | **Inventarnummer** (System-ID + QR-Code separat) |

**Buchungs-Vokabular vereinheitlicht** (war vermischt: Bestellung/Buchung/
Reservierung):
- **Warenkorb** — Sammlung vor dem Absenden.
- **Buchung** — die abgesendete Anfrage. Status **unbestätigt** → **bestätigt**.
- **Reservierung** = Synonym für die *unbestätigte* Buchung.

## 2. Rollen

Die Rollen sind inhaltlich klar, aber sprachlich uneinheitlich (s. o.). Festgelegt:
**Ausleihende**, **Verleihende**, **Admin**. Hinweis: Verleihende und Admins
können *zugleich* Ausleihende sein (Z. 126, 130) — das ist gewollt und im
Rollenmodell als nicht-exklusive Rollen abzubilden.

## 3. Redundanzen (zusammengeführt)

- **R1 — Ressourcenpool-Attribute doppelt und abweichend.** Grundlagen
  (Z. 27–41) und „Pool erstellen" (Z. 212–220) listen *unterschiedliche*
  Felder: Grundlagen hat Bild/Wegbeschreibung/Beschreibung/Default-Dauer,
  Erstellen hat zusätzlich Telefon/Email. Die Vorlaufzeit (Z. 89) fehlt in
  beiden Listen. → In der neuen Fassung **eine** maßgebliche Attributliste.
- **R2 — Min/max Ausleihdauer 4×.** System-Default (Z. 83), Pool-Default
  (Z. 41), Produkt (Z. 73), Ressource (Z. 56). → Als **eine** Override-Kette
  beschrieben: System → Pool → Produkt → Ressource.
- **R3 — Inventarisierung/QR** mehrfach (Z. 44, 84, 246). → einmal zentral.
- **R4 — Pool-übergreifende Verfügbarkeit** verteilt (Z. 78–79, 113–116,
  181–182). → in einem Abschnitt gebündelt.

## 4. Widersprüche — entschieden

> Leitlinie (vom Auftraggeber bestätigt): Bei Widersprüchen gewinnen die
> **Definitionen im oberen „Grundlagen"-Teil** gegenüber späteren Passagen.

- **C1 — Produkt vs. Ressource beim Anlegen (Z. 227–231).** Im unteren Text
  wurde mehrfach „Produkt" statt „Ressource" für das ausleihbare Exemplar
  verwendet. **Entschieden:** „Produkt anlegen" erzeugt den Katalog-Eintrag
  (aus einer Produktart); das Anlegen einer **Ressource** (physisches Exemplar)
  erzeugt die Inventarnummer + QR-Code und ordnet den Pool zu.
- **C2 — Inventar-Tabelle (Z. 247–248).** **Entschieden:** Die Inventar-
  Übersicht listet **Ressourcen**, nicht Produkte.
- **C3 — Set-Definition.** **Entschieden:** Es gilt die obere Definition — ein
  Set ist eine **Liste von Produkten** (nicht Produktarten mit Stückzahl).
  Entspricht dem bereits umgesetzten Modell (`ProductSet` ↔ M2M `Product`).
- **C4 — Inventarnummer.** **Entschieden:** Beim Anlegen einer Ressource wird
  eine **menschenlesbare, pool-bezogene** Inventarnummer vergeben (laufende
  Nummer innerhalb des Pools, z. B. `DigiLab-001`) — keine UUID, nicht
  systemweit fortlaufend. Beim Anlegen vorgeschlagen, editierbar. (Genaues
  Nummern-Schema pro Pool noch festzulegen.)
- **C5 — Berechtigung über Claims.** **Entschieden (mit Vorbehalt):**
  Eligibility basiert auf **OIDC/Shibboleth-Claims** + optionaler Allowlist.
  ⚠️ Vor der Umsetzung zu verifizieren, **welche Claims der Uni-IdP tatsächlich
  liefert** — OIDC wurde an der Uni Osnabrück erst kürzlich eingeführt. Gehört
  ins Auth-ADR.
- **C6 — Tenant-Grenze.** Bewusst auf **viel später** vertagt (Multi-Tenancy
  ist ohnehin Ausblick); wird erst beim Multi-Tenancy-ADR geklärt.

## 5. Offene Fragen aus dem Konzept (unverändert offen)

- **Kalendereintrag bei mehreren Terminen** (Z. 205) — wie in einen
  `.ics`-Eintrag packen?
- ~~Personalausweisnummer bei Verifizierung (Z. 285)~~ — **entschieden:**
  fällt weg. Verifizierung = einfache **Account-Bestätigung durch Verleihende
  beim Erstkontakt**, ohne Ausweisdaten (s. `concept.md` §6.5).
- **Abgebrochene Sätze** im Original: Z. 82 („… nach der Verfügbarkeit aller
  Produkte") und Z. 171 („Die Seite sieht wie Kalender aus, der auch") — in der
  neuen Fassung sinngemäß ergänzt.

## 6. Tippfehler (in der neuen Fassung korrigiert)

Öffungszeiten→Öffnungszeiten (Z. 31), sowaohl (41), ähnliche (77),
ander Ortsfeste (86), genutz (150), weißt→weist (195), gelösch (191),
Auusleihen (234), ausleidende (268), defelt (278), Ressoucenpool (126, 203),
scollen (145).
