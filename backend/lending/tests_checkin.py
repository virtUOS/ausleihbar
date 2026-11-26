# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for the item check-in data model and product setting."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product, Resource
from catalog.serializers import ProductManageSerializer

from .models import Booking, BookingItem
from .services import create_reservation, create_walkin_booking, submit_cart
from .tests import _make_product_with_resources

User = get_user_model()


def _make_checkin_product(count=2, suffix="", on=True):
    product, resources = _make_product_with_resources(count, suffix)
    product.lending_type = Product.LendingType.HOURS
    product.use_type = Product.UseType.ONSITE
    product.requires_handout = False
    product.checkin_required = on
    product.save()
    return product, resources


def _update(product, **data):
    ser = ProductManageSerializer(product, data=data, partial=True)
    valid = ser.is_valid()
    if valid:
        ser.save()
    return ser, valid


class CheckinModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("borrower", password="x")
        self.start = timezone.now() + timedelta(days=3)
        self.end = self.start + timedelta(hours=2)

    def _item(self, resource, start=None, booking=None):
        start = start or self.start
        booking = booking or Booking.objects.create(borrower=self.user)
        return BookingItem.objects.create(
            booking=booking, resource=resource,
            period=DateTimeTZRange(start, start + timedelta(hours=2)),
        )

    def test_item_snapshots_product_flag_on_create(self):
        product, (r1, _r2) = _make_checkin_product(on=True)
        self.assertTrue(self._item(r1).checkin_required)
        other, (o1,) = _make_checkin_product(1, "B", on=False)
        self.assertFalse(self._item(o1).checkin_required)

    def test_switching_on_does_not_touch_existing_items(self):
        product, (r1, _r2) = _make_checkin_product(on=False)
        item = self._item(r1)
        ser, valid = _update(product, checkin_required=True)
        self.assertTrue(valid, ser.errors)
        item.refresh_from_db()
        self.assertFalse(item.checkin_required)

    def test_switching_off_clears_unstarted_items(self):
        product, (r1, r2) = _make_checkin_product(on=True)
        started = self._item(r1, start=timezone.now() - timedelta(minutes=10))
        future = self._item(r2)
        self.assertTrue(started.checkin_required and future.checkin_required)
        ser, valid = _update(product, checkin_required=False)
        self.assertTrue(valid, ser.errors)
        started.refresh_from_db()
        future.refresh_from_db()
        self.assertTrue(started.checkin_required)
        self.assertFalse(future.checkin_required)

    def test_rebooking_keeps_flag(self):
        product, (r1, r2) = _make_checkin_product(on=True)
        item = self._item(r1)
        product.checkin_required = False
        product.save()
        item.resource = r2
        item.save()
        item.refresh_from_db()
        self.assertTrue(item.checkin_required)

    def test_submit_sets_submitted_at(self):
        product, (r1,) = _make_checkin_product(1, "A", on=False)
        _other, (r2,) = _make_checkin_product(1, "B", on=False)
        cart = create_reservation(
            self.user,
            [(r1, self.start, self.end), (r2, self.start, self.end)],
            status=Booking.Status.CART,
        )
        self.assertIsNone(cart.submitted_at)
        before = timezone.now()
        bookings = submit_cart(cart)
        self.assertEqual(len(bookings), 2)
        stamps = {b.submitted_at for b in bookings}
        self.assertEqual(len(stamps), 1)
        stamp = stamps.pop()
        self.assertIsNotNone(stamp)
        self.assertLessEqual(before, stamp)
        self.assertLess(stamp - before, timedelta(seconds=30))

    def test_walkin_sets_submitted_at(self):
        product, (r1,) = _make_checkin_product(1, "W", on=False)
        before = timezone.now()
        booking = create_walkin_booking(
            self.user, r1.resource_pool_id,
            [(product, self.start, self.end, r1)],
        )
        self.assertIsNotNone(booking.submitted_at)
        self.assertGreaterEqual(booking.submitted_at, before)
        self.assertLess(booking.submitted_at - before, timedelta(seconds=30))
        direct = create_reservation(self.user, [(r1, self.end, self.end + timedelta(hours=1))])
        self.assertIsNotNone(direct.submitted_at)


class CheckinProductSettingTests(TestCase):
    def test_checkin_requires_self_service_hourly(self):
        loan, _ = _make_product_with_resources(1, "L")
        loan.lending_type = Product.LendingType.HOURS
        loan.save()
        ser, valid = _update(loan, checkin_required=True)
        self.assertFalse(valid)
        self.assertIn("checkin_required", ser.errors)

        days, _ = _make_product_with_resources(1, "D")
        days.use_type = Product.UseType.ONSITE
        days.requires_handout = False
        days.save()
        ser, valid = _update(days, checkin_required=True)
        self.assertFalse(valid)
        self.assertIn("checkin_required", ser.errors)

        ok, _ = _make_checkin_product(1, "OK", on=False)
        ser, valid = _update(ok, checkin_required=True)
        self.assertTrue(valid, ser.errors)
        ok.refresh_from_db()
        self.assertTrue(ok.checkin_required)

    def test_release_minutes_range(self):
        product, _ = _make_checkin_product(1, "R")
        for bad in (4, 241):
            ser, valid = _update(product, checkin_release_minutes=bad)
            self.assertFalse(valid, bad)
            self.assertIn("checkin_release_minutes", ser.errors)
        for good in (5, 240):
            ser, valid = _update(product, checkin_release_minutes=good)
            self.assertTrue(valid, ser.errors)

    def test_product_losing_self_service_switches_off(self):
        product, _ = _make_checkin_product(1, "S")
        ser, valid = _update(product, requires_handout=True)
        self.assertTrue(valid, ser.errors)
        product.refresh_from_db()
        self.assertFalse(product.checkin_required)
