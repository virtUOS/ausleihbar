---
title: Installation
description: Ausleihbar an der eigenen Einrichtung betreiben – Docker Compose, OIDC und Konfiguration.
docs_include: true
---

# Installation

Ausleihbar ist freie Software (Apache-2.0) und läuft als
**Docker-Compose-Stack**: PostgreSQL, Django-Backend und die React-Oberfläche.
Die Anmeldung läuft über den Identity Provider der Einrichtung (OIDC, z. B.
Keycloak).

!!! info "Quelle dieser Seite"
    Der folgende Text (englisch) ist die Installations- und
    Konfigurationsanleitung aus dem Repository
    ([`docs/INSTALL.md`](https://github.com/virtUOS/ausleihbar/blob/main/docs/INSTALL.md))
    und wird bei jedem Website-Build von dort übernommen.

--8<-- "docs/INSTALL.md:2"

## Monitoring (Prometheus)

Ausleihbar kann Bestands- und Nutzungszahlen (Pools, Gegenstände, Buchungen,
aktuelle Ausleihen) als Prometheus-Endpoint `/metrics` bereitstellen – etwa
für Dashboards in Grafana. Der Endpoint ist standardmäßig aus, wird über ein
Token (`METRICS_TOKEN`) freigeschaltet und liefert nur aggregierte Zahlen,
keine personenbezogenen Daten. Einrichtung, Kennzahlen und Beispielabfragen
beschreibt die Anleitung
[`docs/monitoring.md`](https://github.com/virtUOS/ausleihbar/blob/main/docs/monitoring.md)
(englisch).
