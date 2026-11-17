# 0016. Buchungszyklen und Vorab-Kontingent im Desksharing

- **Status:** Accepted
- **Date:** 2026-11-17

## Context
Desksharing ist nur fair, wenn niemand Arbeitsplätze oder Besprechungsräume
für ein ganzes Jahr sperren kann. Gleichzeitig muss, wer einen Sprint oder
Workshop Monate vorher plant, früh buchen können, ohne sich merken zu müssen,
wann „das Quartal aufgeht“. Bisher gab es nur Serien mit hartem
3-Monats-Deckel; Tage ließen sich einzeln, aber nicht gebündelt buchen, und
eine Freigabeanfrage endete immer in einer manuellen Nachbuchung.

## Decision
- **Zyklen je Abteilung** (`DeskSettings`): `cycle_months` (1, 2, 3, 4, 6 oder
  12; Standard 3), ausgerichtet am 1. Januar, also standardmäßig Quartale.
  `transition_weeks` (Standard 4; muss kürzer als ein Zyklus sein) öffnet
  ab „Beginn des nächsten Zyklus minus Übergang“ auch den nächsten Zyklus.
- **Offenes Fenster:** heute bis Ende des laufenden Zyklus, im Übergang bis
  Ende des nächsten. Darin gibt es keine Mengenbegrenzung.
- **Vorab-Kontingent** jenseits des Fensters bis `advance_until`
  (`advance_months`, Standard 12, mindestens `cycle_months`, zusätzlich
  begrenzt durch `max_booking_months` des Bereichs): je Inhaber/in und
  Abteilung höchstens `advance_days` verschiedene Tage (Standard 15) und
  `advance_places` Plätze pro Tag (Standard 10), Arbeitsplätze und
  Besprechungsräume zusammen. Gezählt werden künftige aktive Buchungen und
  offene Freigabeanfragen mit Wunschzeiten. Bestehende Buchungen jenseits des
  Fensters (z. B. alte Serien) bleiben unangetastet, zählen aber mit; wer
  darüber liegt, kann dort erst wieder buchen, wenn er darunter fällt.
- **Eine Stelle, alle Wege:** die Prüfung sitzt in der Buchungs-Engine unter
  einer Sperre je Inhaber/in; Einzel-, Mehrtages-, Serien- und
  Schnellbuchung laufen darüber, tageweises Buchen umgeht das Kontingent
  nicht. Verschiebungen, Tausch und Systemumbuchungen (Defekt, entzogenes
  Recht) sind ausgenommen.
- **Für andere buchen:** Assistenz und Abteilungsadmins erhalten bei
  Überschreitung von Fenster oder Kontingent eine Warnung statt einer
  Ablehnung. Der Horizont (`advance_until`) wird nie aufgehoben.
- **Mehrtagesbuchung** (`POST /api/desks/reservations/days/`): Tage × Plätze,
  alles oder nichts; geschlossene Tage werden abgelehnt, nicht übersprungen.
  Belegte Tage: `on_taken=fail` oder `request`. Anfragbar ist ein Termin nur,
  wenn genau eine fremde Buchung ihn blockiert; feste Plätze anderer, eigene
  Überschneidungen und mehrere Blockierer gelten als nicht verfügbar.
- **Freigabeanfragen buchen automatisch:** sie tragen `wanted_period`, `batch`
  und `result`. Bei Annahme wird die ganze Buchung des Tages der Halterin bzw.
  des Halters übergeben und die Wunschzeiten der anfragenden Person atomar
  gebucht. Scheitert das (zwischenzeitlich belegt, Kontingent), ändert sich
  nichts, die Anfrage läuft ab und die anfragende Person wird benachrichtigt.
  Halter/innen beantworten gebündelt je Anfrager/in („alle annehmen/
  ablehnen“), Anfragende können zurückziehen; Anfragen verfallen mit
  Beginn der Wunschzeit.
- **Serien:** kein 3-Monats-Deckel mehr; eine Serie darf nicht über das offene
  Fenster hinausreichen (für andere gebucht: Warnung). Verlängern geht bis
  zum Ende des aktuell offenen Fensters, sobald dieses über das Serienende
  hinausgewandert ist; die Erinnerungen (28/7 Tage) warten, bis Verlängern
  möglich ist. Serien können belegte Termine anfragen (`on_taken=request`);
  angefragte Termine erscheinen auf der Serienseite als „angefragt“ und lassen
  sich zwischenzeitlich nicht anderweitig auflösen.

## Consequences
Fairness folgt aus dem Fenster und dem kleinen Kontingent, nicht aus
Verwaltung von Hand; Planung im Voraus bleibt für Sprints möglich. Die
Regeln stehen an einer Stelle und sind daher leicht prüfbar, die Sperre je
Inhaber/in kostet etwas Nebenläufigkeit bei Massenbuchungen. Altbestand
braucht keine Datenmigration, kann aber das Kontingent der Betroffenen
vorübergehend aufbrauchen.

**Datenschutz:** Freigabeanfragen speichern jetzt die Wunschzeiten und
verknüpfen die daraus entstandene Buchung. Aufbewahrung unverändert: sie
werden mit den beendeten Buchungen gelöscht. Die Datenschutzseite
(`catalog.Page`, Slug `privacy`) und `docs/desksharing-personalrat.md` sind
entsprechend zu prüfen.

## Alternatives considered
- **Frontend bucht Tag für Tag:** nicht atomar, das Kontingent wäre leicht zu
  umgehen, Teilfehler unübersichtlich. Gewählt: ein Backend-Aufruf.
- **Belegte Termine alles-oder-nichts:** zwingt zu Neuversuchen. Gewählt:
  freie Termine sofort, für belegte wird um Freigabe gebeten und bei
  Annahme automatisch gebucht.
- **Teilfreigabe nur der überlappenden Stunden:** schwer zu erklären und
  erzeugt Restfragmente. Gewählt: ganze Buchung des Tages übergeben.
- **Mengenlimit auch im offenen Fenster:** nicht nötig, das Fenster begrenzt
  bereits die Reichweite.
- **Feste Kalenderquartale ohne Konfiguration:** Hochschulen planen nach
  Semestern oder Monaten; daher `cycle_months`.
