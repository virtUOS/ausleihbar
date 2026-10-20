# Projekt-Website

Quellen der Projekt-Website (GitHub Pages): Startseite, Anleitung für
Ausleihende, Anleitung für Verleihende und Admins, Installation. Die Website
ist bisher nur auf Deutsch (an der Wurzel); Englisch ist vorbereitet, aber
noch nicht gebaut — später als `mkdocs.en.yml` mit `INHERIT` und Quellen in
`en/`, wie bei abstimmbar (dazu Sprachumschalter und `exclude_docs` ergänzen).

## Website bauen und ansehen

[MkDocs Material](https://squidfunk.github.io/mkdocs-material/), Konfiguration
`website/mkdocs.yml`. Der Workflow `.github/workflows/docs.yml` baut die
Website bei Pull Requests (`--strict`) und veröffentlicht sie bei Änderungen
auf `main` auf GitHub Pages. Alle Befehle **im Repo-Root** ausführen
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
mkdocs serve -f website/mkdocs.yml     # http://127.0.0.1:8000/ausleihbar/
mkdocs build --strict -f website/mkdocs.yml
```

Die fertige Seite unter dem Pages-Pfad ansehen:

```bash
mkdir -p /tmp/pages && ln -sfn "$PWD/site" /tmp/pages/ausleihbar
python3 -m http.server -d /tmp/pages    # http://localhost:8000/ausleihbar/
```

## Aufbau

- `index.md` — Startseite; `anleitung/` — Anleitung für Ausleihende;
  `verwaltung/` — Verleihtheke und Administration (ein Kapitel pro Datei).
- `installation.md` bindet `docs/INSTALL.md` per `pymdownx.snippets` ein —
  Änderungen dort machen. Relative Links aus dem Dokument auf andere Dateien
  in `docs/` schreibt `hooks/docs_links.py` auf GitHub um.
- `assets/ausleihbar.css` — das „-bar“-Theme (Tokens aus
  `frontend/tailwind.config.js`, Präfix `--al-`), `assets/logo.svg` — Logo und
  Favicon.

## Screenshots (`bilder/`)

(Wird ergänzt, sobald die Screenshot-Pipeline steht.)
