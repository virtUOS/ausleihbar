# 0008. Eine Reservierung pro Pool

- **Status:** Accepted (implemented)
- **Date:** 2026-09-26

## Context
Vor dieser Änderung konnte eine einzelne `Booking` Items aus mehreren
`ResourcePool`s enthalten (ein Warenkorb, der z. B. eine Kamera aus dem
DigiLab und ein Mikrofon aus einem anderen Pool bündelt). Verleihende wurden
dabei über ihre Items gescoped: *„verwaltet ein Item dieser Buchung einen
Pool, den ich betreue?“* Das öffnete zwei Probleme (Issue #26):

- Ein Verleihender, der nur einen der beteiligten Pools betreut, konnte auf
  der Buchung Aktionen sehen und (je nach Endpunkt) auch auslösen, die
  eigentlich Items eines **fremden** Pools betrafen — Statuswechsel,
  Bestätigung, Strafpunkte — weil die Berechtigungsprüfung nur „irgendein
  Item in einem meiner Pools“ verlangte, nicht „alle Items“.
- Die Verleihschalter-Ansicht (QR-Scan, „zu bestätigen“-Liste) musste pro
  Buchung mehrere Pools gleichzeitig darstellen, obwohl jeder Pool nur seinen
  eigenen Teil bearbeiten darf — unübersichtlich und fehleranfällig.

Der volle Entwurf steht in
`docs/superpowers/specs/2026-09-24-per-pool-confirmation-design.md`.

## Decision
- **Eine Reservierung gehört genau einem Pool.** `lending.Booking` bekommt ein
  Pflichtfeld `resource_pool` (nur ein *Warenkorb* darf es noch leer lassen,
  solange nicht klar ist, aus welchem Pool am Ende bestellt wird).
- **Aufteilen beim Absenden:** Enthält der Warenkorb Items aus mehreren Pools,
  wird er beim Submit (`lending.services.submit_cart`) in mehrere
  `Booking`-Zeilen aufgeteilt — eine pro Pool, jede mit ihrer eigenen
  Reservierungsnummer. Alle so entstandenen Teile teilen sich eine gemeinsame
  `checkout_id` (UUID), damit sie als *eine Bestellung* erkennbar bleiben
  (z. B. für die Sammel-Bestätigungsmail und die Übersicht der Borger:in).
- **Verleihende werden über `resource_pool` gescoped**, nicht mehr über die
  Items der Buchung: `ManageBookingViewSet.get_queryset()` filtert auf
  `resource_pool__in=<verwaltete Pools>`; dieselbe Regel gilt für die
  Strike-Vergabe über eine Buchung (`accounts.views.ManageStrikeViewSet`,
  M4) und — mit einem Fallback für alte, noch nicht per Code aufgeteilte
  QR-Codes — für den Pickup-Lookup (`ManageBookingViewSet.by_code`/`scan`,
  I2): trifft der gescopte Lookup nicht, aber der Code gehört zu einer
  aufgeteilten Bestellung, wird der zum eigenen Pool gehörende Teil derselben
  Bestellung zurückgegeben statt gar nichts (nie ein fremder Teil).
- **Bestätigungsmails werden pro Bestellung gesammelt**, nicht pro Buchung:
  Ist die ganze Bestellung fertig bestätigt, geht sofort eine kombinierte Mail
  raus; ist nur ein Teil bestätigt, wird die Mail bis zur täglichen
  Versandzeit zurückgehalten und dann klar als Teilbestätigung
  („Teilbestätigung“) verschickt — außer ein bestätigter Teil hat eine
  dringende Abholung vor der nächsten Versandzeit. Umgesetzt in
  `lending.confirmations.dispatch_confirmation_mails` (mit Row-Lock +
  Claim-Update gegen Doppelversand bei gleichzeitigen Aufrufen) und dem
  wiederkehrenden Job `send_confirmation_mails` (Management-Command), der
  fällige, aber noch zurückgehaltene Mails nachträgt.
- **Datenmigration:** `lending/migrations/0014_split_multi_pool_bookings.py`
  (Logik in `lending/splitting.py`) füllt `resource_pool` für Bestandsdaten
  und teilt bestehende Mehr-Pool-Buchungen nach demselben Schema auf wie ein
  Submit — inklusive hochgerechnetem Status je Teil (z. B. „teilweise
  zurückgegeben“ wird pro Pool getrennt betrachtet) und Zeitstempeln, damit
  bereits abgeschlossene Altfälle nicht rückwirkend (erneut) gemailt werden.

## Consequences
- Eine Bestellung über mehrere Pools erzeugt **mehrere Reservierungsnummern**
  (eine je Pool) statt einer einzigen — Shop-UI und Mails müssen das als
  „eine Bestellung, mehrere Reservierungen“ darstellen (siehe
  `Booking.order_parts()`, die Gruppierung im Warenkorb-Absenden-Response und
  die Sammel-/Teilbestätigungsmail).
- Verleihende sehen und bearbeiten nur noch die Teile ihrer eigenen Pools —
  das schließt die oben beschriebene Berechtigungslücke, verlangt aber, dass
  jeder neue Endpunkt konsequent nach `resource_pool` statt nach Items
  scoped (siehe M4-Testfall: Verleihende dürfen nicht über eine Buchung eines
  fremden Pools strafen, selbst wenn eines ihrer Items zufällig in einem
  verwalteten Pool liegt).
- Die Migration 0014 ist **nicht umkehrbar** — sie ordnet Items bestehender
  Buchungen neuen Buchungsobjekten zu (inklusive neuer IDs/Codes für alle
  Teile außer dem ersten); ein Rollback würde die ursprüngliche Gruppierung
  nicht wiederherstellen können. Vor dem Deploy auf Bestandsdaten ist ein
  Datenbank-Backup daher Pflicht.
- Der periodische Job `send_confirmation_mails` ist jetzt **erforderlich**
  (nicht nur „nice to have“) — ohne ihn bleiben Teilbestätigungen, die vor
  der Versandzeit bestätigt wurden, unbegrenzt zurückgehalten. Ein
  einzelner Mailfehler in einer Bestellung darf den Lauf für die übrigen
  Bestellungen nicht abbrechen (I1).
- Mehr bewegte Teile beim Absenden (Aufteilen, `checkout_id`, Race-Schutz per
  `select_for_update` gegen doppeltes Absenden desselben Warenkorbs, M1) —
  etwas höhere Komplexität in `submit_cart`, aber eine einzige Quelle der
  Wahrheit für „wem gehört diese Reservierung“.

## Alternatives considered
- **Bestätigung pro Item innerhalb einer Buchung** (Buchung bleibt
  Mehr-Pool-fähig, aber jedes Item trägt seinen eigenen
  Bestätigt/Gemailt-Status): verworfen — die Berechtigungslücke wäre nur
  verschoben (jeder Endpunkt müsste weiterhin item-genau filtern statt sich
  auf ein einziges Buchungsfeld verlassen zu können), und Reservierungsnummer,
  QR-Code und Verleihschalter-Ansicht sind heute an *eine* Buchung geknüpft,
  nicht an einzelne Items — das hätte weit mehr Oberfläche berührt als das
  Aufteilen beim Submit.
- **Nur die Bestätigungsaktion absichern** (Statuswechsel/Strike-Vergabe
  zusätzlich gegen die Pools der betroffenen Items prüfen, ohne die Buchung
  selbst aufzuteilen): verworfen — behebt zwar die akute
  Berechtigungslücke, lässt aber weiterhin eine Buchung mit Items aus
  mehreren Pools zu, die für QR-Scan, Abholcode und Verleihschalter-Anzeige
  weiterhin mehrdeutig bliebe (welcher Pool „besitzt“ den Abholcode?).
