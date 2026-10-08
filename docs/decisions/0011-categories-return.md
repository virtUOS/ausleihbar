# 0011. Kategorien kehren als Shop-Navigation zurück

- **Status:** Accepted (ersetzt den Navigationsteil von ADR-0010)
- **Date:** 2026-10-07

## Context
Mit ADR-0010 wurden Produkttypen zur mittleren Ebene der Shop-Navigation
(Sparte → Produkttyp → Produkt). In der Praxis zeigte sich (Issue #78), dass
ein Produkttyp zwei verschiedene Aufgaben schlecht zugleich erfüllt: Er ist
**Eigenschaftsvorlage** (welche Attribute ein Produkt hat) und sollte zugleich
**thematische Gruppe** im Shop sein. Für die Navigation fehlen dabei
Unterebenen (z. B. „Kameras › Video“) und die Möglichkeit, ein Produkt in
mehreren Gruppen zu zeigen. Produktion hat die Migration aus ADR-0010 bereits
ausgeführt; dort gibt es keine Kategorien mehr.

## Decision
- **Hierarchische Kategorien sind die Shop-Navigation:** Sparte → Kategorie →
  Unterkategorie (beliebig tief) → Produkt. Produkttypen sind wieder reine
  Eigenschaftsvorlagen; ihre Navigationsfelder (`image`, `position`,
  `product_order`, `Section.product_types`/`product_type_order`) entfallen
  mit Migration `catalog` 0056 im selben Release (nicht umkehrbar).
- **Modell `catalog.Category`** (Papierkorb-fähig wie die übrigen
  Katalogmodelle): `name`/`description` (übersetzbar), `image`, `parent`
  (selbstbezogen, `null` = oberste Ebene, `PROTECT`), `position` (Reihenfolge
  unter Geschwistern), `product_order` (Produkt-IDs). `Product.categories`
  (M2M, ein Produkt kann in mehreren Kategorien liegen), `Section.categories`
  (nur oberste Ebene) mit `Section.category_order`.
- **Baumregeln:** Eine Kategorie kann nicht unter sich selbst oder einem ihrer
  Nachfahren liegen; eine Kategorie in einer Sparte muss oberste Ebene bleiben
  (`Category.clean`). Eine Kategorie mit Unterkategorien kann nicht gelöscht
  werden (`parent` ist `PROTECT`; die Verwaltung lehnt das Löschen ab, solange
  Unterkategorien existieren). Endgültiges Löschen aus dem Papierkorb erfolgt
  von den tiefsten Kategorien aufwärts; Wiederherstellen einer Kategorie stellt
  auch ihre gelöschten Vorfahren wieder her.
- **Automatische Vorbelegung** (`catalog` 0052): Jeder aktive Produkttyp, der
  in mindestens einer Sparte liegt, wird zu einer Kategorie der obersten Ebene
  (Name/Beschreibung je Sprache, derselbe Bildpfad ohne Kopie, Position,
  Produktreihenfolge, alle Produkte des Typs — auch solche im Papierkorb:
  sie bleiben dort unsichtbar und behalten nach dem Wiederherstellen ihre
  Kategorie). Die Sparten erhalten diese Kategorien
  in der bisherigen Typ-Reihenfolge. Der Shop sieht direkt nach dem Update
  unverändert aus. Die Migration ist idempotent (vorhandene gleichnamige
  Kategorien der obersten Ebene werden wiederverwendet) und gibt eine
  Zusammenfassung aus.

## Consequences
- Die Navigation kann tiefer gegliedert werden; Kategorieseiten zeigen die
  Produkte der Kategorie samt aller Unterkategorien (ohne Duplikate).
- Ein Produkt kann wieder in mehreren Gruppen erscheinen; die Einordnung
  (Kategorie) ist von der Eigenschaftsvorlage (Produkttyp) getrennt — dafür
  ist bei neuen Produkten wieder beides zu pflegen.
- Die vorbelegten Kategorien referenzieren die Bilder der Produkttypen an
  Ort und Stelle — diese liegen unter `media/product_types/` **oder**, wenn
  Migration 0049 (#20) dem Typ ein altes Kategoriebild gegeben hatte, unter
  `media/categories/`. Keiner der beiden Ordner darf von Hand aufgeräumt
  werden; neue Kategoriebilder landen unter `media/categories/`.
- Das Entfernen der Typ-Navigationsfelder (0056) ist nicht umkehrbar; vor dem
  Update sind Datenbank und Medien zu sichern (`docs/INSTALL.md`, §7.3).
- Die Ausleihart-Gruppierung (#19) aus ADR-0010 bleibt bestehen.

## Alternatives considered
- **Produkttypen hierarchisch machen:** würde Vorlage und Navigation weiter
  vermischen und Mehrfachzuordnung nicht lösen; verworfen.
- **Kategorien leer starten und manuell befüllen:** sauberer Neuanfang, aber
  der Shop wäre nach dem Update leer; verworfen zugunsten der Vorbelegung aus
  den Produkttypen.
- **Löschen mit Unterkategorien kaskadieren oder Kinder hochziehen:**
  kaskadierendes Löschen ist zu folgenreich, Hochziehen überraschend; das
  Ablehnen ist am einfachsten nachvollziehbar.
