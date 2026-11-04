<!--
SPDX-License-Identifier: Apache-2.0
Copyright 2026 Universität Osnabrück (virtUOS)

Operator guide: Prometheus endpoint and Grafana. When gauges change
(backend/lending/metrics.py), keep the table below in sync.
-->

# Monitoring with Prometheus and Grafana

Ausleihbar exposes its inventory and usage figures as a **Prometheus
endpoint**. Scrape it with an existing Prometheus, chart it in Grafana, alert
on it or compare it with other services.

This guide is for whoever runs the server. The base installation is described
in [`INSTALL.md`](INSTALL.md).

## Overview

| | |
|---|---|
| **URL** | `https://<your-domain>/metrics` — exactly this path, no trailing slash, deliberately outside `/api/` |
| **Format** | Prometheus text format (`text/plain; version=0.0.4`) |
| **Protection** | Bearer token: header `Authorization: Bearer <METRICS_TOKEN>` |
| **Default** | **off** — while `METRICS_TOKEN` is unset the endpoint answers `404` |
| **Wrong or missing token** | `401` (with `WWW-Authenticate: Bearer`) |
| **Caching** | `Cache-Control: no-store`; every scrape counts fresh from the database |
| **Content** | aggregated counts only — no names, e-mail addresses, booking notes or IP addresses |

## 1. Enable the endpoint

1. Generate a long random token:

   ```bash
   openssl rand -hex 32
   ```

2. Add it to `.env` on the server (the template `.env.example` already
   contains the line, commented out):

   ```bash
   METRICS_TOKEN=<the generated token>
   ```

   `docker-compose.prod.yml` already forwards the variable to the `backend`
   container — nothing else to do there.

3. Recreate the backend container so it picks up the variable:

   ```bash
   cd /opt/ausleihbar
   sudo docker compose -f docker-compose.prod.yml up -d backend
   ```

4. Caddy must forward `/metrics` to the backend. The git-managed `Caddyfile`
   contains the block

   ```caddy
   handle /metrics {
   	reverse_proxy backend:8000
   }
   ```

   If the checkout on the server is older, `git pull` brings it in (see
   [`INSTALL.md`](INSTALL.md) §7.3 "Updating to a new version"). After any
   change to the Caddyfile on the host, relabel it on SELinux hosts (Rocky
   Linux) and recreate Caddy:

   ```bash
   cd /opt/ausleihbar
   sudo chcon -t container_file_t Caddyfile
   sudo docker compose -f docker-compose.prod.yml up -d --force-recreate caddy
   ```

   With **your own reverse proxy** instead of the bundled Caddy, forward
   exactly the path `/metrics` to the backend. `/metrics/` (trailing slash)
   is not the endpoint — it falls through to the web app.

   Without the forwarding, `/metrics` returns the web app's start page (HTML)
   instead of the metrics, and Prometheus reports a parse error.

5. Test:

   ```bash
   curl -s -H "Authorization: Bearer <token>" https://<your-domain>/metrics | head
   ```

   Expect text such as `# TYPE ausleihbar_pools gauge` and
   `ausleihbar_pools 3`. Without the header you must get `401`:

   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://<your-domain>/metrics
   ```

### Optional: additionally restrict access to the Prometheus server

The token already protects the endpoint. To also open it only for the
Prometheus server's IP address, replace the block in the `Caddyfile` with the
following (a deliberate local change — carry it across updates with
`git stash && git pull && git stash pop`, then relabel and recreate Caddy as
in step 4):

```caddy
handle /metrics {
	@not_prometheus not remote_ip 192.0.2.10/32
	respond @not_prometheus 403
	reverse_proxy backend:8000
}
```

(Replace `192.0.2.10` with the address of your Prometheus server.)

## 2. Configure Prometheus

Example `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: ausleihbar
    scheme: https
    metrics_path: /metrics
    scrape_interval: 5m        # values change slowly; 1–5 min is plenty
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/ausleihbar.token   # contains only the token
    static_configs:
      - targets: ["ausleihbar.example.org"]
