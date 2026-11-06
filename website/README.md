# Projekt-Website

Quellen der Projekt-Website (GitHub Pages): Startseite, Anleitung für
Ausleihende, Anleitung für Verleihende und Admins, Installation —
zweisprachig: Deutsch an der Wurzel der Website, Englisch unter `/en/`.

## Zwei Sprachen

Die Website besteht aus zwei MkDocs-Konfigurationen, ohne i18n-Plugin (wie
bei abstimmbar):

- `mkdocs.yml` — Deutsch, Quellen in diesem Ordner, Ausgabe `site/`.
- `mkdocs.en.yml` — Englisch, erbt per `INHERIT` Theme, CSS, `overrides/`,
  Hooks und Markdown-Erweiterungen; Quellen in `en/` (englische Dateinamen,
  z. B. `en/guide/cart.md`, `en/management/day-overview.md`), Ausgabe
  `site/en/`. Die deutsche Konfiguration schließt `en/` aus.
- `hooks/i18n.py` verknüpft die Seiten paarweise (Tabelle `PAGES`, deutscher
  Quellpfad → englischer) für den Sprachumschalter im Kopf
  (`overrides/partials/alternate.html`, springt zum Gegenstück der aktuellen
  Seite) und stellt der englischen Seite die gemeinsamen `assets/` bereit.
  Bilder dagegen nicht: englische Seiten verwenden nur `en/bilder/`.

**Beide Sprachen synchron halten:** Jede Änderung an einer deutschen Seite
braucht die passende Änderung in `en/`. **Neue Seite:** deutsche und
englische Datei anlegen, in beide `nav`-Listen (`mkdocs.yml`,
`mkdocs.en.yml`) und in `PAGES` eintragen; beim Umbenennen ebenso. Beide
Installationsseiten binden dasselbe (englische) `docs/INSTALL.md` ein.

Englische Texte: amerikanische Schreibweise (wie die Oberfläche, z. B.
„Catalog“, „Favorites“); Bezeichnungen aus der Oberfläche wörtlich aus
`frontend/src/locales/en/translation.json` übernehmen. Begriffe: Gegenstand
= item, Verleihtheke = lending desk, Verleihteam = lending team, Sparte =
section, Direktausleihe = walk-in lending, Nutzung vor Ort = on-site use.

## Website bauen und ansehen

