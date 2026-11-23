# 0022. Türschilder: der Server rendert die Bilder

- **Status:** Accepted
- **Date:** 2026-11-23

## Context
Desksharing-Räume erhalten batteriebetriebene E-Ink-Türschilder (Elecrow
CrowPanel ESP32-S3, 2,1" und 5,79"), die zeigen, wer eingecheckt ist und was
frei ist, und an denen man ein- und auschecken oder einen Besprechungsraum
belegen kann (Spec `docs/superpowers/specs/2026-11-19-door-displays-design.md`).
Die Anzeigelogik ist nicht trivial: Platzzustände, Datenschutzregeln
(Opt-out-Namen), „Endzeit nur bei < 5 h", Namenskürzung, tastengesteuerte
Auswahl- und Bestätigungsabläufe. Ein Gerät am Akku soll selten aufwachen und
ein dünner Client bleiben.

## Decision
- **Der Server rendert, das Gerät zeigt nur an (Ansatz A).** Django rendert
  je Display ein 1-Bit-Bild mit Pillow (`desksharing.door_render`, Zustand in
  `door_view`); die Firmware holt es, zeichnet es und schläft. Tastendrücke
  gehen als Ereignisse an den Server, die Antwort ist das nächste Bild.
  Zustände, Datenschutz und Texte gibt es nur einmal; Layoutänderungen
  brauchen kein Neuflashen; jedes Schild lässt sich ohne Hardware als PNG
  prüfen (`/api/desks/manage/rooms/<id>/door-preview.png`).
- **Öffentlicher Betrachter.** Bilder entstehen mit `viewer=None`
  (`desksharing.privacy`): verborgene Arbeitsplatz-Inhaber erscheinen als
  „belegt", Besprechungsräume zeigen Inhaber/in und Titel wie überall in
  Desksharing.
- **Weckrhythmus vom Server** (`X-Next-Wake`): 300 s in den Öffnungszeiten,
  sonst bis kurz vor Öffnung (höchstens 4 h). Das ETag wird über das Bild
  *ohne* den Zeitstempel „Stand HH:MM" gebildet; unveränderter Zustand ergibt
  304, das Panel wird nicht neu gezeichnet.
- **Tasten-Sitzungen im Server.** Ablauf aus Auswahl, Bestätigung und Dauer
  liegt in `Display.ui_state` (`door_session`) und verfällt nach 20 s bzw.
  10 s; das Gerät bleibt nur wach, solange der Server `X-Session-Timeout`
  sendet.
- **Aktionen an der Tür sind anonym.** Ein-/Auschecken und anonyme
  Besprechungsbuchung handeln als das Display, nie als Person: keine
  Inhaberprüfung, **Zugriffsgruppen schränken sie nicht ein**, das
  Auschecken versendet keine Mail. Die anonyme Buchung hat `holder=None` und
  `Reservation.display`, zählt so in der Statistik als genutzt und wird nicht
  mit einer anonymisierten Altbuchung verwechselt; Auschecken an der Tür
  gibt mit `ReleaseReason.DISPLAY` frei. `DisplayEvent` ist das Protokoll
  (Aktion, Raum, Platz, Zeit – **keine Person**) und wird nach der
  Aufbewahrungsfrist der Abteilung gelöscht. Arbeitsplätze werden nur für
  eine Person gebucht (QR-Code, Anmeldung).
- **Kopplung per Code, Geheimnis je Gerät.** Ein unbekanntes Geheimnis bei
  `GET /api/displays/frame/` legt ein ausstehendes Display an, das Bild zeigt
  einen 8-stelligen Code (10 min). Ein Abteilungsadmin löst ihn unter
  `/desks/manage/displays` ein und wählt den Raum. Gespeichert wird nur der
  SHA-256 des Geheimnisses; es gilt nur für den eigenen Raum; Entfernen
  sperrt sofort. Der offene Weg (Bildabrufe unbekannter/ungekoppelter
  Geräte) ist je Client-IP gedrosselt (12/min, `common.net.client_ip`) und
  begrenzt ausstehende Anfragen; Tastenereignisse sind je Display
  ratenbegrenzt.
- **Kein neuer Dienst, keine neue Umgebungsvariable.** Die Geräte nutzen das
  vorhandene Backend per HTTPS; die Firmware prüft das Zertifikat gegen
  eingebettete Wurzeln (ISRG X1 + X2). Die Firmware liegt in
  `firmware/door-display/` (PlatformIO).

## Consequences
- Eine Layout-Implementierung; jede Änderung kommt mit dem Backend. Preis:
  Jeder Tastendruck in einem Ablauf ist ein Netzwerk-Roundtrip (~0,3–1 s).
- Türschilder zeigen Namen im Flur (Arbeitsplatz-Inhaber außer bei Opt-out;
  Besprechungsräume immer) – Datenschutzseite und Personalrats-Zusammenfassung
  erwähnen das.
- Wer an der Tür steht, kann eine Buchung ein-/auschecken oder einen freien
  Besprechungsraum belegen, auch ohne Zugriffsgruppen-Recht; vom
  Produktverantwortlichen akzeptiert. Wer physisch an ein Gerät kommt, kann
  das unverschlüsselte NVS-Geheimnis auslesen, bis Flash-Verschlüsselung mit
  dem späteren Einrichtungsmodus kommt.
- Zertifikatsdaten werden nicht geprüft, da das Gerät keine Uhrzeit hat
  (mbedTLS ohne `MBEDTLS_HAVE_TIME_DATE`); abgelaufene, aber sonst gültige
  Ketten werden akzeptiert.
- Neu flashen ist nur für Client-Änderungen nötig (WLAN, Server-URL,
  Wurzelzertifikate).

## Alternatives considered
- **B – Server schickt JSON, Gerät zeichnet:** sofortiges Feedback und
  weniger Daten, aber jede Layoutänderung hieße alle Displays neu zu flashen,
  und die Regeln gäbe es doppelt (Server und Firmware). Verworfen.
- **Hybrid (Auswahlbild lokal gezeichnet):** nur falls A im Test zu träge
  wirkt; bisher nicht nötig.
- **ESPHome für die Firmware:** der Ablauf aus Auswahl, Bestätigung und
  Timeout ist dort sperrig; gewählt wurde Arduino/PlatformIO.
