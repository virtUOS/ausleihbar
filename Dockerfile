# Production image: builds the SPA and bundles it with the Django backend.
# On start the container copies /app/frontend_dist into the shared
# frontend_data volume for Caddy to serve directly (see
# docker-compose.prod.yml) — this image is the single versioned artifact for
# a release; Caddy itself does no building.

FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System dependencies: psycopg build deps, gettext (for compilemessages) and
# gosu (drops from root to the `app` user at start, see below).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc gettext gosu \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user (fixed uid/gid 1000 so volume ownership is stable
# across image versions). The image deliberately has no `USER app`: the
# production start command (docker-compose.prod.yml) runs its setup steps as
# root — copying the SPA into the frontend_data volume, migrate,
# compilemessages (writes .mo files next to the code), collectstatic and a
# chown of the media volume, which existing installations created root-owned —
# and then hands over to gunicorn with `exec gosu app …`. The application code,
# static files and the SPA stay root-owned and read-only for `app`; only
# /app/media (uploads) is writable by it.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home-dir /app \
       --no-create-home --shell /usr/sbin/nologin app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-build /frontend/dist /app/frontend_dist
RUN mkdir -p /app/media /app/staticfiles \
    && chown app:app /app/media

EXPOSE 8000

# Production-safe default: an image started without docker-compose.prod.yml
# runs gunicorn as `app`, never the dev server. (Still needs the production
# env — DJANGO_SECRET_KEY, DJANGO_DEBUG=0, database — like any deployment.)
CMD ["gosu", "app", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
