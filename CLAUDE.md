# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project
**Ausleihbar** — a university device lending system (catalog of products,
physical resources, lending rules, locations).

## Language convention
The codebase is written in **English**: all variables, models, database
tables, API endpoints and comments use English names. (User-facing UI text
may be localized later.) Keep this consistent in all new code.

## Tech stack
- **Database:** PostgreSQL 16
- **Backend:** Django 5 (Python 3.12) + Django REST Framework. Apps: `accounts`
  (custom `User`, roles, `PoolMembership`), `catalog` (products, resources,
  grouping), `lending` (the heart — booking engine, currently a skeleton),
  `tenancy` (skeleton), `common` (shared base models). `AUTH_USER_MODEL = accounts.User`.
- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS v3
- **Auth:** OIDC via Keycloak (`mozilla-django-oidc`); local dev Keycloak runs
  in Compose. Django `ModelBackend` stays as a local fallback (admin superuser).
- **Runtime:** Docker Compose, run via **colima** (no Docker Desktop on this machine)

## Running the project
```bash
colima start                  # start the container VM (needed after a reboot)
docker compose up -d          # start db + backend + frontend
docker compose logs -f backend
docker compose down           # stop everything
```
Ports:
- Frontend: http://localhost:5173
- Backend / Django admin: **http://localhost:8001**/admin/ (host 8001 → container 8000)
- Keycloak (OIDC): http://localhost:8080 (admin/admin; realm `ausleihbar`, demo user `demo`/`demo`)
- PostgreSQL: localhost:5432

OIDC login flow: visit `http://localhost:8001/oidc/authenticate/`. The browser
reaches Keycloak at `localhost:8080`; the backend reaches it via
`host.docker.internal:8080` (keeps the issuer consistent). Check session with
`GET /api/whoami/`.

Back-channel logout: when a user signs out of the SSO, the IdP POSTs a signed
`logout_token` to `POST /oidc/backchannel-logout/` (`accounts.oidc`), which
verifies it and drops that user's local sessions. Enable it in the Keycloak
client's "Backchannel logout URL" (e.g. `http://host.docker.internal:8001/oidc/backchannel-logout/`).

> Host port 8000 is occupied by an unrelated local process, so the backend is
> mapped to host port **8001**. Do not change this without checking.

### Common backend commands (run inside the container)
```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py test
```

## Domain model
Catalog models live in `backend/catalog/models.py`; users in `backend/accounts/models.py`.
- **accounts.User** — custom user (`AbstractUser`); OIDC `subject`,
  `is_self_registered`, `verified_at`, `claims` (login claim snapshot). Roles:
  Admin via `is_staff`/`is_superuser`, lender via `PoolMembership`, borrower =
  any authenticated user (ADR-0002). Admin role/pool management under
  `/api/manage/users/`.
