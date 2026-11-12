---
title: Installation
description: Run Ausleihbar at your own institution — Docker Compose, OIDC and configuration.
docs_include: true
---

# Installation

Ausleihbar is free software (Apache-2.0) and runs as a **Docker Compose
stack**: PostgreSQL, the Django backend and the React interface. Sign-in goes
through your institution's identity provider (OIDC, e.g. Keycloak).

!!! info "Source of this page"
    The following text is the installation and configuration guide from the
    repository
    ([`docs/INSTALL.md`](https://github.com/virtUOS/ausleihbar/blob/release/1.0/docs/INSTALL.md))
    and is pulled in from there on every website build.

--8<-- "docs/INSTALL.md:2"

## Monitoring (Prometheus)

Ausleihbar can expose inventory and usage figures (pools, items, bookings,
current loans) as a Prometheus endpoint `/metrics` — for dashboards in
Grafana, for example. The endpoint is off by default, is enabled with a token
(`METRICS_TOKEN`) and returns aggregated figures only, no personal data. The
guide
[`docs/monitoring.md`](https://github.com/virtUOS/ausleihbar/blob/release/1.0/docs/monitoring.md)
covers setup, metrics and example queries.