[MkDocs Material](https://squidfunk.github.io/mkdocs-material/), Konfiguration
`website/mkdocs.yml`. Der Workflow `.github/workflows/docs.yml` baut die
Website bei Pull Requests (`--strict`) und veröffentlicht sie bei Änderungen
auf `main` auf GitHub Pages. Alle `mkdocs`-Befehle **im Repo-Root** ausführen
(Einbindung von `docs/INSTALL.md` und Ausgabeordner `site/` setzen das voraus).

Wie in CI erst Deutsch (räumt `site/` auf), dann Englisch nach `site/en/`.
Ohne lokale Python-Umgebung, per Docker:

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c \
  "pip install -q -r website/requirements.txt \
   && mkdocs build --strict -f website/mkdocs.yml \
   && mkdocs build --strict -f website/mkdocs.en.yml"
```

Oder in einer virtuellen Umgebung:

```bash
python3 -m venv /tmp/ausleihbar-docs && . /tmp/ausleihbar-docs/bin/activate
pip install -r website/requirements.txt
mkdocs serve -f website/mkdocs.yml -a 127.0.0.1:8093      # deutsch, http://127.0.0.1:8093/ausleihbar/
mkdocs serve -f website/mkdocs.en.yml -a 127.0.0.1:8094   # englisch, http://127.0.0.1:8094/ausleihbar/en/
# (Port 8000 ist auf dem Dev-Rechner belegt – hier freie Ports)
mkdocs build --strict -f website/mkdocs.yml
mkdocs build --strict -f website/mkdocs.en.yml
```

`mkdocs serve` zeigt nur eine Sprache; der Sprachumschalter funktioniert erst
in der fertig gebauten Seite.

Die fertige Seite unter dem Pages-Pfad ansehen:

```bash
mkdir -p /tmp/pages && ln -sfn "$PWD/site" /tmp/pages/ausleihbar
python3 -m http.server -d /tmp/pages    # http://localhost:8000/ausleihbar/
```

## Aufbau

- `index.md` – Startseite; `anleitung/` – Anleitung für Ausleihende;
  `verwaltung/` – Verleihtheke und Administration (ein Kapitel pro Datei);
  englisch entsprechend `en/index.md`, `en/guide/`, `en/management/`.
- `installation.md` und `en/installation.md` binden `docs/INSTALL.md` per
  `pymdownx.snippets` ein –
  Änderungen dort machen. Relative Links aus dem Dokument auf andere Dateien
  in `docs/` schreibt `hooks/docs_links.py` auf GitHub um.
- `assets/ausleihbar.css` – das „-bar“-Theme (Tokens aus
  `frontend/tailwind.config.js`, Präfix `--al-`), `assets/logo.svg` – Logo und
  Favicon.

## Screenshots (`bilder/`, `en/bilder/`)

Die Bilder in `bilder/` (Deutsch) und `en/bilder/` (Englisch, gleiche
Dateinamen) sind **generiert** – nicht von Hand ersetzen oder
nachbearbeiten, sondern die Pipeline neu laufen lassen. Sie zeigen nur
erfundene Demodaten (Alex Beispiel, Kim Verleih, Sam Admin, Robin Gesperrt …,
Adressen unter `example.org`).

Voraussetzungen: Docker (Compose) mit laufendem `db`-Dienst des Projekts
bzw. startbar, Node.js auf dem Host (Playwright läuft auf dem Host, nicht im
Container). Fehlende Frontend-Abhängigkeiten und Playwrights Chromium
installiert das Skript selbst. Aus dem Repo-Root:

```bash
scripts/docs-shots.sh               # beide Sprachen (= --lang all)
scripts/docs-shots.sh --lang de     # nur bilder/
scripts/docs-shots.sh --lang en     # nur en/bilder/
```

Das Skript startet den isolierten Docs-Stack (`docs-backend` auf
`localhost:8011`, `docs-frontend` auf `localhost:5183`, Datenbank
`ausleihbar_docs`), migriert ihn und nimmt dann je Sprache alle Screenshots auf: erst
`seed_docs_demo --reset --language <de|en>` (gleiche Daten in beiden Läufen;
Personennamen bleiben gleich, Freitexte wie Buchungsnotizen, Strike-Gründe
oder Sperrtag-Gründe sind englisch, Katalogtexte kommen aus den `_en`-Feldern),
dann `npm run docs:shots` (`frontend/e2e/docs-screenshots.spec.ts`) mit
`DOCS_SHOTS_LANG=<de|en>`. Danach stoppt es den Docs-Stack wieder.
Die Entwicklungsdatenbank und die Dev-Container bleiben unberührt. Die
Anmeldung läuft ohne Keycloak über `docs_session <user>` (nur auf der
Docs-Datenbank erlaubt).

Umgebungsvariablen:

| Variable | Wirkung |
| --- | --- |
| `DOCS_SHOTS_ONLY=start,produkt` | nur diese Bilder neu aufnehmen (Dateinamen ohne `.png`) |
| `DOCS_SHOTS_DIR=/tmp/bilder` | Bilder in ein anderes Verzeichnis schreiben (Standard: `website/bilder` bzw. `website/en/bilder`) |
| `KEEP_DOCS_STACK=1` | Docs-Stack danach laufen lassen (zum Nachsehen unter `localhost:5183`) |

Formate: Desktop 1440×900 bei Skalierung 1,5 (meist auf die mittlere
Inhaltsspalte, 896 px breit, zugeschnitten; einzelne Bilder zeigen nur einen
Ausschnitt), Handy 390×844 bei Skalierung 2; helles Farbschema, Sprache
Deutsch (`de-DE`) bzw. Englisch (`en-GB`). Läuft ein Bild schief, meldet der Lauf am Ende alle
fehlgeschlagenen Bilder; die übrigen werden trotzdem geschrieben.