- **accounts.AccessGroup** — pool eligibility (ADR-0007, concept §3.4): manual
  `members` + claim matching (`claim_key`/`claim_values`) grant access to its
  `pools`. A pool with no group is open to all; otherwise only members (plus the
  pool's lenders/admins) may see and book it. Enforced centrally via
  `accounts.eligibility.eligible_pool_ids` / `visible_products`.
- **accounts.Strike / StrikeSetting** — strikes (concept §7.3): lenders issue
  with a reason (via a booking they manage), admins delete; pool-wide, expire
  after `strike_expiry_days`. Reaching a configurable `thresholds` step suspends
  the account (`User.blocked_until` / `blocked_permanently`, `is_blocked()`);
  blocked users can't add to cart or submit. Logic in `accounts.strikes`;
  endpoints `/api/manage/strikes/`, `…/users/<id>/unblock/`, `…/strike-setting/`.
- **ProductType** — template with a JSON `attribute_schema` (dynamic
  attributes with type + default + `visible` / `required` flags).
- **Product** — catalog entry; FK to `ProductType`; `title`, `LendingType`
  (hours/days), optional `min_duration` / `max_duration`, optional `return_info`
  (lender-only guidance shown in the return dialog, concept §6.3). See ADR-0001
  for why this is an FK and not model inheritance. `complementary_products`
  (#23) is a symmetric self-M2M of curated "complementary devices"
  ("Ergänzende Geräte"; linking A to B also links B to A), ordered per-product
  via `complementary_order`; managed in the Verleihtheke product form, shown
  on the product page with each complement's eligible pools.
- **Resource** — one physical device/room; FK to `Product` + `ResourcePool`;
  `Status` (available/blocked/defective/retired), human-readable pool-scoped
  `inventory_number`, `qr_code_id`. Marking defective (concept §3.6) runs
  `lending.services.mark_resource_defective`: upcoming bookings are rebooked to
  free units of the same product/pool, else the borrower is notified; the
  `review_defects` command nudges lenders about long-standing defects. Also
  carries `serial_number`, `storage_location`, procurement/warranty/value fields.
  The `import_leihs` command (catalog) imports inventory from a leihs CSV export
  (models→Product, items→Resource); inventory-only, never reads personal columns
  (see `docs/leihs-import.md`).
- **ResourcePool** — physical location with `opening_hours`, lead time,
  `max_booking_months` (booking horizon, default 24), default durations, contact
  info, `is_active`.
- **Category** — M2M to `Product`.
- **Section** — M2M to `Category` ("Sparte"; renamed from `Department`, ADR-0003).
- **ProductSet** — M2M to `Product` (a list of products often lent together).
- **lending.Block** — a blocked time range (Sperrtag), scoped system-wide or to
  a pool/product/resource; managed via `/api/manage/blocks/` (admins see all,
  lenders their pools). **lending.HolidaySetting** — singleton region (country +
  subdivision); `refresh_holidays` loads public holidays as system-wide blocks
  across the longest booking horizon (concept §3.5; `manage/holiday-setting/` +
  `refresh_holidays` command).
- **lending.Booking / BookingItem** — a `Booking` with status `cart` is the
  shopping cart: adding a product allocates a free `Resource` and holds it via
  an active `BookingItem` until `expires_at`. The hold (renewed on every cart
  action) lasts `CartSetting.hold_minutes` (singleton, default 30, configurable
  via `manage/cart-setting/`). Availability treats expired carts as free; the
  `release_cart_holds` command cancels them as a periodic tidiness pass. The
  `expire_uncollected_bookings` command cancels never-collected reservations
  once their whole lending period has passed (frees the held slots; keeps
  history) — `lending.services.cancel_uncollected_bookings`. On submit, every
  reservation is single-pool (`resource_pool`); multi-pool carts are split
  (shared `checkout_id`), lenders act only on their pools' reservations, and
  confirmation mails are combined per order or held until
  `NotificationSetting.confirmation_send_time` and sent as partial confirmations
  (`lending.confirmations`, `send_confirmation_mails`).

## Documentation
- **Full product concept:** `docs/concept.md` — read it when working on
  features, business rules, or workflows.
- **Design decisions:** `docs/decisions/` (ADRs) — read the relevant ADR
  before changing an established design; add a new ADR for new decisions.
- **Data import/export:** `docs/data-transfer.md` — the admin ZIP round-trip
  (structure + inventory + media) implemented in `catalog/transfer.py`.
- **Design context:** `PRODUCT.md` (strategy: users, personality,
  anti-references, a11y target) and `DESIGN.md` (visual contract: honey-gold
  accent on warm neutrals, component vocabulary, motion & a11y rules) — read
  both before styling UI; tokens live in `frontend/tailwind.config.js`.

## UI conventions
- **Reuse UI elements wherever possible and sensible.** Before building a new
  widget, check for an existing component and extend it (e.g. with optional
  props) instead of duplicating. Established building blocks include the
  booking calendars (`BookingCalendar` / `HourlyBookingCalendar`, both accept
  data-source props so they work for products, sets and the lending desk),
  `MonthCalendar`, `ReorderControls`, `SortToggle`, `ImageCropField` and the
  `Status` helpers. New shared widgets belong in `frontend/src/components/`.

## Workflow expectations
- After a code change, prefer running `/code-review` and verifying behavior
  with `/verify` or `/run` before considering it done.
- New models should come with a migration, an admin registration in the
  owning app's `admin.py` and at least a basic test in its `tests.py`.
- Migrations run inside the container (see commands above), not on the host.
