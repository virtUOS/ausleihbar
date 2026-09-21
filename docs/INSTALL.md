# Installation & configuration guide

This guide covers running Ausleihbar locally and what to configure for a real
deployment. For a 60-second local start see the README; this document is the
full reference.

## 1. Architecture

Ausleihbar runs as four services (see `docker-compose.yml`):

| Service    | What it is                          | Dev port |
|------------|-------------------------------------|----------|
| `db`       | PostgreSQL 16                       | 5432     |
| `backend`  | Django 5 + DRF API + Django admin   | 8000     |
| `frontend` | React + Vite SPA                    | 5173     |
| `keycloak` | OIDC provider (local dev only)      | 8080     |

- Backend / Django admin: http://localhost:8000/admin/
- Frontend (shop): http://localhost:5173
- Keycloak admin: http://localhost:8080 (dev `admin`/`admin`)

> If host port 8000 is already taken on your machine, set `BACKEND_PORT` (and a
> matching `VITE_API_BASE_URL`) in `.env` to publish the backend elsewhere.

## 2. Prerequisites

- Docker + Docker Compose.
- On macOS without Docker Desktop: [colima](https://github.com/abiosoft/colima)
  (`colima start`, then `docker compose …`).

## 3. Quick start (development)

```bash
cp .env.example .env                 # 1. environment file
docker compose up --build            # 2. start db + backend + frontend + keycloak
docker compose exec backend python manage.py migrate          # 3. database schema
docker compose exec backend python manage.py createsuperuser  # 4. break-glass admin
# optional:
docker compose exec backend python manage.py seed_demo        #    demo catalog & data
docker compose exec backend python manage.py refresh_holidays #    load public holidays
```

The bundled Keycloak imports a realm `ausleihbar` with a demo user
(`demo`/`demo`); OIDC login works out of the box in dev. Migrations run inside
the container, never on the host.

## 4. Configuration reference

All configuration is via environment variables (read in
`backend/config/settings.py`; defaults target local dev). Set them in `.env`
(read by Docker Compose) or your deployment's secret store. **Never commit real
secrets** — `.env` is git-ignored; keep production secrets out of
`docker-compose.yml`.

### 4.1 PostgreSQL

| Variable            | Default      | Notes |
|---------------------|--------------|-------|
| `POSTGRES_DB`       | `ausleihbar` | |
| `POSTGRES_USER`     | `ausleihbar` | |
| `POSTGRES_PASSWORD` | `ausleihbar` | **Change for production.** |
| `POSTGRES_HOST`     | `db`         | Set when using an external DB. |
| `POSTGRES_PORT`     | `5432`       | |

### 4.2 Django core

| Variable               | Default (dev)                                   | Production |
|------------------------|-------------------------------------------------|------------|
| `DJANGO_SECRET_KEY`    | insecure placeholder                            | **Set a long random secret.** |
| `DJANGO_DEBUG`         | `1`                                             | **`0`** |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0,backend`           | Your real host name(s). |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`   | The SPA's public origin(s). |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:5173,http://localhost:8000`   | The SPA + API public origins. |
| `CONTENT_DEFAULT_LANGUAGE` | `de`                                        | Canonical content language (`de` or `en`). See §4.4. |

The SPA calls the API with the session cookie, so the API and SPA origins must
be listed in CORS/CSRF and credentials are allowed.

#### Content language (translatable catalog content)

Catalog content (product, category, section, set, page and pool text) is
translatable into every language in `LANGUAGES` (German and English). The
**canonical language** set by `CONTENT_DEFAULT_LANGUAGE` is the one that is

- **required** when an editor creates content, and
- the **first fallback** the shop shows when another language has no value.

It is read once at start-up, so change it in `.env` and restart the backend
(`docker compose up -d backend`); an unsupported value stops the backend with a
clear error. The SPA learns the value from the backend (via `whoami`), so set it
in **one place** only. Default is German, matching the seeded data; an
institution publishing this software can set `CONTENT_DEFAULT_LANGUAGE=en` to
make English canonical instead.

##### Optional: machine-translation pre-fill

The editor can offer a one-click "Translate from <language>" button that
pre-fills an empty translation from the canonical value (an editable draft — it
never overwrites a human translation). It is **off by default** and uses a
pluggable, self-hostable provider.

To enable with the bundled [LibreTranslate](https://libretranslate.com)
(Apache-2.0) service:

```bash
# start the optional service (first run downloads the de/en model)
docker compose --profile translation up -d libretranslate
```

and set in `.env`:

```dotenv
CONTENT_TRANSLATION_PROVIDER=libretranslate
LIBRETRANSLATE_URL=http://libretranslate:5000   # or an external instance
# LIBRETRANSLATE_API_KEY=...                     # if your instance requires one
```

The backend proxies translation requests (`POST /api/manage/translate/`,
lender/admin only) so the URL and key stay server-side. With the provider unset
the button is hidden and the endpoint returns `503`.

| Variable                       | Default                     | Notes |
|--------------------------------|-----------------------------|-------|
| `CONTENT_TRANSLATION_PROVIDER` | `none`                      | `libretranslate` to enable. |
| `LIBRETRANSLATE_URL`           | `http://libretranslate:5000`| The (self-hosted) instance. |
| `LIBRETRANSLATE_API_KEY`       | empty                       | If the instance requires a key. |

#### Secret encryption at rest (`TOKEN_ENCRYPTION_KEY`)

Some optional features store a third-party secret per pool — currently the
**GitLab access token** used to open a defect ticket (see §4.7). These secrets
are **encrypted at rest** with [Fernet](https://cryptography.io/en/latest/fernet/)
(AES-128 + HMAC): the database column and any backup hold only ciphertext, and
the API never returns the value (write-only; it only reports whether one is
set).

The encryption key comes from `TOKEN_ENCRYPTION_KEY`. If you leave it unset, a
key is **derived from `DJANGO_SECRET_KEY`** so the feature works out of the box —
but then rotating `DJANGO_SECRET_KEY` makes the stored secrets undecryptable
(they degrade to "not set" and must be re-entered). For production, set a
**dedicated, stable key** and keep it in your backups alongside the database:

```bash
# generate a key
docker compose exec backend \
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```dotenv
TOKEN_ENCRYPTION_KEY=PASTE-THE-GENERATED-KEY-HERE
```

Read at start-up — change it in `.env` and recreate the backend
(`docker compose -f docker-compose.prod.yml up -d backend`). Rotating this key
invalidates already-stored tokens, so plan to re-enter them afterwards.

| Variable                | Default                       | Notes |
|-------------------------|-------------------------------|-------|
| `TOKEN_ENCRYPTION_KEY`  | derived from `DJANGO_SECRET_KEY` | A dedicated Fernet key for encrypting stored secrets at rest. |

#### Creation caps (`MAX_RESOURCES` / `MAX_PRODUCTS` / `MAX_USERS`)

Optional per-deployment ceilings on how many of each entity may be created.
**Leave a variable unset (or blank) for no limit** — the default. They are read
at start-up, so change them in `.env` and recreate the backend.

When a cap is reached, the next creation is refused with a clear message:

- `MAX_RESOURCES` / `MAX_PRODUCTS` — adding a resource/product via the API
  (admin/lender UI) returns a 400 explaining the cap.
- `MAX_USERS` — a *new* identity is turned away at first OIDC login; existing
  users keep logging in. Anonymized (deleted) accounts don't count toward the
  total, so removing one frees a slot.

Caps guard the interactive flows; **bulk operations are not capped** — the
data/leihs imports and the management shell can still exceed them (they are
trusted admin operations).

Current usage against these caps is shown on the lending desk's statistics page
(**Verleih → Auswertung → Statistik**, "Inventory & limits"): each metric shows
the count and, when a cap is set, the limit with a usage bar.

| Variable        | Default     | Notes |
|-----------------|-------------|-------|
| `MAX_RESOURCES` | unlimited   | Max physical resources (inventory units). |
| `MAX_PRODUCTS`  | unlimited   | Max catalogue products. |
| `MAX_USERS`     | unlimited   | Max (non-anonymized) user accounts. |

#### 4.7 Defect tickets in GitLab (per pool)

A pool can link a GitLab project so that marking one of its devices defective
opens an issue there. It is **opt-in and configured per pool** in the lending
area (Defects → **Connect GitLab**), not via environment variables — most pools
leave it off. Each pool stores the full project URL (server included) and an
access token (encrypted at rest, see above).

The token needs only **minimal rights**: a **Project Access Token** with the
lowest role that can create issues — **Reporter** — and **only the `api`
scope** (leave every other scope unchecked; `read_api` is not enough because
creating an issue is a write). Give it an expiry and renew it in time. Each
created issue links back to the device's page so it can be returned to service
after the repair.

#### Optional AI features

Some features can call out to an external large-language-model endpoint (e.g.
to suggest catalog attributes). This is **off by default** and only enabled by
configuring a provider — with no configuration the app behaves exactly as
before. The endpoint must be **OpenAI-compatible** (e.g. a self-hosted
[LiteLLM](https://www.litellm.ai) proxy):

```dotenv
AI_PROVIDER=litellm
AI_BASE_URL=https://litellm.example.org/v1
AI_API_KEY=...
AI_MODEL=qwen-3.5
AI_TIMEOUT=30
```

| Variable      | Default | Notes |
|---------------|---------|-------|
| `AI_PROVIDER` | `none`  | `litellm` to enable. |
| `AI_BASE_URL` | empty   | OpenAI-compatible base URL (e.g. `https://…/v1`). |
| `AI_API_KEY`  | empty   | API key/token for the endpoint. |
| `AI_MODEL`    | empty   | Model name to request, e.g. `qwen-3.5`. |
| `AI_TIMEOUT`  | `30`    | Request timeout in seconds. |
| `AI_MAX_TOKENS` | `2000` | Max reply length. Reasoning models need headroom for the answer after any hidden thinking. |
| `AI_DISABLE_THINKING` | `1` | Ask the backend to disable a reasoning model's hidden "thinking" (`chat_template_kwargs.enable_thinking=false`), so it doesn't spend the whole token budget reasoning and return an empty answer. Set `0` if your model/endpoint rejects the flag. |

When a feature that uses this is enabled, whatever text it sends (e.g. a
product's title/description) is transmitted to the configured endpoint — no
personal data about users is included. With product extraction from a PDF
manual enabled, the **extracted text of the uploaded manual** is also sent to
the configured endpoint (non-personal manual text; the PDF file itself is not
sent, and neither the file nor the extracted text is persisted). Read at
start-up: change these in `.env` and recreate the backend
(`docker compose up -d`) for them to take effect.

### 4.3 Frontend

| Variable            | Default                                                       | Notes |
|---------------------|----------------------------------------------------------------|-------|
| `VITE_API_BASE_URL` | same-origin (relative) in production; `http://localhost:8000` for `vite`/`vite build` outside docker compose | Baked into the SPA at build time, not read at container runtime — has no effect in `docker-compose.prod.yml`, whether pulling the released image or building it locally (its `Dockerfile` takes no build args). Only relevant when building the frontend yourself outside Docker. |
| `BACKEND_PORT`      | `8000`                                                          | Dev only: host port the backend is published on. |

### 4.4 Shop URL & email (notifications, QR codes)

| Variable              | Default                              | Notes |
|-----------------------|--------------------------------------|-------|
| `SHOP_BASE_URL`       | `http://localhost:5173`              | **Public URL of the shop.** Used in email links, the pickup-QR deeplink and the device-QR stickers. Set before printing QR stickers. |
| `EMAIL_BACKEND`       | console (prints to log)              | Production: `django.core.mail.backends.smtp.EmailBackend`. |
| `EMAIL_HOST`          | `localhost`                          | SMTP host. |
| `EMAIL_PORT`          | `25`                                 | |
| `EMAIL_HOST_USER`     | empty                                | |
| `EMAIL_HOST_PASSWORD` | empty                                | Keep in the secret store. |
| `EMAIL_USE_TLS`       | `0`                                  | `1` to enable TLS. |
| `DEFAULT_FROM_EMAIL`  | `Ausleihbar <noreply@ausleihbar.local>` | **Must be a sender your relay accepts.** |

### 4.5 Authentication (OIDC)

OIDC is the primary login (`mozilla-django-oidc`); Django's local password login
stays as a break-glass fallback for the `createsuperuser` account.

| Variable                          | Default (dev → Keycloak)            | Notes |
|-----------------------------------|-------------------------------------|-------|
| `OIDC_RP_CLIENT_ID`               | `ausleihbar-backend`                | Client ID registered at the IdP. |
| `OIDC_RP_CLIENT_SECRET`           | `ausleihbar-dev-secret`             | **Secret** — secret store in prod. |
| `OIDC_OP_AUTHORIZATION_ENDPOINT`  | local Keycloak auth URL             | Browser-facing (must be reachable by the user's browser). |
| `OIDC_OP_TOKEN_ENDPOINT`          | …/token                             | Back-channel (reachable by the backend). |
| `OIDC_OP_USER_ENDPOINT`           | …/userinfo                          | Back-channel. |
| `OIDC_OP_JWKS_ENDPOINT`           | …/certs                             | Back-channel. |
| `OIDC_OP_LOGOUT_ENDPOINT`         | …/logout                            | Browser-facing. |
| `OIDC_OP_ISSUER`                  | empty                               | **Shortcut:** set only this and leave the endpoints empty to auto-derive them from the provider's discovery document. |
| `OIDC_CLAIM_USERNAME`             | `preferred_username`                | Per-provider claim mapping. |
| `OIDC_CLAIM_EMAIL`                | `email`                             | |
| `OIDC_CLAIM_FIRST_NAME`           | `given_name`                        | |
| `OIDC_CLAIM_LAST_NAME`            | `family_name`                       | |
| `OIDC_GROUPS_CLAIM`               | `groups`                            | Claim carrying the user's groups/roles. |
| `OIDC_ADMIN_GROUP`                | `ausleihbar-admins`                 | Members of this IdP group get Django admin on login (empty = disabled; manage admins manually). |
| `OIDC_LOGIN_REDIRECT_URL`         | `http://localhost:5173/`            | Where the browser lands after login (the SPA). |
| `OIDC_LOGOUT_REDIRECT_URL`        | `http://localhost:5173/`            | After logout. |

> **Browser vs. back-channel split:** the authorization/logout endpoints are
> opened in the user's browser, while token/userinfo/JWKS are fetched by the
> backend. In the dev compose, the browser uses `localhost:8080` and the backend
> uses `host.docker.internal:8080` for the same Keycloak — keep that distinction
> when your browser and backend reach the IdP via different hostnames.

At the IdP, register the backend's redirect URI **`<API base>/oidc/callback/`**
(dev: `http://localhost:8000/oidc/callback/`) and a post-logout redirect to the
SPA. Verify the available claims (especially the groups claim) before go-live.

### 4.6 Keycloak (dev only)

| Variable                  | Default | Notes |
|---------------------------|---------|-------|
| `KEYCLOAK_ADMIN`          | `admin` | Dev Keycloak bootstrap admin. |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Dev only. |

The bundled Keycloak runs in `start-dev` mode and imports
`keycloak/realm-export.json`. In production you typically point OIDC at the
university IdP instead and drop this service.

## 5. Post-install / first run

1. **Migrate** the database and create a **superuser** (steps 3–4 above).
2. **Sign in via OIDC** at least once so your account exists, then grant roles:
   admins via Django admin or the `OIDC_ADMIN_GROUP`; lenders via pool
   memberships under *Admin → People & access → Users*.
3. **Create a resource pool** (Admin → Locations & inventory → Resource pools):
   address, opening hours, lead time, booking horizon.
4. **Build the catalog**: product types (with attribute schema) → products →
   resources (each gets an inventory number + QR id), plus categories/sections.
5. **Public holidays**: set the region under *Admin → Block days / holiday
   setting*, then run `refresh_holidays` (and schedule it — see §6).
6. **QR stickers**: once `SHOP_BASE_URL` is the final public URL, print device
   labels under *Admin → Locations & inventory → QR labels*.

## 6. Scheduled jobs (cron)

> ⚠️ **Ausleihbar does not run these for you.** There is no built-in scheduler
> (no Celery/beat, no cron container in the compose stack). Each command only
> does something when it is invoked, so **an admin must register them on the
> host** — via cron (`crontab -e`), a systemd timer, or a Kubernetes CronJob —
> each calling `docker compose exec -T backend python manage.py <cmd>`.
> Ready-to-paste crontab lines are in **§7.2**.

**Schedule these on every install:** `release_cart_holds`,
`send_overdue_reminders`, `expire_uncollected_bookings`, `refresh_holidays`,
`purge_trash`. The remaining ones only matter once you use that feature.

| Command | Cadence | Purpose | If you don't schedule it |
|---|---|---|---|
| `release_cart_holds` | every 5–10 min | Free resources from expired carts (tidiness pass). | Availability already treats expired carts as free, but abandoned carts linger as open carts. |
| `send_overdue_reminders` | daily | Email borrowers about overdue pickups/returns. | No overdue reminders are ever sent. |
| `expire_uncollected_bookings` | daily | Cancel never-collected reservations whose lending period has fully passed (`--dry-run` to preview). | No-show reservations keep blocking their slots until a lender cancels them by hand. |
| `refresh_holidays` | monthly | Keep public-holiday blocks current across the booking horizon. | Holiday blocks aren't extended into newly-reachable future dates. |
| `review_defects` | daily/weekly | Nudge lenders about long-standing defective units. | Lenders get no defect-review reminders. |
| `notify_missing_products` | hourly | For an upcoming pickup whose unit is overdue (not returned), rebook it to a free unit or warn the borrower ahead of time (`--dry-run` to preview). Only fires for products with a `missing_notice_lead` set. | Borrowers aren't warned in advance when a device won't be back in time; no automatic rebooking of overdue units. |
| `purge_trash` | daily | Hard-delete catalog objects (products, resources, pools, …) that have sat in the trash past the retention window (default 30 days; configurable via `GET/PUT /api/manage/trash-setting/`; `--dry-run` to preview). | Soft-deleted objects stay restorable in the trash indefinitely and are never permanently removed. |
| `anonymize_inactive_users` | weekly | Anonymize accounts past the retention window (GDPR). Off until enabled — see below. | No automatic anonymization (only relevant once retention is switched on). |

**Data retention (`anonymize_inactive_users`).** Accounts that have had no
activity for a configurable window (default **3 years**) and have no open
lending process are anonymized: all personal data is scrubbed and the record is
kept only as a neutral placeholder (“Gelöschter Nutzer”) so device/booking
history survives. **Administrators are never touched; inactive lenders are.**
The feature is **off by default** — an admin turns it on (and sets the window)
under **Admin → People & access → Data retention**. The command no-ops while
disabled; run it manually with `--dry-run` (and `--force` to ignore the switch)
to preview:

```bash
docker compose exec backend python manage.py anonymize_inactive_users --dry-run --force
```

Other commands: `seed_demo` (demo data), `import_holidays` (one country/year),
`backfill_defects` (one-off data migration helper).

### 6.1 Other things an admin must switch on

Besides the cron jobs, a few capabilities are **inactive until someone turns
them on**. None of these happen automatically:

| Feature | State out of the box | How to activate |
|---|---|---|
| **Email sending (SMTP)** | Off — mails only print to the backend log | Set `EMAIL_BACKEND`/`EMAIL_HOST…` (§4.4). Until then, reservation, confirmation, overdue and cancellation notices reach no one. |
| **Back-channel logout** | Off | Enter the *Backchannel logout URL* `<API base>/oidc/backchannel-logout/` in the Keycloak client (§4.5); otherwise signing out of the SSO doesn't drop the local Ausleihbar session. |
| **Data retention (GDPR)** | Off | Enable it and set the window under *Admin → People & access → Data retention*, and schedule `anonymize_inactive_users` (§6). |
| **GitLab defect tickets** | Off | Opt-in **per pool** in the lending area (§4.7); leave blank to keep it off. |
| **Machine-translation pre-fill** | Off | Set `CONTENT_TRANSLATION_PROVIDER` (+ LibreTranslate URL/key) (§4.2). |
| **AI features** | Off | Set `AI_PROVIDER=litellm` (+ base URL/key/model) (§4.2). |
| **Public holidays** | Off | Pick the region under *Admin → Block days / holiday setting*, then run and schedule `refresh_holidays` (§5, §6). |

Per-pool notification toggles (**defect** and **cancellation** emails) are *on*
by default, but only actually send once SMTP is configured **and** the pool has
a contact email address.

## 7. Production deployment on Rocky Linux — step by step

This is a complete walk-through for a fresh **Rocky Linux 9** server, written so
you can follow it without prior Linux experience. Copy each command exactly.

**How it fits together (read once):** you install just one thing on the server —
**Docker**. Docker then downloads and runs all the moving parts as
*containers*: the database (**PostgreSQL**), the application (**Django**) and the
web server with HTTPS (**Caddy**). You do **not** install PostgreSQL or Caddy
yourself, and Caddy gets the HTTPS certificate automatically. Everything is
reached under one address, e.g. `https://ausleihbar.example.org`.

**Before you start you need:**

- A server running Rocky Linux 9 and a user that can run `sudo` (or the `root`
  user — then leave out the `sudo` in front of each command).
- A **domain name** (e.g. `ausleihbar.example.org`) you can create a DNS record
  for. HTTPS needs a real domain.
- The server's **public IP address**.

> Notation: lines starting with `sudo` are run in the server's terminal. In the
> `nano` text editor, save with **Ctrl+O** then **Enter**, and exit with
> **Ctrl+X**.

### Step 1 — Log in to the server

From your own computer:

```bash
ssh your-user@SERVER-IP        # e.g. ssh admin@203.0.113.10
```

### Step 2 — Update the system and install basic tools

```bash
sudo dnf -y update
sudo dnf -y install git nano dnf-plugins-core
```

### Step 3 — Install Docker

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo docker --version            # should print a version → Docker works
```

(Optional, so you can drop the `sudo` before `docker`: run
`sudo usermod -aG docker $USER`, then log out and back in. This guide keeps
`sudo` so it works either way.)

### Step 4 — Open the firewall for web traffic

Caddy needs port **80** (to obtain the certificate and redirect to HTTPS) and
**443** (HTTPS).

Rocky uses **firewalld**, but a minimal install may not have it. First install,
enable and start it (this is a no-op if it's already there):

```bash
sudo dnf -y install firewalld
sudo systemctl enable --now firewalld
```

Then open the two web ports and reload:

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

Confirm both services are now allowed:

```bash
sudo firewall-cmd --list-services      # should include 'http' and 'https'
```

> **Note:** Some servers (especially cloud VMs) don't run a host firewall at all
> and instead filter traffic with an external **security group / network
> firewall**. If `firewall-cmd` reports `FirewallD is not running` after the
> steps above — or you intentionally don't use firewalld — skip this step and
> make sure ports **80** and **443** are opened in your provider's firewall
> instead.

### Step 5 — Point your domain at the server (DNS)

At your DNS provider, create an **A record** for your domain pointing to the
server's public IP (and an **AAAA record** if you have IPv6). Then verify from
the server:

```bash
sudo dnf -y install bind-utils      # provides the 'dig' command
dig +short ausleihbar.example.org   # must print your server's IP
```

Do not continue until this returns the right IP — Let's Encrypt checks it.

### Step 6 — Download the application

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone <repo-url> ausleihbar
cd ausleihbar
```

(`<repo-url>` is the project's Git address. For a private repo you'll be asked
for credentials.)

### Step 7 — Create the configuration file

```bash
sudo cp .env.example .env
openssl rand -base64 48              # copy this output — it's your secret key
sudo nano .env
```

In `nano`, set at least the values below (replace every `...` and the example
domain; paste the secret key you just generated). Lines starting with `#` are
comments.

```dotenv
# Django
DJANGO_SECRET_KEY=PASTE-THE-GENERATED-SECRET-HERE
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=ausleihbar.example.org
CSRF_TRUSTED_ORIGINS=https://ausleihbar.example.org

# Pins the released image tag when pulling from GHCR instead of building from
# source (see Step 9). Leave unset to use `latest`.
# AUSLEIHBAR_VERSION=v1.0.0

# Public address of the site
SHOP_BASE_URL=https://ausleihbar.example.org

# VITE_API_BASE_URL is NOT needed here: it's baked into the SPA at build
# time only, and the production image/build never sets it, so the SPA
# always calls the API on its own origin (see §4.3) — correct behind Caddy.

# Canonical content language ("de" or "en"); leave at "de" for German-first.
CONTENT_DEFAULT_LANGUAGE=de

# Encrypts stored secrets at rest (e.g. the per-pool GitLab token). Optional but
# recommended: a dedicated, stable key kept in your backups. Generate one with
# `docker compose exec backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
# If omitted, a key is derived from DJANGO_SECRET_KEY (see §4.2).
# TOKEN_ENCRYPTION_KEY=PASTE-A-GENERATED-FERNET-KEY-HERE

# Optional creation caps; leave unset for unlimited (see §4.2).
# MAX_RESOURCES=
# MAX_PRODUCTS=
# MAX_USERS=

# Optional machine-translation pre-fill (issue #6). Leave provider unset to keep
# it off. To enable with an external LibreTranslate instance:
# CONTENT_TRANSLATION_PROVIDER=libretranslate
# LIBRETRANSLATE_URL=https://translate.example.org
# LIBRETRANSLATE_API_KEY=...
# After changing these, recreate the backend: docker compose -f docker-compose.prod.yml up -d backend

# Database — pick a long random password
POSTGRES_PASSWORD=change-this-to-a-strong-password

# Email (ask your mail admin for these; the From address must be allowed)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.org
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=Ausleihbar <ausleihbar@example.org>

# Login (OIDC) — your university identity provider. Either set OIDC_OP_ISSUER
# and let the app discover the rest, or set the individual endpoints (see §4.5).
# Register the redirect URI  https://ausleihbar.example.org/oidc/callback/  there.
OIDC_RP_CLIENT_ID=...
OIDC_RP_CLIENT_SECRET=...
OIDC_OP_ISSUER=https://idp.example.org/realms/your-realm
OIDC_ADMIN_GROUP=ausleihbar-admins
```

Save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**.

### Step 8 — Configure the web server (Caddy)

**How Caddy gets installed:** you don't install it with `dnf`. Caddy runs as a
Docker container from the official `caddy:2` image, which Docker downloads
automatically when you start the stack (Step 11). Its definition lives in
`docker-compose.prod.yml` (the `caddy` service), where it also opens ports 80
and 443 and stores its certificates in the `caddy_data` volume.

**Where the Caddyfile is:** the web server's config is a file called
`Caddyfile` in the project root you cloned in Step 6 — i.e.
`/opt/ausleihbar/Caddyfile`. The compose file mounts it **read-only into the
container** at `/etc/caddy/Caddyfile`, so you edit it on the host and Caddy picks
it up on (re)start — there is nothing to copy into the container by hand.

Open it and change two things: the domain on the line
`ausleihbar.example.org {` and the `email` near the top (used by Let's Encrypt
for expiry notices).

```bash
cd /opt/ausleihbar
sudo nano Caddyfile
```

You do **not** configure certificates by hand — Caddy requests and renews a free
HTTPS certificate automatically once the domain and ports are correct. After the
stack is running, apply later edits to the Caddyfile with
`sudo docker compose -f docker-compose.prod.yml restart caddy`.

### Step 9 — Choose how to get the app image

The `backend` image bakes in the built frontend (a multistage build — see
`Dockerfile`), so there's no separate frontend build step. Pick one:

- **Build from source** — Docker builds the SPA and the Django image itself:

  ```bash
  sudo docker compose -f docker-compose.prod.yml up -d --build
  ```

- **Pull a released image** — no local build, faster; set `AUSLEIHBAR_VERSION`
  in `.env` (e.g. `v1.0.0`), otherwise `latest` is used:

  ```bash
  sudo docker compose -f docker-compose.prod.yml pull
  sudo docker compose -f docker-compose.prod.yml up -d
  ```

Neither option needs `VITE_API_BASE_URL` set: the SPA calls its own origin by
default, which is correct since Caddy always serves the SPA and proxies the
API from the same domain (see §4.3).

Either way, Caddy ends up serving the SPA from the shared `frontend_data`
volume that the `backend` container populates on start. (Re-run whichever of
these you chose whenever you deploy a new version — see §7.3.)

### Step 10 — Allow the files under SELinux

Rocky Linux ships with SELinux enabled, which can stop a container from reading
files mounted from the host. Label the Caddyfile:

```bash
sudo chcon -Rt container_file_t Caddyfile
```

### Step 11 — Start everything

If you haven't already run one of the two commands from Step 9, run it now —
that both builds/pulls the image and starts every service in one go:

```bash
sudo docker compose -f docker-compose.prod.yml up -d --build   # build from source
# or: sudo docker compose -f docker-compose.prod.yml up -d     # after `pull`
```

This downloads PostgreSQL and Caddy, prepares the application image, runs the
database migrations, and starts all services. Caddy fetches the HTTPS
certificate (takes up to a minute). Watch the logs and look for Caddy obtaining
the certificate:

```bash
sudo docker compose -f docker-compose.prod.yml logs -f      # Ctrl+C to stop watching
```

Then open `https://ausleihbar.example.org` in a browser.

### Step 12 — Create the first administrator

```bash
sudo docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

Follow the prompts (username, email, password). You can now sign in at
`https://ausleihbar.example.org/admin/`. Next: sign in via your university login
(OIDC) once, grant roles, and create your first resource pool and catalog as in
§5. Schedule the maintenance jobs from §6 (example crontab in §7.2 below).

### Does it survive a server reboot?

Yes — the setup is reboot-safe by design:

- Docker starts at boot (`systemctl enable docker`, Step 3).
- Every service is set to `restart: unless-stopped`, so Docker brings the
  database, backend and Caddy back up automatically after a reboot (unless you
  had deliberately stopped them with `… down`).
- All state lives in persistent Docker volumes that survive reboots: the
  database (`postgres_data`), uploaded files (`media_data`) and the HTTPS
  certificates (`caddy_data`). On each start the backend re-applies migrations
  and re-collects static files automatically.
- The firewall rules were saved with `--permanent` (Step 4).

After a reboot the services may take a few seconds to settle (the backend waits
for the database via Docker's restart policy). To verify:

```bash
sudo reboot
# log back in once it returns, then:
cd /opt/ausleihbar
sudo docker compose -f docker-compose.prod.yml ps     # every service shows "running"
```

If you intentionally stopped the stack with `… down`, it stays down after a
reboot by design — start it again with `… up -d`.

### 7.1 Everyday commands

Run these from the `/opt/ausleihbar` folder:

```bash
P="sudo docker compose -f docker-compose.prod.yml"
$P ps                 # what is running
$P logs -f            # live logs (Ctrl+C to stop)
$P restart            # restart the app
$P down               # stop everything
$P up -d --build      # start / apply changes
```

### 7.2 Scheduled maintenance (cron)

The app does **not** schedule anything itself (see §6) — you set this up once on
the server. Install the periodic jobs with `sudo crontab -e` and add, for
example (these five cover a normal install):

```cron
30 6 * * *    cd /opt/ausleihbar && docker compose -f docker-compose.prod.yml exec -T backend python manage.py send_overdue_reminders
0  3 1 * *    cd /opt/ausleihbar && docker compose -f docker-compose.prod.yml exec -T backend python manage.py refresh_holidays
*/10 * * * *  cd /opt/ausleihbar && docker compose -f docker-compose.prod.yml exec -T backend python manage.py release_cart_holds
15 3 * * *    cd /opt/ausleihbar && docker compose -f docker-compose.prod.yml exec -T backend python manage.py expire_uncollected_bookings
30 3 * * *    cd /opt/ausleihbar && docker compose -f docker-compose.prod.yml exec -T backend python manage.py purge_trash
```

Add `review_defects`, `notify_missing_products`, and/or `anonymize_inactive_users`
(see §6) only if you use those features — e.g. for an hourly missing-product check:

```cron
0  * * * *    cd /opt/ausleihbar && docker compose -f docker-compose.prod.yml exec -T backend python manage.py notify_missing_products
```

Check that a job ran with `grep CRON /var/log/cron` (Rocky Linux).
Also review the one-time activation steps in **§6.1** (email/SMTP, back-channel
logout, holidays, …) — several features stay off until you enable them.

### 7.3 Updating to a new version

Build from source:

```bash
cd /opt/ausleihbar
sudo git pull
sudo docker compose -f docker-compose.prod.yml up -d --build    # build + migrations + restart automatically
```

Or pull a released image (no local build; set `AUSLEIHBAR_VERSION` in `.env`
to the version you want, e.g. `v1.1.0`):

```bash
cd /opt/ausleihbar
sudo docker compose -f docker-compose.prod.yml pull
sudo docker compose -f docker-compose.prod.yml up -d             # migrations + restart automatically
```

### 7.4 HTTPS certificates (Caddy), in plain terms

- Caddy obtains and **auto-renews** a free Let's Encrypt certificate for the
  domain in your `Caddyfile`. Nothing to do by hand. Requirements: ports **80
  and 443** reachable from the internet, correct **DNS** (Step 5), and a valid
  `email` in the `Caddyfile`.
- The certificates live in the `caddy_data` Docker volume — **back it up** so
  they survive a rebuild (otherwise Caddy just re-issues them, which is subject
  to Let's Encrypt rate limits).
- No public domain (internal-only host)? In `Caddyfile`, inside the site block,
  replace the certificate behaviour by adding a line `tls internal` — Caddy then
  uses its own local certificate authority instead of Let's Encrypt.

#### Bring your own certificate (e.g. HARICA) instead of Let's Encrypt

If your institution issues the certificate (HARICA, DFN, an internal CA …),
point Caddy at the files instead of using automatic HTTPS:

1. Put the two PEM files on the host, outside the repo so the **private key is
   never committed**, e.g. `/etc/ausleihbar/certs/`:
   - `ausleihbar.pem` — the server certificate **with its intermediate(s)**
     (leaf first, then the CA chain), PEM format.
   - `ausleihbar.key` (or `…_unverschluesselt.pem`) — the matching **private
     key**, PEM, **without a passphrase** (Caddy can't prompt for one).
   For one site block serving several domains, the certificate must list **all
   of them as SANs**.
2. Mount that directory into the Caddy container. `docker-compose.prod.yml`
   already has a (commented-as-optional) line for it — keep it as:
   ```yaml
   - /etc/ausleihbar/certs:/etc/caddy/certs:ro
   ```
3. In the `Caddyfile` site block, replace the automatic behaviour with a `tls`
   line pointing at the **container** paths (cert first, key second):
   ```
   tls /etc/caddy/certs/ausleihbar.pem /etc/caddy/certs/ausleihbar.key
   ```
4. Label the directory for SELinux (Rocky) so the container may read it:
   ```bash
   sudo chcon -Rt container_file_t /etc/ausleihbar/certs
   ```
5. Apply with `sudo docker compose -f docker-compose.prod.yml up -d` (or
   `restart caddy`). Renewal is **manual**: replace the files before they
   expire, then `restart caddy`. The global `email` is unused in this mode.

### 7.5 Backups & security checklist

- [ ] `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, real `DJANGO_ALLOWED_HOSTS`.
- [ ] `SHOP_BASE_URL`, `CSRF_TRUSTED_ORIGINS` and the OIDC redirect URL all on
      the real `https://` domain (`VITE_API_BASE_URL` is not needed — §4.3).
- [ ] Strong `POSTGRES_PASSWORD`; keep all secrets in `.env` (never commit it).
- [ ] Working SMTP with a `DEFAULT_FROM_EMAIL` your relay accepts.
- [ ] OIDC pointed at the institutional IdP; `/oidc/callback/` registered there.
- [ ] Regularly back up the `postgres_data`, `media_data` and `caddy_data`
      Docker volumes.
- [ ] Only ports 80/443 are open; the database and backend are not published.
- [ ] Confirmed the stack comes back automatically after `sudo reboot`.
