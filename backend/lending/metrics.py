# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Prometheus gauges for the ``/metrics`` endpoint (``common.views.MetricsView``).

Aggregates only — no names, e-mails, notes or ids leave this module; the pool
label is the human-readable ``ResourcePool.pool_id``. Every series is built
from grouped ``COUNT`` queries (nine in total, no per-row loops). Status and
use-type values are zero-filled from the model choices and every active pool
gets a sample, so series don't appear and disappear between scrapes. Data of
an inactive or trashed pool is still emitted (under its ``pool_id``) as long
as it exists; a booking without a pool (legacy) is labelled ``pool=""``.
"""
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Min, OuterRef, Q, Subquery
from django.db.models.functions import Lower
from django.utils import timezone

from catalog.models import Product, ProductSet, Resource, ResourcePool

from .models import Booking, BookingItem

_BOOKING_STATUSES = [s for s in Booking.Status.values if s != Booking.Status.CART]


def _by(qs, *fields, **aggregates):
    """``{(field values…): count}`` (or the named aggregates) grouped by ``fields``.

    ``order_by()`` first so ``Meta.ordering`` doesn't leak into ``GROUP BY``.
    """
    aggregates = aggregates or {"n": Count("id")}
    rows = qs.order_by().values(*fields).annotate(**aggregates)
    if list(aggregates) == ["n"]:
        return {tuple(r[f] for f in fields): r["n"] for r in rows}
    return {tuple(r[f] for f in fields): {k: r[k] for k in aggregates} for r in rows}


def _today_bounds():
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time.min))
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    return start, end


def collect(gauges):
    now = timezone.now()
    start, end = _today_bounds()

    # Pool ids → labels (all rows, so data of inactive/trashed pools keeps a label).
    pools = list(
        ResourcePool.all_objects.order_by("pool_id")
        .values_list("id", "pool_id", "is_active", "deleted_at")
    )
    label = {pk: pool_id for pk, pool_id, _active, _deleted in pools}
    label[None] = ""
    active = [pk for pk, _pid, is_active, deleted in pools if is_active and deleted is None]

    def per_pool(counts):
        """One sample per active pool (zero-filled) plus any other pool with data."""
        keys = list(active) + [pk for pk in counts if pk not in active]
        return [({"pool": label[pk]}, counts.get(pk, 0)) for pk in keys]

    def per_pool_status(counts, statuses):
        """Every status for every active pool, plus any other pool with data."""
        keys = list(active) + sorted(
            {pk for pk, _s in counts if pk not in active}, key=lambda pk: label[pk]
        )
        return [
            ({"pool": label[pk], "status": s}, counts.get((pk, s), 0))
            for pk in keys for s in statuses
        ]

    # --- Inventory -----------------------------------------------------------
    gauges.gauge("ausleihbar_pools", "Active resource pools.", value=len(active))
    gauges.gauge(
        "ausleihbar_users", "User accounts (all, incl. inactive and anonymised).",
        value=get_user_model().objects.count(),
    )
    products = _by(Product.objects.all(), "use_type")
    gauges.gauge(
        "ausleihbar_products", "Live products by use type.",
        labels=[({"use_type": u}, products.get((u,), 0)) for u in Product.UseType.values],
    )
    gauges.gauge(
        "ausleihbar_product_sets", "Live product sets.", value=ProductSet.objects.count(),
    )
    resources = _by(Resource.objects.all(), "resource_pool_id", "status")
    gauges.gauge(
        "ausleihbar_resources", "Live resources (items) by pool and status.",
        labels=per_pool_status(resources, Resource.Status.values),
    )

    # --- Usage ---------------------------------------------------------------
    submitted = Booking.objects.exclude(status=Booking.Status.CART)
    bookings = _by(submitted, "resource_pool_id", "status")
    gauges.gauge(
        "ausleihbar_bookings", "Bookings (excluding carts) by pool and status.",
        labels=per_pool_status(bookings, _BOOKING_STATUSES),
    )

    items = _by(
        BookingItem.objects.filter(handed_out_at__isnull=False),
        "resource__resource_pool_id",
        handed_out=Count("id"),
        active=Count("id", filter=Q(returned_at__isnull=True)),
    )
    gauges.gauge(
        "ausleihbar_booking_items_handed_out",
        "Booking items ever handed out, by pool.",
        labels=per_pool({pk: v["handed_out"] for (pk,), v in items.items()}),
    )
    gauges.gauge(
        "ausleihbar_active_loans",
        "Booking items handed out and not yet returned, by pool.",
        labels=per_pool({pk: v["active"] for (pk,), v in items.items()}),
    )

    first_start = (
        BookingItem.objects.filter(booking=OuterRef("pk")).order_by()
        .values("booking").annotate(first=Min(Lower("period"))).values("first")
    )
    per_booking_pool = _by(
        submitted.annotate(first_start=Subquery(first_start)),
        "resource_pool_id",
        borrowers=Count("borrower_id", distinct=True),
        today=Count("id", filter=Q(first_start__gte=start, first_start__lt=end)
                    & ~Q(status=Booking.Status.CANCELLED)),
    )
    gauges.gauge(
        "ausleihbar_borrowers", "Distinct borrowers of submitted bookings, by pool.",
        labels=per_pool({pk: v["borrowers"] for (pk,), v in per_booking_pool.items()}),
    )
    gauges.gauge(
        "ausleihbar_bookings_today",
        "Non-cancelled bookings whose first appointment starts today, by pool.",
        labels=per_pool({pk: v["today"] for (pk,), v in per_booking_pool.items()}),
    )

    gauges.gauge(
        "ausleihbar_carts_active", "Carts whose slot hold has not expired.",
        value=Booking.objects.filter(status=Booking.Status.CART, expires_at__gt=now).count(),
    )
