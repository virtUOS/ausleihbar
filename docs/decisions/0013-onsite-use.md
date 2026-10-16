# 0013. Nutzung vor Ort statt Ausleihe

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Issue #116: Manche Gegenstände (Podcast-Raum, 3D-Drucker, Lasercutter) werden
nicht ausgeliehen, sondern im gebuchten Zeitraum vor Ort im Pool genutzt. Die
Buchungslogik (Verfügbarkeit, Öffnungszeiten, Sperrtage, Dauern, Vorlaufzeit,
Warenkorb, Sets) soll identisch bleiben; es unterscheiden sich Wortwahl und
die Frage, ob die Theke den Gegenstand überhaupt aushändigt.

## Decision
- **Am Produkt, nicht am Produkttyp:** `Product.use_type` (`loan` | `onsite`,
  Standard `loan`) und `Product.requires_handout` (Standard `true`, nur für
  `onsite` relevant; ein `loan`-Produkt wird immer ausgehändigt). Produkttypen
  bleiben reine Attributvorlagen (ADR-0011); kein Override je Gegenstand.
  „Selbstbedienung" (`Product.is_self_service`) = vor Ort und ohne Ausgabe.
- **Buchungslogik unverändert.** Selbstbedienungs-Positionen werden normal
  gebucht, aber nie ausgehändigt (`hand_out_items` und Walk-in „jetzt
  ausgeben" überspringen sie). Die Thekenbuttons „Aushändigen / Zurücknehmen"
  bleiben; ein Tag „Vor Ort" markiert die Positionen.
- **Automatischer Abschluss:** `expire_uncollected_bookings` führt zuerst die
  No-Show-Stornierung aus, danach `complete_self_service_items`. Beendete
  Selbstbedienungs-Positionen erhalten `handed_out_at` = Periodenbeginn,
  `returned_at` = Periodenende und werden inaktiv (Status der Buchung neu
  berechnet). Offene Perioden und unbestätigte (PENDING) Buchungen bleiben
  unberührt.
- **Gemischte Warenkörbe sind erlaubt;** Beschriftungen gelten je Position.
  In gemischten Buchungen werden nie abgeholte Thekenpositionen verworfen und
  Selbstbedienungs-Positionen abgeschlossen, die Buchung endet als
  `RETURNED`. Jede genutzte, abgeschlossene Position (zurückgegebene Ausleihe
  oder abgeschlossene Selbstbedienung) verhindert eine vollständige
  No-Show-Stornierung. `_sync_status` ignoriert inaktive, nie ausgehändigte
  (also stornierte) Positionen.
- **Wortlaut:** Mails und ICS wechseln auf „Nutzung vor Ort", sobald *alle*
  Positionen vor Ort sind; in gemischten Buchungen wird jede Vor-Ort-Position
  einzeln beschriftet.
- **Stornierung:** Ausleihende dürfen nur bis zum Beginn einer
  Selbstbedienungs-Position stornieren; Verleihende unverändert.
- **Tagesübersicht:** neuer Abschnitt „Vor-Ort-Nutzungen heute"
  (`onsite`-Bucket, schreibgeschützt); Selbstbedienungs-Positionen erzeugen
  keine Abhol-/Rückgabe-/Überfällig-Einträge.

## Consequences
- **Statistik:** Abgeschlossene Selbstbedienungs-Positionen zählen als
  Ausleihen (Dauer = gebuchter Zeitraum, keine Verzögerung).
- **Keine Überfälligkeits- und No-Show-Erkennung** für Selbstbedienung: keine
  Überfälligkeits-Erinnerungen, nicht erschienene Nutzende werden nicht
  erfasst (die Zeit gilt als genutzt).
- Bestehende Produkte bleiben unverändert (Migration mit Standardwerten).
- Export/Import (ZIP) trägt beide Felder; alte Archive behalten die Standards.
- Keine neuen personenbezogenen Daten.

## Alternatives considered
- **Einstellung am Produkttyp:** widerspricht ADR-0011 (reine Attributvorlage)
  und vermischt Navigation/Verhalten.
- **Eigene Buchungsart/Status „Nutzung":** würde Buchungs-Engine, Kalender und
  Statistik verdoppeln; der Unterschied ist nur Wortlaut und Ausgabe.
- **Selbstbedienung nicht automatisch abschließen:** Buchungen blieben ewig
  „bestätigt" und würden als No-Show storniert oder überfällig gemeldet.
- **Warenkorb nach Nutzungsart trennen:** unnötige Reibung; Positionsbeschriftung
  genügt.