```

Notes:

- Prefer `credentials_file` over putting the token into the YAML (make the
  file readable only by the Prometheus user).
- Every scrape runs a handful of grouped `COUNT` queries against the
  database. An interval in the minute range is sensible; scraping every few
  seconds gains nothing.
- After the change, reload Prometheus and check under *Status → Targets*
  that the target is `UP`.

## 3. The metrics

All metrics are **gauges** prefixed `ausleihbar_`. Each scrape reports the
state at that moment, counted from the database — Ausleihbar keeps no
counters in memory. Some gauges are **all-time totals** (they only grow,
except when data is deleted or anonymised away), the others are the
**current state** and go up and down.

### Inventory (current state)

| Metric | Labels | Meaning |
|---|---|---|
| `ausleihbar_pools` | — | Active resource pools |
| `ausleihbar_users` | — | User accounts (all, incl. inactive and anonymised) |
| `ausleihbar_products` | `use_type` | Live (not deleted) products by use type |
| `ausleihbar_product_sets` | — | Live product sets |
| `ausleihbar_resources` | `pool`, `status` | Live resources (items) by pool and status |

### Usage

Bookings never include carts (status `cart`), except for
`ausleihbar_carts_active`.

| Metric | Labels | Kind | Meaning |
|---|---|---|---|
| `ausleihbar_bookings` | `pool`, `status` | all-time total, split by current status | Bookings (excluding carts) by pool and status; the sum over all statuses only grows, a single status goes up and down as bookings move on |
| `ausleihbar_booking_items_handed_out` | `pool` | all-time total | Booking items ever handed out (`handed_out_at` set) |
| `ausleihbar_active_loans` | `pool` | current state | Booking items handed out and not yet returned |
| `ausleihbar_borrowers` | `pool` | all-time total | Distinct borrowers of submitted bookings |
| `ausleihbar_bookings_today` | `pool` | current state (today) | Non-cancelled bookings whose first appointment starts today (server's local date) |
| `ausleihbar_carts_active` | — | current state | Carts whose slot hold has not expired |

Label values:

- `pool`: the pool's short **`pool_id`** (e.g. `DL`), not its name. For
  bookings this is the booking's pool; for resources and booking items the
  item's pool. A legacy booking without a pool is labelled `pool=""`.
- `status` on `ausleihbar_resources`: `available`, `blocked`, `defective`,
  `retired`
- `status` on `ausleihbar_bookings`: `pending`, `confirmed`, `handed_out`,
  `returned`, `cancelled`
- `use_type`: `loan` (lending), `onsite` (on-site use)

Stable series: every **active** pool gets a sample in every pool-labelled
metric, and every status / use type is reported, with `0` where nothing
matches — so series don't appear and disappear between scrapes. An
**inactive or deleted pool** appears only while it still holds data (e.g.
old bookings or resources), under its `pool_id`.

Self-service items (on-site use without hand-out) are closed by the nightly
job with hand-out and return times set, so they count in
`ausleihbar_booking_items_handed_out` but never in `ausleihbar_active_loans`.

## 4. Useful queries (PromQL)

```promql
# Items currently lent out, per pool
ausleihbar_active_loans

# … and in total
sum(ausleihbar_active_loans)

# Defective items per pool
sum by (pool) (ausleihbar_resources{status="defective"})

# Items handed out in the last 7 days, per pool
delta(ausleihbar_booking_items_handed_out[7d])

# Share of the lendable stock currently out
sum(ausleihbar_active_loans)
  / sum(ausleihbar_resources{status=~"available|blocked|defective"})

# Bookings starting today, all pools
sum(ausleihbar_bookings_today)

# Cancellation rate (all time)
sum(ausleihbar_bookings{status="cancelled"}) / sum(ausleihbar_bookings)
```

These are gauges, so use `delta()` rather than `rate()`/`increase()` (which
assume counters and misread a drop as a reset). Values can drop, e.g. after
deletions or when a booking changes status; treat short-window deltas as an
overview. For exact figures the statistics page in the lending area reads
straight from the database.

## 5. Grafana

1. Add Prometheus as a data source (if not already present).
2. Build a dashboard with panels such as:
   - **Stat**: `ausleihbar_pools`, `ausleihbar_users`,
     `sum(ausleihbar_active_loans)`, `ausleihbar_carts_active`
   - **Time series**: `ausleihbar_active_loans` (stacked by `pool`)
   - **Bar chart**: `delta(ausleihbar_booking_items_handed_out[1d])` per pool
   - **Bar gauge**: `sum by (status) (ausleihbar_resources)`
   - **Table**: `ausleihbar_bookings` by `pool` and `status`
3. Add a dashboard variable `pool` (`label_values(ausleihbar_resources, pool)`)
   to filter by pool.
4. Pick a time range of weeks to a semester — most figures move over days,
   not minutes. `ausleihbar_active_loans` and `ausleihbar_bookings_today`
   are the ones worth watching within a day.

## 6. Privacy

The endpoint returns sums only. It contains no names, e-mail addresses,
usernames, booking notes, product titles, IDs or IP addresses; the only
labels are the pool's short `pool_id`, statuses and use types. With very
small pools a count can still hint at individual activity (e.g.
`ausleihbar_borrowers{pool="X"} 1`), so treat the scraped data like other
internal operational data. Keep the token out of public repositories and
tickets. The endpoint stores nothing, so the privacy page needs no change for
it.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `404` | `METRICS_TOKEN` not set, or the backend container not recreated (step 1.3) — or the URL has a trailing slash (`/metrics/`) |
| `401` | Wrong token, or header missing (`Authorization: Bearer …`, with a space) |
| HTML instead of metrics / parse error in Prometheus | `handle /metrics` missing from the `Caddyfile` or not forwarded by your own proxy (step 1.4); Caddy not recreated after `git pull` |
| Caddy fails to start after editing the Caddyfile | SELinux label lost — `sudo chcon -t container_file_t Caddyfile`, then recreate Caddy (step 1.4) |
| Target `DOWN`, TLS error | Check domain/certificate; is `scheme: https` set? |
| A pool's series vanished | The pool was deactivated or deleted and no longer holds data; inactive pools appear only while they hold data |
| Values stay at 0 | Fresh installation, or no bookings yet |
