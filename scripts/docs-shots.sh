#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)
#
# Website screenshots: bring up the isolated docs stack, (re)create its
# synthetic demo data and take the shots. Run from the repository root:
#
#   scripts/docs-shots.sh
#   KEEP_DOCS_STACK=1 scripts/docs-shots.sh   # leave docs-* running afterwards
#
# Only the docs-* services (ports 8011/5183) are started and stopped. They use
# the database `ausleihbar_docs` on the existing `db` service; the dev
# database and the dev containers stay untouched (the seed command refuses to
# run on any database whose name doesn't end with `_docs`).
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.docs.yml --profile docs)
DOCS_DB=ausleihbar_docs
FRONTEND_URL=http://localhost:5183
BACKEND_URL=http://localhost:8011

log() { printf '\033[1m[docs-shots]\033[0m %s\n' "$*"; }

wait_for() { # <description> <timeout seconds> <command…>
  local what=$1 timeout=$2 waited=0
  shift 2
  until "$@" >/dev/null 2>&1; do
    if (( waited >= timeout )); then
      log "Timed out waiting for $what."
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

stop_docs_stack() {
  if [[ "${KEEP_DOCS_STACK:-0}" == "1" ]]; then
    log "KEEP_DOCS_STACK=1 — docs stack left running ($FRONTEND_URL, $BACKEND_URL)."
  else
    log "Stopping the docs stack…"
    "${COMPOSE[@]}" stop docs-frontend docs-backend >/dev/null 2>&1 || true
  fi
}
trap stop_docs_stack EXIT

# --- database server ---------------------------------------------------------
# A no-op when the dev db is already running (it is never recreated or stopped).
if ! docker compose ps --status running --services 2>/dev/null | grep -qx db; then
  log "Starting the db service…"
  docker compose up -d db
fi
wait_for "the database server" 60 docker compose exec -T db sh -c 'pg_isready -U "$POSTGRES_USER"'
PGUSER=$(docker compose exec -T db printenv POSTGRES_USER | tr -d '\r')

DB_EXISTS=$(docker compose exec -T db psql -U "$PGUSER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$DOCS_DB'" | tr -d '[:space:]')
if [[ "$DB_EXISTS" != "1" ]]; then
  log "Creating database $DOCS_DB…"
  docker compose exec -T db createdb -U "$PGUSER" "$DOCS_DB"
fi

# --- docs services -------------------------------------------------------------
# --no-deps: never (re)create the dev services; -V: fresh node_modules volume
# from the (re)built image, so a changed lockfile can't leave a stale one.
log "Starting docs-backend and docs-frontend…"
"${COMPOSE[@]}" up -d --build --no-deps -V docs-backend docs-frontend

wait_for "docs-backend" 120 "${COMPOSE[@]}" exec -T docs-backend python -c "print(1)"
log "Migrating $DOCS_DB…"
"${COMPOSE[@]}" exec -T docs-backend python manage.py migrate --noinput
"${COMPOSE[@]}" exec -T docs-backend python manage.py compilemessages >/dev/null
log "Seeding demo data…"
SEED_SUMMARY=$("${COMPOSE[@]}" exec -T docs-backend python manage.py seed_docs_demo --reset | tail -n 1)
export SEED_SUMMARY
log "Seed summary: $SEED_SUMMARY"

wait_for "$BACKEND_URL/api/whoami/" 120 curl -fsS "$BACKEND_URL/api/whoami/"
wait_for "$FRONTEND_URL" 180 curl -fsS "$FRONTEND_URL"
log "Docs stack ready: $FRONTEND_URL (API $BACKEND_URL)."

# --- shots ----------------------------------------------------------------------
# Playwright runs on the host (the frontend container has no browser). The
# host's frontend/node_modules is separate from the containers' (they mount an
# anonymous volume); `--no-save` installs from the lockfile without rewriting it.
SEED_FILE=$(mktemp -t ausleihbar-docs-seed.XXXXXX)
trap 'rm -f "$SEED_FILE"; stop_docs_stack' EXIT
printf '%s\n' "$SEED_SUMMARY" > "$SEED_FILE"

if [[ ! -x frontend/node_modules/.bin/playwright ]]; then
  log "Installing the frontend dev dependencies on the host (for Playwright)…"
  (cd frontend && npm install --no-save --no-audit --no-fund)
fi
log "Making sure Playwright's Chromium is installed…"
(cd frontend && npx playwright install chromium)

log "Taking the screenshots…"
(cd frontend && DOCS_SEED="$SEED_FILE" npm run docs:shots)

log "Done."
