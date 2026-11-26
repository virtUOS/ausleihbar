# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for the item check-in data model and product setting."""
from datetime import datetime, time, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase
from django.utils import timezone

from catalog.models import Product, Resource
from catalog.serializers import ProductManageSerializer

from . import checkin
from .models import Booking, BookingItem
from .services import (
    _close_self_service_item,
    allocate_resource,
    complete_self_service_items,
    create_reservation,
    create_walkin_booking,
    end_self_service_use_error,
    submit_cart,
)
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


class CheckinRuleTests(TestCase):
    """Check-in window, release deadline, release job and completion (§6.3)."""

    def setUp(self):
        self.user = User.objects.create_user(
            "rules", password="x", email="rules@example.org"
        )
        self.day = (timezone.localtime() + timedelta(days=3)).date()
        self.product, (self.r1, self.r2) = _make_checkin_product(2, "CR")

    def _at(self, hour, minute=0):
        return timezone.make_aware(datetime.combine(self.day, time(hour, minute)))

    def _item(self, *, start=None, end=None, resource=None, status=None,
              submitted=None, booking=None):
        start = start or self._at(10)
        end = end or start + timedelta(hours=1)
        if booking is None:
            booking = Booking.objects.create(
                borrower=self.user,
                status=status or Booking.Status.CONFIRMED,
                submitted_at=submitted or start - timedelta(days=1),
            )
        return BookingItem.objects.create(
            booking=booking, resource=resource or self.r1,
            period=DateTimeTZRange(start, end),
        )

    def test_deadline_uses_later_of_start_and_submit(self):
        late = self._item(submitted=self._at(10, 20))
        self.assertEqual(checkin.deadline(late), self._at(10, 50))
        early = self._item(resource=self.r2, submitted=self._at(9))
        self.assertEqual(checkin.deadline(early), self._at(10, 30))

    def test_deadline_clamped_to_period_end(self):
        item = self._item(submitted=self._at(10, 50))
        self.assertEqual(checkin.deadline(item), self._at(11))
        self.assertIsNone(checkin.checkin_error(item, self._at(10, 59)))
        self.assertEqual(checkin.checkin_error(item, self._at(11, 10)), "too_late")
        self.assertEqual(checkin.release_due_items(now=self._at(11, 1)), 1)
        item.refresh_from_db()
        self.assertIsNotNone(item.released_at)
        self.assertFalse(item.is_active)

    def test_checkin_at_10_59_before_clamped_deadline(self):
        item = self._item(submitted=self._at(10, 50))
        done = checkin.check_in(item, now=self._at(10, 59))
        self.assertEqual(done.checked_in_at, self._at(10, 59))

    def test_deadline_falls_back_to_created_at(self):
        item = self._item()
        Booking.objects.filter(pk=item.booking_id).update(
            submitted_at=None, created_at=self._at(10, 10)
        )
        item = BookingItem.objects.select_related("booking").get(pk=item.pk)
        self.assertEqual(checkin.deadline(item), self._at(10, 40))

    def test_window_opens_15_minutes_early(self):
        item = self._item()
        self.assertEqual(checkin.checkin_error(item, self._at(9, 44)), "too_early")
        with self.assertRaisesMessage(ValueError, "too_early"):
            checkin.check_in(item, now=self._at(9, 44))
        self.assertIsNone(checkin.checkin_error(item, self._at(9, 45)))
        done = checkin.check_in(item, now=self._at(9, 45))
        self.assertEqual(done.checked_in_at, self._at(9, 45))
        self.assertEqual(checkin.checkin_error(done, self._at(9, 50)), "already")

    def test_checkin_errors(self):
        item = self._item()
        self.assertEqual(checkin.checkin_error(item, self._at(10, 30)), "too_late")
        plain, (p1,) = _make_checkin_product(1, "PL", on=False)
        unflagged = self._item(resource=p1)
        self.assertEqual(
            checkin.checkin_error(unflagged, self._at(10)), "not_required"
        )
        cancelled = self._item(resource=self.r2, status=Booking.Status.CANCELLED)
        self.assertEqual(checkin.checkin_error(cancelled, self._at(10)), "inactive")

    def test_checkin_needs_confirmed_booking(self):
        item = self._item(status=Booking.Status.PENDING)
        self.assertEqual(checkin.checkin_error(item, self._at(10)), "not_confirmed")

    def test_state_sequence(self):
        item = self._item()
        self.assertEqual(checkin.state(item, self._at(9)), "upcoming")
        self.assertEqual(checkin.state(item, self._at(9, 50)), "open")
        self.assertEqual(checkin.state(item, self._at(10, 5)), "late")
        self.assertEqual(checkin.late_minutes(item, self._at(10, 5)), 5)
        self.assertEqual(checkin.late_minutes(item, self._at(9, 50)), 0)
        item = checkin.check_in(item, now=self._at(10, 5))
        self.assertEqual(checkin.state(item, self._at(10, 6)), "checked_in")
        plain, (p1,) = _make_checkin_product(1, "ST", on=False)
        self.assertIsNone(checkin.state(self._item(resource=p1), self._at(10)))

    def test_release_due_items(self):
        item = self._item(end=self._at(12))
        now = self._at(10, 31)
        self.assertEqual(checkin.release_due_items(now=self._at(10, 29)), 0)
        self.assertEqual(checkin.release_due_items(now=now), 1)
        item.refresh_from_db()
        self.assertEqual(item.released_at, now)
        self.assertFalse(item.is_active)
        self.assertIsNone(item.handed_out_at)
        self.assertEqual(checkin.state(item, now), "released")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn(self.product.title, mail.outbox[0].body)
        self.assertEqual(checkin.release_due_items(now=now + timedelta(minutes=5)), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.r2.status = Resource.Status.RETIRED
        self.r2.save()
        self.assertEqual(
            allocate_resource(self.product, self._at(11), self._at(12)), self.r1
        )

    def test_release_mail_text(self):
        self.user.language = "en"
        self.user.save()
        self._item()
        checkin.release_due_items(now=self._at(10, 31))
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Your reservation was released")
        self.assertIn(f"Your reservation for {self.product.title} on", msg.body)
        self.assertIn("was released because it was not started by 10:30.", msg.body)

    def test_release_mail_german(self):
        self.user.language = "de"
        self.user.save()
        self._item()
        checkin.release_due_items(now=self._at(10, 31))
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Deine Buchung wurde freigegeben")
        self.assertIn(
            "wurde freigegeben, weil sie nicht bis 10:30 gestartet wurde.", msg.body
        )

    def test_release_applies_to_pending(self):
        item = self._item(status=Booking.Status.PENDING)
        self.assertEqual(checkin.release_due_items(now=self._at(10, 31)), 1)
        item.refresh_from_db()
        self.assertIsNotNone(item.released_at)

    def test_release_skips_unflagged_and_checked_in(self):
        plain, (p1,) = _make_checkin_product(1, "SK", on=False)
        unflagged = self._item(resource=p1)
        checked = self._item()
        checkin.check_in(checked, now=self._at(10, 1))
        self.assertEqual(checkin.release_due_items(now=self._at(10, 45)), 0)
        for item in (unflagged, checked):
            item.refresh_from_db()
            self.assertTrue(item.is_active)
            self.assertIsNone(item.released_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_release_does_not_touch_adjacent_item(self):
        first = self._item(start=self._at(9), end=self._at(10))
        second = self._item(start=self._at(10), end=self._at(11))
        self.assertEqual(checkin.release_due_items(now=self._at(9, 31)), 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.released_at)
        self.assertTrue(second.is_active)
        self.assertIsNone(second.released_at)

    def test_all_items_released_cancels_booking(self):
        item = self._item()
        checkin.release_due_items(now=self._at(10, 31))
        item.booking.refresh_from_db()
        self.assertEqual(item.booking.status, Booking.Status.CANCELLED)

    def test_partial_release_keeps_booking(self):
        item = self._item()
        self._item(booking=item.booking, resource=self.r2,
                   start=self._at(14), end=self._at(15))
        checkin.release_due_items(now=self._at(10, 31))
        item.booking.refresh_from_db()
        self.assertEqual(item.booking.status, Booking.Status.CONFIRMED)

    def test_end_use_requires_checkin_for_flagged(self):
        item = self._item()
        now = self._at(10, 10)
        self.assertEqual(end_self_service_use_error(item, now), "not_endable")
        item = checkin.check_in(item, now=self._at(10, 5))
        self.assertIsNone(end_self_service_use_error(item, now))
        _close_self_service_item(item, now)
        item.refresh_from_db()
        self.assertEqual(item.handed_out_at, self._at(10, 5))
        self.assertEqual(item.returned_at, now)

    def test_completion_skips_unchecked_flagged(self):
        unchecked = self._item()
        checked = self._item(resource=self.r2)
        checkin.check_in(checked, now=self._at(10, 2))
        self.assertEqual(complete_self_service_items(now=self._at(11)), 1)
        unchecked.refresh_from_db()
        checked.refresh_from_db()
        self.assertTrue(unchecked.is_active)
        self.assertIsNone(unchecked.handed_out_at)
        self.assertFalse(checked.is_active)
        self.assertEqual(checked.handed_out_at, self._at(10, 2))
        self.assertEqual(checked.returned_at, self._at(11))

    def test_command_dry_run(self):
        item = Booking.objects.create(
            borrower=self.user, status=Booking.Status.CONFIRMED,
            submitted_at=timezone.now() - timedelta(hours=2),
        )
        start = timezone.now() - timedelta(hours=1)
        due = BookingItem.objects.create(
            booking=item, resource=self.r1,
            period=DateTimeTZRange(start, start + timedelta(hours=3)),
        )
        out = StringIO()
        call_command("release_unstarted_items", "--dry-run", stdout=out)
        self.assertIn("1", out.getvalue())
        due.refresh_from_db()
        self.assertTrue(due.is_active)
        self.assertIsNone(due.released_at)
        self.assertEqual(len(mail.outbox), 0)
        out = StringIO()
        call_command("release_unstarted_items", stdout=out)
        self.assertIn("1", out.getvalue())
        due.refresh_from_db()
        self.assertIsNotNone(due.released_at)


class ReleasedItemPayloadTests(TestCase):
    """Released items in payloads, ICS, overdue and the desk day view (§6.2)."""

    def setUp(self):
        self.user = User.objects.create_user("rel", password="x", email="rel@example.org")
        self.admin = User.objects.create_user(
            "reladmin", password="x", is_staff=True, is_superuser=True
        )
        self.product, (self.r1, self.r2) = _make_checkin_product(2, "RP")
        # On-site *with* hand-out: a desk item (self-service ones skip
        # pickup/overdue logic anyway).
        self.product.requires_handout = True
        self.product.save()
        self.start = timezone.now().replace(microsecond=0) - timedelta(minutes=7)
        self.end = self.start + timedelta(hours=2)
        self.booking = Booking.objects.create(
            borrower=self.user, status=Booking.Status.CONFIRMED,
            submitted_at=self.start - timedelta(days=1),
        )
        self.a = BookingItem.objects.create(
            booking=self.booking, resource=self.r1, period=DateTimeTZRange(self.start, self.end)
        )
        self.b = BookingItem.objects.create(
            booking=self.booking, resource=self.r2, period=DateTimeTZRange(self.start, self.end)
        )

    def _release(self, item):
        item.released_at = timezone.now()
        item.is_active = False
        item.save(update_fields=["released_at", "is_active"])

    def _items(self, url="/api/bookings/"):
        self.client.force_login(self.user)
        data = self.client.get(url).data
        results = data["results"] if "results" in data else data
        return {i["id"]: i for i in results[0]["items"]}

    def test_released_payload(self):
        self._release(self.a)
        items = self._items()
        self.assertTrue(items[self.a.id]["released"])
        self.assertFalse(items[self.a.id]["dropped"])
        self.assertEqual(items[self.a.id]["checkin_state"], "released")
        self.assertIsNotNone(items[self.a.id]["released_at"])
        self.assertIsNone(items[self.a.id]["late_minutes"])
        self.assertFalse(items[self.b.id]["released"])

    def test_late_payload(self):
        items = self._items()
        item = items[self.b.id]
        self.assertTrue(item["checkin_required"])
        self.assertEqual(item["checkin_state"], "late")
        self.assertEqual(item["late_minutes"], 7)
        self.assertIsNotNone(item["checkin_deadline"])
        self.assertIsNone(item["checked_in_at"])

    def test_unflagged_item_payload(self):
        _, (plain,) = _make_checkin_product(1, "RU", on=False)
        other = BookingItem.objects.create(
            booking=self.booking, resource=plain, period=DateTimeTZRange(self.start, self.end)
        )
        item = self._items()[other.id]
        self.assertFalse(item["checkin_required"])
        self.assertIsNone(item["checkin_state"])
        self.assertIsNone(item["checkin_deadline"])
        self.assertIsNone(item["late_minutes"])

    def test_ics_omits_released_item(self):
        from .ics import build_ics

        self._release(self.a)
        booking = Booking.objects.prefetch_related(
            "items__resource__product", "items__resource__resource_pool"
        ).get(pk=self.booking.pk)
        ics = build_ics(booking)
        self.assertNotIn(self.r1.inventory_number, ics)
        self.assertIn(self.r2.inventory_number, ics)

    def test_overdue_ignores_released(self):
        from .services import overdue_items

        past = timezone.now() - timedelta(days=3)
        for item in (self.a, self.b):
            item.period = DateTimeTZRange(past, past + timedelta(hours=1))
            item.save(update_fields=["period"])
        self._release(self.a)
        booking = Booking.objects.get(pk=self.booking.pk)
        pickups, returns = overdue_items(booking)
        self.assertEqual([i.id for i in pickups], [self.b.id])
        self._release(self.b)
        booking = Booking.objects.get(pk=self.booking.pk)
        self.assertEqual(overdue_items(booking), ([], []))

    def test_day_overview_omits_released_only_booking(self):
        self._release(self.a)
        self._release(self.b)
        self.client.force_login(self.admin)
        res = self.client.get(
            "/api/manage/bookings/day/", {"date": timezone.localdate().isoformat()}
        )
        self.assertEqual(res.status_code, 200)
        for key in ("pickups", "returns", "overdue"):
            self.assertNotIn(self.booking.id, {b["id"] for b in res.data[key]})
