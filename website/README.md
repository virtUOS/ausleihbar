# Projekt-Website

Quellen der Projekt-Website (GitHub Pages): Startseite, Anleitung für
Ausleihende, Anleitung für Verleihende und Admins, Installation. Die Website
ist bisher nur auf Deutsch (an der Wurzel); Englisch ist vorbereitet, aber
noch nicht gebaut – später als `mkdocs.en.yml` mit `INHERIT` und Quellen in
`en/`, wie bei abstimmbar (dazu Sprachumschalter und `exclude_docs` ergänzen).

## Website bauen und ansehen

[MkDocs Material](https://squidfunk.github.io/mkdocs-material/), Konfiguration
`website/mkdocs.yml`. Der Workflow `.github/workflows/docs.yml` baut die
Website bei Pull Requests (`--strict`) und veröffentlicht sie bei Änderungen
auf `main` auf GitHub Pages. Alle `mkdocs`-Befehle **im Repo-Root** ausführen
(Einbindung von `docs/INSTALL.md` und Ausgabeordner `site/` setzen das voraus).

Ohne lokale Python-Umgebung, per Docker:

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c \
  "pip install -q -r website/requirements.txt && mkdocs build --strict -f website/mkdocs.yml"
```

Oder in einer virtuellen Umgebung:

```bash
python3 -m venv /tmp/ausleihbar-docs && . /tmp/ausleihbar-docs/bin/activate
pip install -r website/requirements.txt
mkdocs serve -f website/mkdocs.yml -a 127.0.0.1:8002   # http://127.0.0.1:8002/ausleihbar/
# (Port 8000 ist auf dem Dev-Rechner belegt, daher 8002)
mkdocs build --strict -f website/mkdocs.yml
```

Die fertige Seite unter dem Pages-Pfad ansehen:

```bash
mkdir -p /tmp/pages && ln -sfn "$PWD/site" /tmp/pages/ausleihbar
python3 -m http.server -d /tmp/pages    # http://localhost:8000/ausleihbar/
```

## Aufbau

- `index.md` – Startseite; `anleitung/` – Anleitung für Ausleihende;
  `verwaltung/` – Verleihtheke und Administration (ein Kapitel pro Datei).
- `installation.md` bindet `docs/INSTALL.md` per `pymdownx.snippets` ein –
  Änderungen dort machen. Relative Links aus dem Dokument auf andere Dateien
  in `docs/` schreibt `hooks/docs_links.py` auf GitHub um.
- `assets/ausleihbar.css` – das „-bar“-Theme (Tokens aus
  `frontend/tailwind.config.js`, Präfix `--al-`), `assets/logo.svg` – Logo und
  Favicon.

## Screenshots (`bilder/`)

Die Bilder in `bilder/` sind **generiert** – nicht von Hand ersetzen oder
nachbearbeiten, sondern die Pipeline neu laufen lassen. Sie zeigen nur
erfundene Demodaten (Alex Beispiel, Kim Verleih, Sam Admin, Robin Gesperrt …,
Adressen unter `example.org`).

Voraussetzungen: Docker (Compose) mit laufendem `db`-Dienst des Projekts
bzw. startbar, Node.js auf dem Host (Playwright läuft auf dem Host, nicht im
Container). Fehlende Frontend-Abhängigkeiten und Playwrights Chromium
installiert das Skript selbst. Aus dem Repo-Root:

```bash
scripts/docs-shots.sh
```

Das Skript startet den isolierten Docs-Stack (`docs-backend` auf
`localhost:8011`, `docs-frontend` auf `localhost:5183`, Datenbank
`ausleihbar_docs`), migriert und befüllt ihn mit `seed_docs_demo --reset`,
nimmt alle Screenshots auf (`npm run docs:shots`,
`frontend/e2e/docs-screenshots.spec.ts`) und stoppt den Docs-Stack wieder.
Die Entwicklungsdatenbank und die Dev-Container bleiben unberührt. Die
Anmeldung läuft ohne Keycloak über `docs_session <user>` (nur auf der
Docs-Datenbank erlaubt).

Umgebungsvariablen:

| Variable | Wirkung |
| --- | --- |
| `DOCS_SHOTS_ONLY=start,produkt` | nur diese Bilder neu aufnehmen (Dateinamen ohne `.png`) |
| `DOCS_SHOTS_DIR=/tmp/bilder` | Bilder in ein anderes Verzeichnis schreiben (Standard: `website/bilder`) |
| `KEEP_DOCS_STACK=1` | Docs-Stack danach laufen lassen (zum Nachsehen unter `localhost:5183`) |

Formate: Desktop 1440×900 bei Skalierung 1,5 (meist auf die mittlere
Inhaltsspalte, 896 px breit, zugeschnitten; einzelne Bilder zeigen nur einen
Ausschnitt), Handy 390×844 bei Skalierung 2; helles Farbschema, Sprache
Deutsch (`de-DE`). Läuft ein Bild schief, meldet der Lauf am Ende alle
fehlgeschlagenen Bilder; die übrigen werden trotzdem geschrieben.
