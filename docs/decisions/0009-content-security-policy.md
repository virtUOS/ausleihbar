# 0009. Content-Security-Policy und Security-Header

- **Status:** Accepted (report-only; enforcement in #45)
- **Date:** 2026-09-29

## Context
Seit Issue #5 können Verleihende und Admins Produktbeschreibungen als
formatierten HTML-Text (Rich Text) pflegen. Das Frontend rendert diesen
Inhalt, und bisher lieferte der Server keinerlei Security-Header aus — weder
eine Content-Security-Policy (CSP) noch `X-Content-Type-Options` oder
`Referrer-Policy`. Sollte die Bereinigung des HTML einmal eine Lücke haben,
gäbe es keine zweite Verteidigungslinie gegen Cross-Site-Scripting. Hochgeladene
Medien werden zudem direkt unter `/media/` ausgeliefert und könnten, falls ein
Browser sie als HTML interpretiert, Skripte im Ursprung der Anwendung
ausführen (Issue #44).

Randbedingungen: Das Frontend ist eine statische SPA (Vite-Build), die Caddy
ausliefert; es gibt keinen serverseitigen Render-Schritt, in dem sich pro
Antwort ein Nonce einfügen ließe. Eine strenge Policy darf außerdem nicht still
Funktionen zerstören (Bildzuschnitt, QR-Etikettendruck).

## Decision
- **Strenge `'self'`-CSP für die SPA.** Skripte, Styles, Schriften und
  Verbindungen kommen nur vom eigenen Ursprung (Bilder zusätzlich als `data:`
  und `blob:`); kein `'unsafe-inline'` und kein `'unsafe-eval'`; außerdem
  `frame-ancestors 'none'`, `object-src 'none'` und eingeschränkte `base-uri`
  und `form-action`.
- **Kein Inline-Markup im Frontend:** kein `<script>`, kein `<style>` und kein
  `style="…"`-Attribut in ausgelieferten Dateien oder zur Laufzeit erzeugtem
  HTML. React-`style={{ … }}` ist unproblematisch (setzt Eigenschaften über das
  CSSOM, nicht über ein Attribut im Markup). Konkret umgesetzt: das Theme-Skript
  liegt als `frontend/public/theme-init.js`, das QR-Etiketten-Druck-CSS als
  statische Dateien unter `frontend/public/print/` (`qr-print-base.css`,
  `qr-sheet.css`, `qr-label-<id>.css`), die per `<link>` geladen werden;
  `react-easy-crop` läuft mit `disableAutomaticStylesInjection` und seinem
  mitgelieferten CSS.
- **Header liegen im Caddy-Snippet** `deploy/caddy/security-headers.caddy`
  (im Repository versioniert, per Compose read-only eingebunden), damit
  Header-Änderungen mit `git pull` kommen und kein Eingriff in das
  installationsspezifische `Caddyfile` nötig ist. Snippets: `security_headers`
  (jede Antwort: `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`; Werte von Django werden ersetzt),
  `spa_csp` (nur SPA) und `media_csp`.
- **Erst Report-Only:** Die SPA bekommt `Content-Security-Policy-Report-Only`
  plus `Reporting-Endpoints`. Browser melden Verstöße an `POST /api/csp-report/`
  (`common`-App); gespeichert werden sie aggregiert in `common.CspViolation`
  (eindeutig je Direktive + blockierter Quelle + Seite, mit Zähler und
  erstem/letztem Auftreten, höchstens 1000 Zeilen). Es werden keine IP-Adressen,
  Nutzer, Query-Strings oder Code-Samples gespeichert; Seiten werden nur als
  Pfad, blockierte URLs nur als Origin abgelegt. Einsehbar im Django-Admin unter
  **Common → CSP violations**. Das Umschalten auf `Content-Security-Policy`
  (enforcing) folgt in #45, sobald die Liste sauber bleibt.
- **`/media/*` bekommt sofort eine erzwungene Sandbox-CSP**, sodass hochgeladene
  Dateien selbst bei falscher Interpretation als HTML keine Skripte ausführen
  können.
- **Admin und API bleiben vorerst ohne CSP.** Das Django-Admin arbeitet mit
  Inline-Skripten und -Styles; eine Policy dafür wäre ein eigenes Vorhaben.

## Consequences
- Neuer Frontend-Code und neue Bibliotheken dürfen weder Inline-Skripte noch
  Inline-Styles einschleusen. Bibliotheken, die Styles zur Laufzeit in den
  `<head>` schreiben, müssen so konfiguriert werden, dass sie das nicht tun
  (Beispiel `react-easy-crop` mit `disableAutomaticStylesInjection`); ihr CSS
  wird stattdessen als Datei importiert. Verstöße erscheinen im Admin als
  CSP-Reports.
- Dynamisches Druck-CSS (QR-Etiketten je Format) lebt in statischen Dateien pro
  Format und wird per `<link>` eingebunden statt als `<style>` erzeugt.
  Ein neues Etikettenformat braucht daher eine neue CSS-Datei.
- Eine fehlende Snippet-Datei oder fehlende `import`-Zeilen im `Caddyfile`
  lassen Caddy die Konfiguration nicht laden. Bestehende Installationen müssen
  die vier `import`-Zeilen und den Compose-Mount gemeinsam einspielen
  (siehe `docs/INSTALL.md`, Schritt 8).
- Da `Caddyfile` und Snippet Einzeldatei-Bind-Mounts sind, muss der Caddy-
  Container nach Änderungen neu erzeugt werden
  (`docker compose -f docker-compose.prod.yml up -d --force-recreate caddy`);
  `restart` oder `caddy reload` genügen nicht zuverlässig.
- Solange die Policy nur berichtet, schützt sie noch nicht. Bis #45 ist der
  Nutzen die Sichtbarkeit; die Tabelle `CspViolation` ist dabei bewusst
  begrenzt, damit ein manipulierter Client sie nicht aufblähen kann.

## Alternatives considered
- **Hashes oder Nonces für Inline-Code erlauben:** Nonces sind bei einer
  statischen SPA nicht möglich (kein Render-Schritt pro Antwort). Hashes sind
  spröde — jede Änderung am Inline-Code oder Build bricht sie — und würden
  Inline-Code dauerhaft legitimieren, statt ihn abzuschaffen.
- **Benannte `@page`-Regeln für den Etikettendruck** (statt dynamischem
  `<style>`): verworfen, da sie erst ab Safari 18.2 unterstützt werden und das
  bereits abgestimmte Druckverhalten neu justiert werden müsste.
- **Reports nur ins Log schreiben** statt in die Datenbank: verworfen, weil
  Verleihende und Admins auf einem typischen Hosting keinen bequemen
  Log-Zugriff haben; die aggregierte Admin-Liste macht Ursachen ohne
  Server-Zugang sichtbar.
