# 0010. Produkttypen ersetzen Kategorien

- **Status:** Accepted
- **Date:** 2026-10-01

## Context
Der Katalog hatte drei Ebenen: Sparte → Kategorie → Produkt. Daneben gab es den
Produkttyp (`ProductType`), der die dynamischen Eigenschaften eines Produkts
festlegt. Kategorie und Produkttyp liefen parallel: Jedes Produkt hing an genau
einem Produkttyp, aber an beliebig vielen Kategorien, und beide Strukturen
bildeten in der Praxis fast dieselbe Gruppierung ab („Videokameras",
„3D-Drucker"). Das bedeutete doppelte Pflege (Produkt in Art *und* Kategorie
einordnen, zwei Verwaltungsseiten, zwei Reihenfolgen) und uneinheitliche
Anzeige: Dasselbe Produkt konnte im Shop in mehreren Gruppen erscheinen.
Zugleich (Issue #19) sollten Produkte innerhalb einer Gruppe nach Ausleihart
(tagesweise vor stundenweise) sortiert werden und die Produktkarte die Ausleihart
nur als Symbol zeigen.

## Decision
- **Produkttypen sind die mittlere Ebene:** Sparte → Produkttyp → Produkt. Die
  Kategorie (`Category`) entfällt vollständig. `ProductType` bekommt `image`,
  `position` (manuelle Reihenfolge) und `product_order` (Reihenfolge der
  Produkte); `Section.categories`/`category_order` werden zu
  `Section.product_types`/`product_type_order`. Ein Produkttyp kann in mehreren
  Sparten liegen.
- **Automatische, nicht umkehrbare Migration** (`catalog` 0048–0050): Jede
  Sparte erhält die Produkttypen der Produkte ihrer bisherigen Kategorien, in
  Kategorie-Reihenfolge. Hat eine Kategorie nur einen Produkttyp, übernimmt dieser
  Bild, Beschreibung und Produktreihenfolge der Kategorie, soweit er selbst
  keine hat. Die Migration gibt eine Zusammenfassung aus und löscht danach die
  Kategorien (auch die im Papierkorb). Rückwärts-Migration ist bewusst
  ausgeschlossen (`reverse_code=None`); vor dem Update ist ein ZIP-Export
  anzulegen (`docs/INSTALL.md`, §7.3).
- **Die Ableitungsregeln liegen in `catalog.structure.derive_section_types`**
  und werden auch vom ZIP-Import für alte Archive benutzt.
- **Ausleihart-Gruppierung (#19):** Innerhalb jeder Produkttyp-Gruppe stehen
  tagesweise Produkte vor stundenweisen (stabil), mit Zwischenüberschrift nur
  wenn beide vorkommen. Produktkarten zeigen die Ausleihart nur als Symbol
  (Kalender/Uhr, mit Tooltip und Screenreader-Text); die Produktseite behält
  Text und Symbol.

## Consequences
- Jedes Produkt erscheint im Shop in genau **einer** Gruppe je Sparte; die
  Pflege ist einfacher (eine Zuordnung, eine Verwaltungsseite, eine Reihenfolge).
- Mehrfachzuordnung eines Produkts zu thematischen Gruppen ist nicht mehr
  möglich; dafür bleiben Sets (`ProductSet`).
- Alte ZIP-Archive mit `categories` lassen sich weiter importieren; sie werden
  nach denselben Regeln umgewandelt (Zusammenfassung unter `converted`).
  Neue Archive enthalten keine Kategorien mehr.
- Bildateien unter `media/categories/` bleiben liegen; ein Teil ist nun von
  Produkttypen referenziert, der Rest ungenutzt.
- Das Update ist ohne Backup nicht rückgängig zu machen; der Betrieb muss den
  Hinweis in `docs/INSTALL.md` beachten.
- Die Ausleihart-Sortierung und das Symbol machen die Listen ruhiger und
  sparen Platz auf den Karten.

## Alternatives considered
- **Nur Sparte → Produkt (ohne mittlere Ebene):** einfachste Struktur, aber
  lange, unstrukturierte Produktlisten je Sparte und Verlust der Gruppierung und
  Bilder; verworfen.
- **Sparten abschaffen, nur Produkttypen:** würde die Startseiten-Kacheln und
  die Pool-/Zugriffslogik rund um Sparten aufbrechen und die Navigation
  flacher machen; verworfen, Sparten bleiben als oberste Ebene.
- **Manuelle Neuzuordnung statt automatischer Migration:** vermeidet falsche
  Ableitungen, wäre aber für bestehende Installationen aufwendig und
  fehleranfällig; verworfen zugunsten der automatischen Ableitung mit
  nachträglicher manueller Feinarbeit.
