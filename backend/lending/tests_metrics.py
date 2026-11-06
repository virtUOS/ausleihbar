# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for the Prometheus gauges (``lending.metrics``, served at ``/metrics``)."""
import re
from datetime import datetime, time, timedelta

from basicbar_integrations.metrics import Gauges
from django.contrib.auth import get_user_model
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Product, ProductSet, ProductType, Resource, ResourcePool

from . import metrics
from .models import Booking, BookingItem

User = get_user_model()

_SAMPLE = re.compile(r"^([a-z_]+)(?:\{(.*)\})? (\S+)$")


def _parse(body):
    """``{(name, frozenset(labels)): value}`` from a Prometheus text body."""
    samples = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        name, raw_labels, value = _SAMPLE.match(line).groups()
        labels = frozenset(re.findall(r'(\w+)="([^"]*)"', raw_labels or ""))
        samples[(name, labels)] = float(value)
    return samples


def _day_range(day, days=1):
    start = timezone.make_aware(datetime.combine(day, time(10)))
    return DateTimeTZRange(start, start + timedelta(days=days))


class MetricsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.p1 = ResourcePool.objects.create(name="Pool 1", pool_id="P1")
        cls.p2 = ResourcePool.objects.create(name="Pool 2", pool_id="P2")
        ResourcePool.objects.create(name="Closed", pool_id="P3", is_active=False)
        ptype = ProductType.objects.create(name="Camera")
        cls.loan = Product.objects.create(product_type=ptype, title="Cam")
        Product.objects.create(product_type=ptype, title="Room",
                               use_type=Product.UseType.ONSITE)
        Product.objects.create(product_type=ptype, title="Gone").soft_delete()
        ProductSet.objects.create(name="Kit", resource_pool=cls.p1)
        ProductSet.objects.create(name="Old kit", resource_pool=cls.p1).soft_delete()

        def res(pool, n, status=Resource.Status.AVAILABLE):
            return Resource.objects.create(
                product=cls.loan, resource_pool=pool, status=status,
                inventory_number=f"{pool.pool_id}-{n}", qr_code_id=f"QR-{pool.pool_id}-{n}",
            )

        r1a, r1b = res(cls.p1, 1), res(cls.p1, 2)
        res(cls.p1, 3, Resource.Status.DEFECTIVE)
        res(cls.p1, 4).soft_delete()
        r2a = res(cls.p2, 1)
        res(cls.p2, 2, Resource.Status.RETIRED)

        cls.borrower = User.objects.create_user(
            username="metrics-borrower", email="borrower@example.org")
        other = User.objects.create_user(username="metrics-other", email="other@example.org")

        def booking(user, pool, status, **kw):
            return Booking.objects.create(borrower=user, resource_pool=pool, status=status, **kw)

        # P1: confirmed booking starting today.
        b = booking(cls.borrower, cls.p1, Booking.Status.CONFIRMED)
        BookingItem.objects.create(booking=b, resource=r1a, period=_day_range(today))
        # P1: handed-out (active loan), started yesterday.
        b = booking(other, cls.p1, Booking.Status.HANDED_OUT)
        BookingItem.objects.create(booking=b, resource=r1b,
                                   period=_day_range(today - timedelta(days=1), 3),
                                   handed_out_at=timezone.now())
        # P2: returned item.
        b = booking(cls.borrower, cls.p2, Booking.Status.RETURNED)
        BookingItem.objects.create(booking=b, resource=r2a, is_active=False,
                                   period=_day_range(today - timedelta(days=10)),
                                   handed_out_at=timezone.now() - timedelta(days=10),
                                   returned_at=timezone.now() - timedelta(days=9))
        # P2: cancelled booking starting today (not counted in bookings_today).
        b = booking(other, cls.p2, Booking.Status.CANCELLED)
        BookingItem.objects.create(booking=b, resource=r2a, is_active=False,
                                   period=_day_range(today))
        # Legacy booking without a pool.
        booking(other, None, Booking.Status.PENDING)
        # Carts: one active, one expired.
        booking(cls.borrower, None, Booking.Status.CART,
                expires_at=timezone.now() + timedelta(minutes=20))
        booking(other, cls.p1, Booking.Status.CART,
                expires_at=timezone.now() - timedelta(minutes=5))

    def _samples(self):
        gauges = Gauges()
        metrics.collect(gauges)
        return _parse(gauges.render())

    def _get(self, samples, name, **labels):
        return samples[(name, frozenset(labels.items()))]

    def test_inventory_gauges(self):
        s = self._samples()
        self.assertEqual(self._get(s, "ausleihbar_pools"), 2)
        self.assertEqual(self._get(s, "ausleihbar_users"), 2)
        self.assertEqual(self._get(s, "ausleihbar_products", use_type="loan"), 1)
        self.assertEqual(self._get(s, "ausleihbar_products", use_type="onsite"), 1)
        self.assertEqual(self._get(s, "ausleihbar_product_sets"), 1)
        r = "ausleihbar_resources"
        self.assertEqual(self._get(s, r, pool="P1", status="available"), 2)
        self.assertEqual(self._get(s, r, pool="P1", status="defective"), 1)
        self.assertEqual(self._get(s, r, pool="P1", status="retired"), 0)
        self.assertEqual(self._get(s, r, pool="P2", status="available"), 1)
        self.assertEqual(self._get(s, r, pool="P2", status="retired"), 1)
        # The inactive pool has no resources, so no series.
        self.assertNotIn((r, frozenset({("pool", "P3"), ("status", "available")})), s)

    def test_usage_gauges(self):
        s = self._samples()
        b = "ausleihbar_bookings"
        self.assertEqual(self._get(s, b, pool="P1", status="confirmed"), 1)
        self.assertEqual(self._get(s, b, pool="P1", status="handed_out"), 1)
        self.assertEqual(self._get(s, b, pool="P2", status="returned"), 1)
        self.assertEqual(self._get(s, b, pool="P2", status="cancelled"), 1)
        self.assertEqual(self._get(s, "ausleihbar_booking_items_handed_out", pool="P1"), 1)
        self.assertEqual(self._get(s, "ausleihbar_booking_items_handed_out", pool="P2"), 1)
        self.assertEqual(self._get(s, "ausleihbar_active_loans", pool="P1"), 1)
        self.assertEqual(self._get(s, "ausleihbar_active_loans", pool="P2"), 0)
        self.assertEqual(self._get(s, "ausleihbar_borrowers", pool="P1"), 2)
        self.assertEqual(self._get(s, "ausleihbar_borrowers", pool="P2"), 2)
        self.assertEqual(self._get(s, "ausleihbar_bookings_today", pool="P1"), 1)
        self.assertEqual(self._get(s, "ausleihbar_bookings_today", pool="P2"), 0)

    def test_carts_active_excludes_expired(self):
        self.assertEqual(self._get(self._samples(), "ausleihbar_carts_active"), 1)

    def test_booking_without_pool_labelled_empty(self):
        s = self._samples()
        self.assertEqual(self._get(s, "ausleihbar_bookings", pool="", status="pending"), 1)
        self.assertEqual(self._get(s, "ausleihbar_bookings", pool="", status="confirmed"), 0)
        self.assertEqual(self._get(s, "ausleihbar_borrowers", pool=""), 1)

    def test_no_pool_series_without_poolless_bookings(self):
        Booking.objects.filter(resource_pool=None).exclude(status=Booking.Status.CART).delete()
        s = self._samples()
        self.assertFalse([k for k in s if k[0] == "ausleihbar_bookings" and ("pool", "") in k[1]])

    def test_soft_deleted_not_counted(self):
        s = self._samples()
        total = sum(v for (name, _l), v in s.items() if name == "ausleihbar_resources")
        self.assertEqual(total, Resource.objects.count())
        self.assertEqual(total, 5)
        self.assertEqual(self._get(s, "ausleihbar_product_sets"), 1)
        self.assertEqual(sum(v for (name, _l), v in s.items()
                             if name == "ausleihbar_products"), 2)

    def test_all_status_values_present(self):
        s = self._samples()
        for pool in ("P1", "P2"):
            for status in Resource.Status.values:
                self.assertIn(
                    ("ausleihbar_resources",
                     frozenset({("pool", pool), ("status", status)})), s)
            for status in Booking.Status.values:
                key = ("ausleihbar_bookings", frozenset({("pool", pool), ("status", status)}))
                if status == Booking.Status.CART:
                    self.assertNotIn(key, s)
                else:
                    self.assertIn(key, s)

    def test_bookings_today_local_midnight_edge(self):
        today = timezone.localdate()
        res = Resource.objects.get(inventory_number="P2-1")
        spare = Resource.objects.create(
            product=self.loan, resource_pool=self.p2,
            inventory_number="P2-9", qr_code_id="QR-P2-9")

        def at(day, hour, minute):
            start = timezone.make_aware(datetime.combine(day, time(hour, minute)))
            return DateTimeTZRange(start, start + timedelta(minutes=20))

        # 00:30 local today (the previous day in UTC) counts.
        b = Booking.objects.create(borrower=self.borrower, resource_pool=self.p2,
                                   status=Booking.Status.CONFIRMED)
        BookingItem.objects.create(booking=b, resource=res, period=at(today, 0, 30))
        # 23:30 local yesterday does not.
        b = Booking.objects.create(borrower=self.borrower, resource_pool=self.p2,
                                   status=Booking.Status.CONFIRMED)
        BookingItem.objects.create(booking=b, resource=res,
                                   period=at(today - timedelta(days=1), 23, 30))
        # Earliest over all items: an inactive item today + an active one
        # tomorrow counts for today.
        b = Booking.objects.create(borrower=self.borrower, resource_pool=self.p2,
                                   status=Booking.Status.CONFIRMED)
        BookingItem.objects.create(booking=b, resource=spare, is_active=False,
                                   period=at(today, 12, 0))
        BookingItem.objects.create(booking=b, resource=spare,
                                   period=at(today + timedelta(days=1), 9, 0))
        self.assertEqual(
            self._get(self._samples(), "ausleihbar_bookings_today", pool="P2"), 2)

    def test_inactive_pool_with_data_is_emitted(self):
        s = self._samples()
        # No data yet: no P3 series anywhere.
        self.assertFalse([k for k in s if ("pool", "P3") in k[1]])
        p3 = ResourcePool.all_objects.get(pool_id="P3")
        Resource.objects.create(product=self.loan, resource_pool=p3,
                                inventory_number="P3-1", qr_code_id="QR-P3-1")
        Booking.objects.create(borrower=self.borrower, resource_pool=p3,
                               status=Booking.Status.RETURNED)
        s = self._samples()
        r = "ausleihbar_resources"
        self.assertEqual(self._get(s, r, pool="P3", status="available"), 1)
        self.assertEqual(self._get(s, r, pool="P3", status="defective"), 0)
        self.assertEqual(self._get(s, "ausleihbar_bookings", pool="P3", status="returned"), 1)
        self.assertEqual(self._get(s, "ausleihbar_borrowers", pool="P3"), 1)
        # Gauges without P3 data stay without a P3 sample.
        self.assertNotIn(("ausleihbar_active_loans", frozenset({("pool", "P3")})), s)
        self.assertEqual(self._get(s, "ausleihbar_pools"), 2)

    def test_query_budget(self):
        with self.assertNumQueries(9):
            metrics.collect(Gauges())

    @override_settings(METRICS_TOKEN="t0k")
    def test_body_has_no_personal_data(self):
        response = self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer t0k")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("# TYPE ausleihbar_resources gauge", body)
        for secret in ("metrics-borrower", "borrower@example.org",
                       "metrics-other", "other@example.org"):
            self.assertNotIn(secret, body)
