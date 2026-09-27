# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Tests for the lending booking engine (ADR-0006)."""
from datetime import datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import AccessGroup, PoolMembership
from catalog.models import Product, ProductType, Resource, ResourcePool

from .models import Block, Booking, BookingItem
from .services import (
    add_to_cart,
    apply_block_to_bookings,
    availability,
    availability_by_pool,
    availability_on_date,
    availability_per_day,
    available_resources,
    cancel_uncollected_bookings,
    create_reservation,
    import_holidays,
    notify_missing_products,
    product_gap_delta,
)

User = get_user_model()


def _make_product_with_resources(count, suffix=""):
    """Create a product with ``count`` resources in an all-week-open pool.

    Pass a unique ``suffix`` to build a second, independent product within the
    same test (all catalog names are unique).
    """
    product_type = ProductType.objects.create(name=f"Camera{suffix}")
    product = Product.objects.create(product_type=product_type, title=f"GoPro{suffix}")
    # Open every day by default so availability tests are date-independent;
    # closed-weekday tests set this explicitly. max_booking_months=0 disables
    # the booking horizon so existing far-future fixtures stay valid (the
    # horizon itself is covered by BookingHorizonTests).
    pool = ResourcePool.objects.create(
        name=f"DigiLab{suffix}", pool_id=f"DigiLab{suffix}", closed_weekdays=[],
        max_booking_months=0,
    )
    resources = [
        Resource.objects.create(
            product=product,
            resource_pool=pool,
            inventory_number=f"DigiLab{suffix}-{i:03d}",
            qr_code_id=f"QR{suffix}-{i:03d}",
        )
        for i in range(count)
    ]
    return product, resources


def _two_pool_product():
    """A product stocked with one resource each in two independent, open pools.

    Used to test the borrower's pool choice (#10): both pools are eligible
    (no access group), so availability/add-to-cart may be scoped to either.
    """
    product_type = ProductType.objects.create(name="TwoPoolCam")
    product = Product.objects.create(product_type=product_type, title="Multi-pool camera")
    pool1 = ResourcePool.objects.create(
        name="PoolOne", pool_id="PoolOne", closed_weekdays=[], max_booking_months=0,
    )
    pool2 = ResourcePool.objects.create(
        name="PoolTwo", pool_id="PoolTwo", closed_weekdays=[], max_booking_months=0,
    )
    r1 = Resource.objects.create(
        product=product, resource_pool=pool1,
        inventory_number="PoolOne-001", qr_code_id="QR-PoolOne-001",
    )
    r2 = Resource.objects.create(
        product=product, resource_pool=pool2,
        inventory_number="PoolTwo-001", qr_code_id="QR-PoolTwo-001",
    )
    return product, pool1, pool2, r1, r2


class BookingOrderModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice")
        self.product, res = _make_product_with_resources(1)
        self.pool = res[0].resource_pool

    def test_confirm_records_time_and_message(self):
        b = Booking.objects.create(borrower=self.user, status=Booking.Status.PENDING,
                                   resource_pool=self.pool)
        b.confirm("Bitte um 10 Uhr")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CONFIRMED)
        self.assertIsNotNone(b.confirmed_at)
        self.assertEqual(b.confirmation_message, "Bitte um 10 Uhr")

    def test_order_parts(self):
        import uuid
        other = ResourcePool.objects.create(name="Zeta", pool_id="zeta", position=5)
        self.pool.position = 1
        self.pool.save(update_fields=["position"])
        cid = uuid.uuid4()
        b2 = Booking.objects.create(borrower=self.user, status="pending",
                                    resource_pool=other, checkout_id=cid)
        b1 = Booking.objects.create(borrower=self.user, status="pending",
                                    resource_pool=self.pool, checkout_id=cid)
        self.assertEqual(b2.order_parts(), [b1, b2])
        lone = Booking.objects.create(borrower=self.user, status="pending",
                                      resource_pool=self.pool)
        self.assertEqual(lone.order_parts(), [lone])

    def test_send_time_default(self):
        from datetime import time
        from catalog.models import NotificationSetting
        self.assertEqual(NotificationSetting.load().confirmation_send_time, time(17, 0))


class BookingEngineTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(days=2)

    def test_exclusion_constraint_blocks_overlapping_active_booking(self):
        _, resources = _make_product_with_resources(1)
        resource = resources[0]
        create_reservation(self.borrower, [(resource, self.start, self.end)])

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_reservation(
                    self.borrower,
                    [(resource, self.start + timedelta(days=1), self.end + timedelta(days=1))],
                )

    def test_availability_counts_free_resources(self):
        product, resources = _make_product_with_resources(3)
        create_reservation(self.borrower, [(resources[0], self.start, self.end)])

        result = availability(product, self.start, self.end)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["available"], 2)

    def test_cancelled_booking_frees_the_slot(self):
        product, resources = _make_product_with_resources(1)
        booking = create_reservation(self.borrower, [(resources[0], self.start, self.end)])
        booking.cancel()

        result = availability(product, self.start, self.end)
        self.assertEqual(result["available"], 1)

    def test_expired_cart_hold_is_free(self):
        product, resources = _make_product_with_resources(1)
        booking = create_reservation(
            self.borrower, [(resources[0], self.start, self.end)],
            status=Booking.Status.CART,
        )
        booking.expires_at = timezone.now() - timedelta(minutes=1)
        booking.save(update_fields=["expires_at"])

        result = availability(product, self.start, self.end)
        self.assertEqual(result["available"], 1)


class BlockTests(TestCase):
    def setUp(self):
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(days=2)
        self.period = DateTimeTZRange(self.start, self.end)

    def _available(self, product):
        return availability(product, self.start, self.end)["available"]

    def test_resource_block_reduces_availability(self):
        product, resources = _make_product_with_resources(3)
        Block.objects.create(period=self.period, resource=resources[0])
        self.assertEqual(self._available(product), 2)

    def test_product_block_blocks_all(self):
        product, _ = _make_product_with_resources(2)
        Block.objects.create(period=self.period, product=product)
        self.assertEqual(self._available(product), 0)

    def test_pool_block_blocks_pool_resources(self):
        product, resources = _make_product_with_resources(2)
        Block.objects.create(period=self.period, resource_pool=resources[0].resource_pool)
        self.assertEqual(self._available(product), 0)

    def test_system_block_blocks_everything(self):
        product, _ = _make_product_with_resources(2)
        Block.objects.create(period=self.period)  # all targets empty = system
        self.assertEqual(self._available(product), 0)

    def test_block_outside_window_has_no_effect(self):
        product, resources = _make_product_with_resources(2)
        far = DateTimeTZRange(self.start + timedelta(days=10), self.end + timedelta(days=10))
        Block.objects.create(period=far, resource=resources[0])
        self.assertEqual(self._available(product), 2)

    def test_blocked_resource_cannot_be_reserved(self):
        from .services import available_resources

        product, resources = _make_product_with_resources(1)
        Block.objects.create(period=self.period, resource=resources[0])
        self.assertFalse(available_resources(product, self.start, self.end).exists())


class ClosedWeekdayTests(TestCase):
    def _day(self):
        # A fixed datetime; its weekday drives the test.
        return timezone.make_aware(timezone.datetime(2099, 6, 6, 10, 0))

    def test_closed_weekday_makes_resources_unavailable(self):
        product, resources = _make_product_with_resources(2)
        day = self._day()
        pool = resources[0].resource_pool
        pool.closed_weekdays = [day.weekday()]
        pool.save()
        result = availability(product, day, day + timedelta(hours=2))
        self.assertEqual(result["available"], 0)

    def test_open_weekday_is_available(self):
        product, resources = _make_product_with_resources(2)
        day = self._day()
        pool = resources[0].resource_pool
        pool.closed_weekdays = [(day.weekday() + 1) % 7]  # a different weekday
        pool.save()
        result = availability(product, day, day + timedelta(hours=2))
        self.assertEqual(result["available"], 2)


class HourlyAvailabilityTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")

    def test_slots_follow_opening_hours_and_occupancy(self):
        from .services import availability_per_hour

        product, resources = _make_product_with_resources(2)
        day = timezone.datetime(2099, 6, 3).date()
        key = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][day.weekday()]
        pool = resources[0].resource_pool
        pool.opening_hours = {key: [["09:00", "12:00"]]}
        pool.save()

        slots = availability_per_hour(product, day)
        self.assertEqual([s["label"] for s in slots], ["09:00", "10:00", "11:00"])
        self.assertTrue(all(s["available"] == 2 for s in slots))

        # Occupy 10:00–11:00 on one room.
        start = timezone.make_aware(timezone.datetime(2099, 6, 3, 10, 0))
        create_reservation(self.borrower, [(resources[0], start, start + timedelta(hours=1))])
        by_label = {s["label"]: s["available"] for s in availability_per_hour(product, day)}
        self.assertEqual(by_label["10:00"], 1)
        self.assertEqual(by_label["09:00"], 2)

    def test_closed_weekday_has_no_slots(self):
        from .services import availability_per_hour

        product, resources = _make_product_with_resources(1)
        day = timezone.datetime(2099, 6, 3).date()
        pool = resources[0].resource_pool
        pool.opening_hours = {}  # no opening hours for that weekday
        pool.save()
        self.assertEqual(availability_per_hour(product, day), [])

    def test_utilization_percentage_per_day(self):
        from .services import hourly_utilization_per_day

        product, resources = _make_product_with_resources(2)
        day = timezone.datetime(2099, 6, 3).date()
        key = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][day.weekday()]
        pool = resources[0].resource_pool
        pool.opening_hours = {key: [["09:00", "12:00"]]}  # 3h × 2 rooms = 6 capacity
        pool.save()
        start = timezone.make_aware(timezone.datetime(2099, 6, 3, 9, 0))
        create_reservation(self.borrower, [(resources[0], start, start + timedelta(hours=2))])

        days = hourly_utilization_per_day(product, day, day + timedelta(days=1))
        self.assertFalse(days[0]["closed"])
        self.assertEqual(days[0]["booked_pct"], 33)  # 2 of 6 resource-hours

    def test_utilization_marks_closed_day(self):
        from .services import hourly_utilization_per_day

        product, resources = _make_product_with_resources(1)
        day = timezone.datetime(2099, 6, 3).date()
        pool = resources[0].resource_pool
        pool.opening_hours = {}
        pool.save()
        days = hourly_utilization_per_day(product, day, day + timedelta(days=1))
        self.assertTrue(days[0]["closed"])
        self.assertIsNone(days[0]["booked_pct"])


class LeadTimeTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")

    def _product_with_lead(self, hours, count=2):
        product, resources = _make_product_with_resources(count)
        pool = resources[0].resource_pool
        pool.lead_time_hours = hours
        pool.save()
        return product

    def test_pickup_within_lead_time_is_unavailable(self):
        product = self._product_with_lead(48)
        start = timezone.now() + timedelta(hours=24)  # too soon for a 48h lead
        result = availability(product, start, start + timedelta(days=1))
        self.assertEqual(result["available"], 0)

    def test_pickup_after_lead_time_is_available(self):
        product = self._product_with_lead(48)
        start = timezone.now() + timedelta(hours=72)
        result = availability(product, start, start + timedelta(days=1))
        self.assertEqual(result["available"], 2)

    def test_zero_lead_time_allows_immediate_pickup(self):
        product = self._product_with_lead(0, count=1)
        start = timezone.now() + timedelta(minutes=5)
        result = availability(product, start, start + timedelta(days=1))
        self.assertEqual(result["available"], 1)


class LeadTimeApiTests(APITestCase):
    def test_booking_within_lead_time_is_rejected(self):
        user = User.objects.create_user(username="alice")
        product, resources = _make_product_with_resources(1)
        pool = resources[0].resource_pool
        pool.lead_time_hours = 48
        pool.save()
        self.client.force_login(user)
        start = (timezone.now() + timedelta(hours=12)).isoformat()
        end = (timezone.now() + timedelta(hours=36)).isoformat()
        response = self.client.post(
            "/api/cart/items/",
            {"product": product.id, "start": start, "end": end},
            format="json",
        )
        self.assertEqual(response.status_code, 409)


class BridgingTests(TestCase):
    """A booking may span blocked/closed days as long as the pickup and return
    days are open — the device is simply kept over the closure."""

    def _window(self):
        start = timezone.make_aware(timezone.datetime(2099, 6, 1, 10, 0))  # pickup
        return start, start + timedelta(days=3)  # return day = June 4

    def _full_day_block(self, product, day_number):
        day_start = timezone.make_aware(timezone.datetime(2099, 6, day_number, 0, 0))
        Block.objects.create(
            period=DateTimeTZRange(day_start, day_start + timedelta(days=1)),
            product=product,
        )

    def test_booking_bridges_a_blocked_middle_day(self):
        from .services import available_resources

        product, _ = _make_product_with_resources(2)
        start, end = self._window()
        self._full_day_block(product, 2)  # block the middle day (June 2)
        self.assertEqual(available_resources(product, start, end).count(), 2)

    def test_block_on_pickup_day_prevents_booking(self):
        from .services import available_resources

        product, _ = _make_product_with_resources(2)
        start, end = self._window()
        self._full_day_block(product, 1)  # block the pickup day
        self.assertEqual(available_resources(product, start, end).count(), 0)

    def test_block_on_return_day_prevents_booking(self):
        from .services import available_resources

        product, _ = _make_product_with_resources(2)
        start, end = self._window()
        self._full_day_block(product, 4)  # block the return day
        self.assertEqual(available_resources(product, start, end).count(), 0)

    def test_calendar_marks_blocked_day_closed_not_zero(self):
        from .services import availability_per_day

        product, _ = _make_product_with_resources(2)
        self._full_day_block(product, 2)
        days = availability_per_day(
            product, timezone.datetime(2099, 6, 1).date(), timezone.datetime(2099, 6, 4).date()
        )
        by_date = {d["date"]: d for d in days}
        blocked = by_date["2099-06-02"]
        self.assertTrue(blocked["closed"])
        self.assertEqual(blocked["available"], 0)
        self.assertFalse(by_date["2099-06-01"]["closed"])
        self.assertEqual(by_date["2099-06-01"]["available"], 2)


class HolidayImportTests(TestCase):
    def test_import_creates_blocks_and_is_idempotent(self):
        created = import_holidays("DE", "NI", 2026)
        self.assertEqual(len(created), 10)
        self.assertEqual(Block.objects.count(), 10)
        again = import_holidays("DE", "NI", 2026)  # no duplicates
        self.assertEqual(len(again), 0)
        self.assertEqual(Block.objects.count(), 10)

    def test_holiday_block_makes_day_unavailable(self):
        product, _ = _make_product_with_resources(2)
        import_holidays("DE", "NI", 2026)
        new_year = timezone.make_aware(timezone.datetime(2026, 1, 1, 10, 0))
        result = availability(product, new_year, new_year + timedelta(hours=2))
        self.assertEqual(result["available"], 0)


class HolidayImportApiTests(APITestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="b")
        self.admin = User.objects.create_user(
            username="a", is_staff=True, is_superuser=True
        )

    def _import(self, **body):
        return self.client.post("/api/manage/holidays/import/", body, format="json")

    def test_requires_lender(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self._import(country="DE", subdiv="NI", year=2026).status_code, 403)

    def test_admin_imports(self):
        self.client.force_login(self.admin)
        response = self._import(country="DE", subdiv="NI", year=2026)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 10)

    def test_invalid_country_returns_400(self):
        self.client.force_login(self.admin)
        self.assertEqual(self._import(country="ZZ", year=2026).status_code, 400)


class AvailabilityApiTests(APITestCase):
    def test_availability_endpoint(self):
        borrower = User.objects.create_user(username="bob")
        product, resources = _make_product_with_resources(2)
        start = timezone.now() + timedelta(days=1)
        create_reservation(borrower, [(resources[0], start, start + timedelta(days=1))])

        response = self.client.get(
            f"/api/products/{product.id}/availability/",
            {"start": "2099-01-01", "end": "2099-01-02"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["available"], 2)  # far future: nothing booked

    def test_availability_requires_valid_range(self):
        product, _ = _make_product_with_resources(1)
        response = self.client.get(f"/api/products/{product.id}/availability/")
        self.assertEqual(response.status_code, 400)

    def test_availability_calendar_per_day(self):
        borrower = User.objects.create_user(username="dave")
        product, resources = _make_product_with_resources(2)
        start = timezone.make_aware(timezone.datetime(2099, 8, 10, 9, 0))
        create_reservation(borrower, [(resources[0], start, start + timedelta(days=2))])

        response = self.client.get(
            f"/api/products/{product.id}/availability/calendar/",
            {"from": "2099-08-09", "to": "2099-08-13"},
        )
        self.assertEqual(response.status_code, 200)
        by_date = {d["date"]: d["available"] for d in response.data["days"]}
        self.assertEqual(by_date["2099-08-09"], 2)  # free
        self.assertEqual(by_date["2099-08-10"], 1)  # booked
        self.assertEqual(by_date["2099-08-11"], 1)  # booked
        self.assertEqual(by_date["2099-08-12"], 1)  # booking runs until 09:00

    def test_bulk_availability_for_date(self):
        borrower = User.objects.create_user(username="erin")
        product, resources = _make_product_with_resources(2)
        start = timezone.make_aware(timezone.datetime(2099, 9, 5, 9, 0))
        create_reservation(borrower, [(resources[0], start, start + timedelta(days=1))])

        response = self.client.get(
            "/api/availability/", {"date": "2099-09-05", "products": str(product.id)}
        )
        self.assertEqual(response.status_code, 200)
        entry = response.data["availability"][str(product.id)]
        self.assertEqual(entry["total"], 2)
        self.assertEqual(entry["available"], 1)

    def test_single_day_window_spans_the_whole_day(self):
        """A date-only start == end must cover that day, not be rejected."""
        borrower = User.objects.create_user(username="carol")
        product, resources = _make_product_with_resources(2)
        # Book one resource across 2099-03-10.
        day_start = timezone.make_aware(timezone.datetime(2099, 3, 10, 9, 0))
        create_reservation(borrower, [(resources[0], day_start, day_start + timedelta(hours=2))])

        response = self.client.get(
            f"/api/products/{product.id}/availability/",
            {"start": "2099-03-10", "end": "2099-03-10"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["available"], 1)


class BookingApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice")
        self.product, self.resources = _make_product_with_resources(2)
        self.window = {"start": "2099-05-01", "end": "2099-05-03"}

    def _add(self):
        return self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, **self.window},
            format="json",
        )

    def _submit(self, note=""):
        return self.client.post("/api/cart/submit/", {"note": note}, format="json")

    def test_add_requires_authentication(self):
        self.assertEqual(self._add().status_code, 403)

    def test_cart_submit_creates_listed_reservation(self):
        self.client.force_login(self.user)
        self.assertEqual(self._add().status_code, 201)
        submitted = self._submit(note="for the music seminar")
        self.assertEqual(submitted.status_code, 201)
        booking = submitted.data["bookings"][0]
        self.assertEqual(booking["status"], "pending")
        self.assertEqual(booking["note"], "for the music seminar")
        self.assertTrue(booking["code"])  # reservation number assigned

        listing = self.client.get("/api/bookings/")
        self.assertEqual(listing.data["count"], 1)

    def test_required_note_blocks_empty_submit(self):
        pool = self.resources[0].resource_pool
        pool.require_booking_note = True
        pool.save(update_fields=["require_booking_note"])
        self.client.force_login(self.user)
        self.assertEqual(self._add().status_code, 201)
        # Cart signals the requirement so the UI can mark the field.
        self.assertTrue(self.client.get("/api/cart/").data["cart"]["note_required"])
        # Empty note is rejected; a note goes through.
        self.assertEqual(self._submit(note="").status_code, 400)
        self.assertEqual(self._submit(note="for class").status_code, 201)

    def test_note_not_required_when_pool_does_not_ask(self):
        self.client.force_login(self.user)
        self._add()
        self.assertFalse(self.client.get("/api/cart/").data["cart"]["note_required"])
        self.assertEqual(self._submit(note="").status_code, 201)

    def test_cart_is_excluded_from_my_bookings(self):
        self.client.force_login(self.user)
        self._add()  # sits in the cart, not yet submitted
        self.assertEqual(self.client.get("/api/bookings/").data["count"], 0)

    def test_current_count_counts_only_active_bookings(self):
        self.client.force_login(self.user)
        # Nothing submitted yet.
        self.assertEqual(
            self.client.get("/api/bookings/current-count/").data["count"], 0
        )
        # A submitted (pending) booking is "current".
        self._add()
        booking = self._submit().data["bookings"][0]
        self.assertEqual(
            self.client.get("/api/bookings/current-count/").data["count"], 1
        )
        # Cancelling drops it back out of the count.
        self.client.delete(f"/api/bookings/{booking['id']}/")
        self.assertEqual(
            self.client.get("/api/bookings/current-count/").data["count"], 0
        )

    def test_overbooking_returns_409(self):
        self.client.force_login(self.user)
        self.assertEqual(self._add().status_code, 201)  # resource 1
        self.assertEqual(self._add().status_code, 201)  # resource 2
        self.assertEqual(self._add().status_code, 409)  # none left

    def test_cancel_frees_the_resource(self):
        self.client.force_login(self.user)
        self._add()
        self._add()  # both resources held by the cart
        booking = self._submit().data["bookings"][0]
        self.assertEqual(self._add().status_code, 409)  # none free
        self.assertEqual(
            self.client.delete(f"/api/bookings/{booking['id']}/").status_code, 204
        )
        self.assertEqual(self._add().status_code, 201)  # free again

    def test_cancel_notifies_pool_contact(self):
        pool = self.resources[0].resource_pool
        pool.email = "desk@example.org"
        pool.save(update_fields=["email"])  # notify_on_cancellation defaults True
        self.client.force_login(self.user)
        self._add()
        booking = self._submit().data["bookings"][0]
        mail.outbox.clear()
        self.client.delete(f"/api/bookings/{booking['id']}/")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["desk@example.org"])
        self.assertIn(booking["code"], msg.subject)

    def test_cancel_does_not_notify_when_opted_out(self):
        pool = self.resources[0].resource_pool
        pool.email = "desk@example.org"
        pool.notify_on_cancellation = False
        pool.save(update_fields=["email", "notify_on_cancellation"])
        self.client.force_login(self.user)
        self._add()
        booking = self._submit().data["bookings"][0]
        mail.outbox.clear()
        self.client.delete(f"/api/bookings/{booking['id']}/")
        self.assertEqual(len(mail.outbox), 0)

    def test_cancel_without_pool_email_sends_nothing(self):
        self.client.force_login(self.user)
        self._add()
        booking = self._submit().data["bookings"][0]
        mail.outbox.clear()
        self.client.delete(f"/api/bookings/{booking['id']}/")
        self.assertEqual(len(mail.outbox), 0)

    def test_only_own_bookings_are_listed(self):
        other = User.objects.create_user(username="bob")
        self.client.force_login(other)
        self._add()
        self._submit()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/bookings/").data["count"], 0)

    def test_expired_cart_hold_is_reaped_and_slot_reusable(self):
        # A slot held by an expired cart must be re-bookable.
        product, resources = _make_product_with_resources(1, suffix="-exp")
        other = User.objects.create_user(username="bob")
        start = timezone.make_aware(timezone.datetime(2099, 5, 1))
        end = timezone.make_aware(timezone.datetime(2099, 5, 3))
        cart = create_reservation(
            other, [(resources[0], start, end)], status=Booking.Status.CART
        )
        cart.expires_at = timezone.now() - timedelta(minutes=1)
        cart.save(update_fields=["expires_at"])

        self.client.force_login(self.user)
        response = self.client.post(
            "/api/cart/items/",
            {"product": product.id, "start": "2099-05-01", "end": "2099-05-03"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        cart.refresh_from_db()
        self.assertEqual(cart.status, "cancelled")

    def test_live_reservation_blocks_the_slot(self):
        # A submitted reservation by someone else blocks adding the slot.
        product, resources = _make_product_with_resources(1, suffix="-live")
        other = User.objects.create_user(username="carol")
        create_reservation(
            other,
            [(resources[0],
              timezone.make_aware(timezone.datetime(2099, 5, 1)),
              timezone.make_aware(timezone.datetime(2099, 5, 3)))],
        )
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/cart/items/",
            {"product": product.id, "start": "2099-05-01", "end": "2099-05-03"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)


class SplitSubmitTests(APITestCase):
    """Submitting a multi-pool cart splits it into one booking per pool (#26)."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", email="a@example.org")
        self.p1, r1 = _make_product_with_resources(1)
        self.p2, r2 = _make_product_with_resources(1, suffix="B")
        self.pool_a, self.pool_b = r1[0].resource_pool, r2[0].resource_pool
        self.pool_a.position, self.pool_b.position = 1, 2
        self.pool_a.save(update_fields=["position"]); self.pool_b.save(update_fields=["position"])
        self.client.force_login(self.user)
        for p in (self.p1, self.p2):
            self.client.post("/api/cart/items/",
                             {"product": p.id, "start": "2099-05-01", "end": "2099-05-02"},
                             format="json")

    def test_two_pool_cart_becomes_two_reservations(self):
        mail.outbox = []
        res = self.client.post("/api/cart/submit/", {"note": "Seminar"}, format="json")
        self.assertEqual(res.status_code, 201)
        codes = [b["code"] for b in res.data["bookings"]]
        self.assertEqual(len(codes), 2)
        self.assertEqual(len(set(codes)), 2)
        parts = list(Booking.objects.filter(borrower=self.user).exclude(status="cart")
                     .order_by("resource_pool__position"))
        self.assertEqual([p.resource_pool_id for p in parts], [self.pool_a.id, self.pool_b.id])
        self.assertEqual(len({p.checkout_id for p in parts}), 1)
        self.assertTrue(all(p.status == Booking.Status.PENDING for p in parts))
        self.assertTrue(all(p.note == "Seminar" for p in parts))
        for p in parts:
            self.assertEqual({i.resource.resource_pool_id for i in p.items.all()}, {p.resource_pool_id})
        self.assertEqual(len(mail.outbox), 1)           # one combined received mail
        for code in codes:
            self.assertIn(code, mail.outbox[0].body)

    def test_submit_response_groups_only_own_pool(self):
        # The first reservation reuses the cart object; its prefetched items
        # must not still list the items moved to the second reservation.
        res = self.client.post("/api/cart/submit/", {"note": ""}, format="json")
        self.assertEqual(res.status_code, 201)
        pools = [[g["pool_id"] for g in b["groups"]] for b in res.data["bookings"]]
        self.assertEqual(pools, [[self.pool_a.id], [self.pool_b.id]])
        self.assertEqual(
            [[i["pool_id"] for i in b["items"]] for b in res.data["bookings"]],
            [[self.pool_a.id], [self.pool_b.id]],
        )

    def test_received_mail_lists_each_pool_under_its_own_code(self):
        mail.outbox = []
        res = self.client.post("/api/cart/submit/", {"note": ""}, format="json")
        code_a, code_b = [b["code"] for b in res.data["bookings"]]
        body = mail.outbox[0].body
        first_part = body.split(code_a, 1)[1].split(code_b, 1)[0]
        self.assertIn(self.pool_a.name, first_part)
        self.assertNotIn(self.pool_b.name, first_part)

    def test_single_pool_cart_keeps_cart_code(self):
        cart = Booking.objects.get(borrower=self.user, status="cart")
        cart.items.filter(resource__resource_pool=self.pool_b).delete()
        res = self.client.post("/api/cart/submit/", {"note": ""}, format="json")
        self.assertEqual([b["code"] for b in res.data["bookings"]], [cart.code])
        cart.refresh_from_db()
        self.assertEqual(cart.resource_pool_id, self.pool_a.id)


class SplitCodeLookupTests(APITestCase):
    """Legacy pickup codes still resolve correctly after a split (#26, I2)."""

    def setUp(self):
        import uuid

        self.borrower = User.objects.create_user(username="alice", email="a@x.test")
        self.lender_b = User.objects.create_user(username="lenb")
        self.lender_c = User.objects.create_user(username="lenc")
        self.p1, r1 = _make_product_with_resources(1, suffix="X")
        self.p2, r2 = _make_product_with_resources(1, suffix="Y")
        self.pool_a, self.pool_b = r1[0].resource_pool, r2[0].resource_pool
        self.pool_c = ResourcePool.objects.create(
            name="PoolC", pool_id="PC", closed_weekdays=[], max_booking_months=0
        )
        # lender_b manages only pool_b (the sibling part's pool); lender_c
        # manages neither part's pool at all.
        PoolMembership.objects.create(user=self.lender_b, resource_pool=self.pool_b)
        PoolMembership.objects.create(user=self.lender_c, resource_pool=self.pool_c)

        far = timezone.make_aware(datetime(2099, 5, 1, 10, 0))
        self.part_a = create_reservation(
            self.borrower, [(r1[0], far, far + timedelta(days=1))]
        )
        self.part_b = create_reservation(
            self.borrower, [(r2[0], far, far + timedelta(days=1))]
        )
        cid = uuid.uuid4()
        Booking.objects.filter(id__in=[self.part_a.id, self.part_b.id]).update(
            checkout_id=cid
        )
        self.part_a.refresh_from_db()
        self.part_b.refresh_from_db()

    def test_lender_of_sibling_pool_gets_their_own_part_by_code(self):
        # Scanning/looking up part_a's code as a lender who only manages
        # pool_b (part_b's pool) must return part_b — the same order's own
        # part in scope — never part_a itself.
        self.client.force_login(self.lender_b)
        res = self.client.get(f"/api/manage/bookings/by-code/?code={self.part_a.code}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], self.part_b.code)
        self.assertEqual(res.json()["id"], self.part_b.id)

    def test_lender_of_neither_pool_gets_404_by_code(self):
        self.client.force_login(self.lender_c)
        res = self.client.get(f"/api/manage/bookings/by-code/?code={self.part_a.code}")
        self.assertEqual(res.status_code, 404)

    def test_lender_of_sibling_pool_scan_routes_to_their_own_part(self):
        self.client.force_login(self.lender_b)
        res = self.client.get(
            "/api/manage/bookings/scan/", {"value": self.part_a.code}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["kind"], "booking")
        self.assertEqual(res.data["mode"], "handout")
        self.assertEqual(res.data["booking"]["code"], self.part_b.code)

    def test_lender_of_neither_pool_scan_is_404(self):
        self.client.force_login(self.lender_c)
        res = self.client.get(
            "/api/manage/bookings/scan/", {"value": self.part_a.code}
        )
        self.assertEqual(res.status_code, 404)


class ExpireUncollectedBookingsTests(TestCase):
    """cancel_uncollected_bookings cancels past, never-collected reservations."""

    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")
        self.product, self.resources = _make_product_with_resources(3)
        self.now = timezone.now()

    def _reservation(self, resource, start, end, status=Booking.Status.CONFIRMED):
        return create_reservation(self.borrower, [(resource, start, end)], status=status)

    def test_past_uncollected_reservation_is_cancelled(self):
        booking = self._reservation(
            self.resources[0],
            self.now - timedelta(days=3),
            self.now - timedelta(days=1),
        )
        self.assertEqual(cancel_uncollected_bookings(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        # The slot is freed (its item deactivated).
        self.assertFalse(booking.items.filter(is_active=True).exists())

    def test_dry_run_reports_without_cancelling(self):
        booking = self._reservation(
            self.resources[0],
            self.now - timedelta(days=3),
            self.now - timedelta(days=1),
        )
        self.assertEqual(cancel_uncollected_bookings(dry_run=True), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_future_reservation_is_kept(self):
        booking = self._reservation(
            self.resources[0],
            self.now + timedelta(days=1),
            self.now + timedelta(days=3),
        )
        self.assertEqual(cancel_uncollected_bookings(), 0)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_ongoing_reservation_is_kept(self):
        # Started yesterday, ends tomorrow — still within its window.
        booking = self._reservation(
            self.resources[0],
            self.now - timedelta(days=1),
            self.now + timedelta(days=1),
        )
        self.assertEqual(cancel_uncollected_bookings(), 0)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_collected_booking_is_kept(self):
        # A picked-up item in the past is a real (overdue-return) lending, not a no-show.
        booking = self._reservation(
            self.resources[0],
            self.now - timedelta(days=3),
            self.now - timedelta(days=1),
            status=Booking.Status.HANDED_OUT,
        )
        booking.items.update(handed_out_at=self.now - timedelta(days=3))
        self.assertEqual(cancel_uncollected_bookings(), 0)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.HANDED_OUT)

    def test_partially_collected_reservation_is_kept(self):
        # Two items, both past; one was handed out → the booking is a real lending.
        start, end = self.now - timedelta(days=3), self.now - timedelta(days=1)
        booking = create_reservation(
            self.borrower,
            [(self.resources[0], start, end), (self.resources[1], start, end)],
            status=Booking.Status.CONFIRMED,
        )
        booking.items.first().__class__.objects.filter(
            pk=booking.items.first().pk
        ).update(handed_out_at=start)
        self.assertEqual(cancel_uncollected_bookings(), 0)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)


class CartApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice")
        self.product, self.resources = _make_product_with_resources(2)
        self.client.force_login(self.user)

    def _add(self, start="2099-05-01", end="2099-05-03"):
        return self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "start": start, "end": end},
            format="json",
        )

    def test_empty_cart(self):
        self.assertIsNone(self.client.get("/api/cart/").data["cart"])

    def test_add_creates_cart_with_code_and_groups(self):
        self._add()
        cart = self.client.get("/api/cart/").data["cart"]
        self.assertEqual(cart["status"], "cart")
        self.assertTrue(cart["code"])
        self.assertEqual(len(cart["items"]), 1)
        # Grouped by pool, then period.
        self.assertEqual(len(cart["groups"]), 1)
        self.assertEqual(cart["groups"][0]["pool"], "DigiLab")
        self.assertEqual(len(cart["groups"][0]["periods"]), 1)

    def test_cart_items_carry_pool_accent_color(self):
        # Cart items (and the grouped-by-pool view) must expose the pool's
        # accent colour so the frontend can colour each pool's cart group (#16).
        self.resources[0].resource_pool.accent_color = "sky"
        self.resources[0].resource_pool.save(update_fields=["accent_color"])
        self._add()
        cart = self.client.get("/api/cart/").data["cart"]
        self.assertEqual(cart["items"][0]["accent_color"], "sky")
        self.assertEqual(
            cart["groups"][0]["periods"][0]["items"][0]["accent_color"], "sky"
        )

    def test_remove_item(self):
        self._add()
        cart = self.client.get("/api/cart/").data["cart"]
        item_id = cart["items"][0]["id"]
        response = self.client.delete(f"/api/cart/items/{item_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["items"]), 0)

    def test_submit_empty_cart_is_rejected(self):
        self.assertEqual(
            self.client.post("/api/cart/submit/", {}, format="json").status_code, 400
        )

    def test_double_submit_of_the_same_cart_is_rejected(self):
        # M1: a concurrent second submit racing on the same (now-stale)
        # in-memory cart object must abort instead of creating a duplicate
        # reservation — submit_cart re-checks the status under a row lock.
        from .services import get_active_cart, submit_cart

        self._add()
        cart = get_active_cart(self.user)
        submit_cart(cart)  # first submit succeeds
        before = Booking.objects.filter(borrower=self.user).count()
        with self.assertRaises(ValueError):
            submit_cart(cart)  # same (stale) cart object, submitted again
        self.assertEqual(Booking.objects.filter(borrower=self.user).count(), before)

    def test_view_returns_400_when_cart_already_submitted_concurrently(self):
        from unittest.mock import patch

        from .services import get_active_cart

        self._add()
        cart = get_active_cart(self.user)
        # Simulate a request that raced ahead and already submitted this
        # same cart between this request's own lookup and its submit call.
        Booking.objects.filter(pk=cart.pk).update(status=Booking.Status.PENDING)
        with patch("lending.views.get_active_cart", return_value=cart):
            res = self.client.post("/api/cart/submit/", {"note": ""}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("already submitted", res.data["detail"])

    def test_discard_cart_releases_slots(self):
        self._add()
        self.assertEqual(self.client.delete("/api/cart/").status_code, 204)
        self.assertIsNone(self.client.get("/api/cart/").data["cart"])

    def test_one_cart_per_user_accumulates_items(self):
        self._add()
        self._add(start="2099-06-01", end="2099-06-03")  # different period
        cart = self.client.get("/api/cart/").data["cart"]
        self.assertEqual(len(cart["items"]), 2)
        self.assertEqual(len(cart["groups"][0]["periods"]), 2)  # two periods, one pool

    def test_add_response_includes_the_just_added_item(self):
        # The POST response must reflect the item added in that very call (no
        # off-by-one from a stale prefetch cache on the existing cart).
        self._add()
        second = self._add(start="2099-06-01", end="2099-06-03")
        self.assertEqual(second.status_code, 201)
        self.assertEqual(len(second.data["items"]), 2)


class PoolChoiceApiTests(APITestCase):
    """Borrower picks the pool a booking comes from (#10, task 4)."""

    def setUp(self):
        self.user = User.objects.create_user(username="pat")
        self.product, self.pool1, self.pool2, self.r1, self.r2 = _two_pool_product()
        self.client.force_login(self.user)
        self.window = {"start": "2099-05-01", "end": "2099-05-03"}

    def test_add_to_cart_with_pool_allocates_from_that_pool(self):
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "pool": self.pool1.id, **self.window},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        item = response.data["items"][0]
        self.assertEqual(item["pool_id"], self.pool1.id)

        # Booking again with the other pool comes from that one instead.
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "pool": self.pool2.id, **self.window},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        pool_ids = {i["pool_id"] for i in response.data["items"]}
        self.assertIn(self.pool2.id, pool_ids)

    def test_availability_with_pool_counts_only_that_pool(self):
        response = self.client.get(
            f"/api/products/{self.product.id}/availability/",
            {"pool": self.pool1.id, **self.window},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["available"], 1)

        # Without a pool, both pools' units are counted.
        response = self.client.get(
            f"/api/products/{self.product.id}/availability/", self.window,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["available"], 2)

    def test_add_to_cart_with_pool_lacking_resource_falls_back(self):
        empty_pool = ResourcePool.objects.create(
            name="EmptyPool", pool_id="EmptyPool", closed_weekdays=[], max_booking_months=0,
        )
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "pool": empty_pool.id, **self.window},
            format="json",
        )
        self.assertEqual(response.status_code, 201)  # not a 500; falls back
        item = response.data["items"][0]
        self.assertNotEqual(item["pool_id"], empty_pool.id)
        self.assertIn(item["pool_id"], {self.pool1.id, self.pool2.id})

    def test_add_to_cart_with_garbage_pool_param_falls_back(self):
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "pool": "not-a-number", **self.window},
            format="json",
        )
        self.assertEqual(response.status_code, 201)  # tolerant parsing, not a 500

    def test_stepper_plus_one_stays_in_the_lines_pool(self):
        """The cart's "+1 of this line" stepper (CartItemView.post) must pull
        the extra unit from the SAME pool as the rest of the line, never a
        different eligible pool — otherwise one product/period line would
        silently split across pickup locations (#10 follow-up)."""
        # A second free unit in pool1, so the "+1" has somewhere to come from
        # if (and only if) it stays scoped to pool1.
        Resource.objects.create(
            product=self.product, resource_pool=self.pool1,
            inventory_number="PoolOne-002", qr_code_id="QR-PoolOne-002",
        )
        add = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "pool": self.pool1.id, **self.window},
            format="json",
        )
        self.assertEqual(add.status_code, 201)
        item_id = add.data["items"][0]["id"]
        self.assertEqual(add.data["items"][0]["pool_id"], self.pool1.id)

        stepped = self.client.post(f"/api/cart/items/{item_id}/", format="json")
        self.assertEqual(stepped.status_code, 201)
        pool_ids = {i["pool_id"] for i in stepped.data["items"]}
        # Both units of the line must be pool1 — never pool2, even though
        # pool2 also holds a free, eligible unit of this product.
        self.assertEqual(pool_ids, {self.pool1.id})

    def test_stepper_plus_one_409s_when_the_lines_pool_has_no_more_units(self):
        """If the line's own pool has no further free unit, the stepper must
        not reach into a different pool — it should just report none free."""
        add = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "pool": self.pool1.id, **self.window},
            format="json",
        )
        self.assertEqual(add.status_code, 201)
        item_id = add.data["items"][0]["id"]

        # pool1 only ever had one resource (self.r1, now held by this line);
        # pool2's free unit must not be used as a fallback.
        stepped = self.client.post(f"/api/cart/items/{item_id}/", format="json")
        self.assertEqual(stepped.status_code, 409)


class PoolAvailabilityBreakdownTests(APITestCase):
    """Per-pool availability breakdown, used to let the borrower pick a pickup
    pool AFTER choosing a date (#10, task 1)."""

    def setUp(self):
        self.user = User.objects.create_user(username="breakdown-user")
        self.restricted_user = User.objects.create_user(username="breakdown-restricted")

        product_type = ProductType.objects.create(name="BreakdownCam")
        self.product = Product.objects.create(
            product_type=product_type, title="Breakdown Camera"
        )

        # pool_b has a lower curated position than pool_a, so it must come
        # first in the breakdown even though it was created second.
        self.pool_b = ResourcePool.objects.create(
            name="BreakdownPoolB", pool_id="BreakdownPoolB",
            closed_weekdays=[], max_booking_months=0, position=0,
        )
        self.pool_a = ResourcePool.objects.create(
            name="BreakdownPoolA", pool_id="BreakdownPoolA",
            closed_weekdays=[], max_booking_months=0, position=1,
        )
        # pool_c holds no resource for this product -> omitted from any result.
        self.pool_c = ResourcePool.objects.create(
            name="BreakdownPoolC", pool_id="BreakdownPoolC",
            closed_weekdays=[], max_booking_months=0, position=2,
        )
        self.resource_a = Resource.objects.create(
            product=self.product, resource_pool=self.pool_a,
            inventory_number="BreakdownPoolA-001", qr_code_id="QR-BreakdownPoolA-001",
        )
        Resource.objects.create(
            product=self.product, resource_pool=self.pool_b,
            inventory_number="BreakdownPoolB-001", qr_code_id="QR-BreakdownPoolB-001",
        )

        # A pool gated behind an access group neither user is a member of
        # (except via manual membership, added only where needed) -- must
        # never appear in a breakdown for a user who lacks access.
        self.restricted_pool = ResourcePool.objects.create(
            name="BreakdownRestrictedPool", pool_id="BreakdownRestrictedPool",
            closed_weekdays=[], max_booking_months=0, position=3,
        )
        group = AccessGroup.objects.create(name="BreakdownGroup")
        group.pools.add(self.restricted_pool)
        Resource.objects.create(
            product=self.product, resource_pool=self.restricted_pool,
            inventory_number="BreakdownRestrictedPool-001",
            qr_code_id="QR-BreakdownRestrictedPool-001",
        )

        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(days=2)
        self.start_iso = self.start.date().isoformat()
        self.end_iso = self.end.date().isoformat()

    def test_availability_by_pool_lists_only_pools_with_resources_ordered_by_position(self):
        result = availability_by_pool(
            self.product, self.start, self.end,
            {self.pool_a.id, self.pool_b.id, self.pool_c.id},
        )
        # C omitted; ordered by position -> B (0) before A (1)
        self.assertEqual([r["pool_id"] for r in result], [self.pool_b.id, self.pool_a.id])
        self.assertTrue(all("total" in r and "available" in r for r in result))

    def test_availability_by_pool_includes_pool_with_zero_free(self):
        # occupy every unit in pool A for the range
        create_reservation(self.user, [(self.resource_a, self.start, self.end)])

        result = availability_by_pool(self.product, self.start, self.end, {self.pool_a.id})
        row = next(r for r in result if r["pool_id"] == self.pool_a.id)
        self.assertGreater(row["total"], 0)
        self.assertEqual(row["available"], 0)

    def test_pool_availability_endpoint_returns_eligible_breakdown(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            f"/api/products/{self.product.id}/availability/pools/",
            {"start": self.start_iso, "end": self.end_iso},
        )
        self.assertEqual(resp.status_code, 200)
        pools = resp.json()["pools"]
        self.assertIn("accent_color", pools[0])
        self.assertIn("name", pools[0])

    def test_pool_availability_endpoint_ignores_pool_param(self):
        # passing ?pool=<one id> must NOT narrow the breakdown
        self.client.force_login(self.user)
        base = self.client.get(
            f"/api/products/{self.product.id}/availability/pools/",
            {"start": self.start_iso, "end": self.end_iso},
        ).json()["pools"]
        scoped = self.client.get(
            f"/api/products/{self.product.id}/availability/pools/",
            {"start": self.start_iso, "end": self.end_iso, "pool": self.pool_a.id},
        ).json()["pools"]
        self.assertEqual([p["pool_id"] for p in base], [p["pool_id"] for p in scoped])

    def test_pool_availability_endpoint_excludes_ineligible_pools(self):
        # a pool the user cannot access (behind an access group) must not appear
        self.client.force_login(self.restricted_user)
        resp = self.client.get(
            f"/api/products/{self.product.id}/availability/pools/",
            {"start": self.start_iso, "end": self.end_iso},
        )
        ids = [p["pool_id"] for p in resp.json()["pools"]]
        self.assertNotIn(self.restricted_pool.id, ids)

    def test_pool_availability_endpoint_400_on_bad_bounds(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            f"/api/products/{self.product.id}/availability/pools/",
            {"start": "nope", "end": "nope"},
        )
        self.assertEqual(resp.status_code, 400)


class ManageBookingApiTests(APITestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.product, resources = _make_product_with_resources(1)
        self.pool = resources[0].resource_pool
        start = timezone.now() + timedelta(days=1)
        self.booking = create_reservation(
            self.borrower, [(resources[0], start, start + timedelta(days=1))]
        )

    def _extra_resource(self, suffix):
        return Resource.objects.create(
            product=self.product,
            resource_pool=self.pool,
            inventory_number=f"DigiLab-1{suffix:02d}",
            qr_code_id=f"QR-1{suffix:02d}",
        )

    def test_borrower_cannot_access_manage(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self.client.get("/api/manage/bookings/").status_code, 403)

    def test_admin_lists_all_with_borrower(self):
        self.client.force_login(self.admin)
        response = self.client.get("/api/manage/bookings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["borrower"], "alice")
        self.assertTrue(response.data["results"][0]["code"])  # reservation number

    def test_return_info_visible_to_lender_only(self):
        self.product.return_info = "Check the lens before taking it back."
        self.product.save(update_fields=["return_info"])

        # Lender/admin booking view exposes the product's return information.
        self.client.force_login(self.admin)
        item = self.client.get("/api/manage/bookings/").data["results"][0]["items"][0]
        self.assertEqual(item["return_info"], "Check the lens before taking it back.")

        # The borrower's own booking view does not.
        self.client.force_login(self.borrower)
        b_item = self.client.get("/api/bookings/").data["results"][0]["items"][0]
        self.assertNotIn("return_info", b_item)

    def test_search_by_reservation_number_and_customer(self):
        self.client.force_login(self.admin)
        bob = User.objects.create_user(username="bob")
        other = self._extra_resource(0)
        start = timezone.now() + timedelta(days=1)
        booking2 = create_reservation(bob, [(other, start, start + timedelta(days=1))])

        # By reservation number → only that booking.
        by_code = self.client.get("/api/manage/bookings/", {"search": self.booking.code})
        self.assertEqual(by_code.data["count"], 1)
        self.assertEqual(by_code.data["results"][0]["code"], self.booking.code)

        # By customer name.
        by_customer = self.client.get("/api/manage/bookings/", {"search": "bob"})
        self.assertEqual(by_customer.data["count"], 1)
        self.assertEqual(by_customer.data["results"][0]["borrower"], "bob")
        self.assertEqual(by_customer.data["results"][0]["id"], booking2.id)

    def test_confirm_includes_custom_message_in_email(self):
        self.borrower.email = "alice@example.org"
        self.borrower.save(update_fields=["email"])
        self.client.force_login(self.admin)
        mail.outbox.clear()
        res = self.client.post(
            f"/api/manage/bookings/{self.booking.id}/confirm/",
            {"message": "Pickup Tuesday 10:00 works."},
            format="json",
        )
        self.assertEqual(res.data["status"], "confirmed")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Pickup Tuesday 10:00 works.", mail.outbox[0].body)

    def test_confirm_without_message_sends_plain_email(self):
        self.borrower.email = "alice@example.org"
        self.borrower.save(update_fields=["email"])
        self.client.force_login(self.admin)
        mail.outbox.clear()
        self.client.post(f"/api/manage/bookings/{self.booking.id}/confirm/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("lending team:", mail.outbox[0].body)

    def test_confirm_returns_200_when_mail_dispatch_raises(self):
        # I1: a mail/dispatch error must never turn a successful confirm into
        # a 500 — the confirmation itself stays saved and is retried later.
        from unittest.mock import patch

        self.borrower.email = "alice@example.org"
        self.borrower.save(update_fields=["email"])
        self.client.force_login(self.admin)
        mail.outbox.clear()
        with patch(
            "lending.views.dispatch_confirmation_mails",
            side_effect=RuntimeError("smtp down"),
        ):
            res = self.client.post(f"/api/manage/bookings/{self.booking.id}/confirm/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "confirmed")
        self.assertEqual(mail.outbox, [])
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertIsNotNone(self.booking.confirmed_at)

    def test_scan_pickup_code_returns_booking_for_handout(self):
        self.client.force_login(self.admin)
        res = self.client.get("/api/manage/bookings/scan/", {"value": self.booking.code})
        self.assertEqual(res.data["kind"], "booking")
        self.assertEqual(res.data["mode"], "handout")
        self.assertEqual(res.data["booking"]["code"], self.booking.code)

    def test_scan_idle_device_shows_storage_and_defect(self):
        self.client.force_login(self.admin)
        qr = self.booking.items.first().resource.qr_code_id
        # The setUp booking is pending and starts tomorrow → device is idle.
        res = self.client.get("/api/manage/bookings/scan/", {"value": qr})
        self.assertEqual(res.data["mode"], "idle")
        self.assertIsNone(res.data["booking"])
        self.assertIn("storage_location", res.data["resource"])

    def test_scan_handed_out_device_offers_return(self):
        self.client.force_login(self.admin)
        base = f"/api/manage/bookings/{self.booking.id}"
        self.client.post(f"{base}/confirm/")
        self.client.post(f"{base}/handout/")
        qr = self.booking.items.first().resource.qr_code_id
        res = self.client.get("/api/manage/bookings/scan/", {"value": qr})
        self.assertEqual(res.data["mode"], "return")
        self.assertEqual(res.data["booking"]["id"], self.booking.id)

    def test_scan_due_reservation_offers_handout(self):
        self.client.force_login(self.admin)
        res = self._extra_resource(9)
        past = timezone.now() - timedelta(hours=1)
        create_reservation(
            self.borrower, [(res, past, past + timedelta(days=1))],
            status=Booking.Status.CONFIRMED,
        )
        out = self.client.get("/api/manage/bookings/scan/", {"value": res.qr_code_id})
        self.assertEqual(out.data["mode"], "handout")
        self.assertEqual(out.data["kind"], "resource")

    def test_scan_unknown_value_is_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get("/api/manage/bookings/scan/", {"value": "NOPE-1"}).status_code,
            404,
        )

    def test_status_transitions(self):
        self.client.force_login(self.admin)
        base = f"/api/manage/bookings/{self.booking.id}"
        self.assertEqual(self.client.post(f"{base}/confirm/").data["status"], "confirmed")
        self.assertEqual(self.client.post(f"{base}/handout/").data["status"], "handed_out")
        self.assertEqual(self.client.post(f"{base}/return/").data["status"], "returned")

    def test_invalid_transition_is_rejected(self):
        self.client.force_login(self.admin)
        # A pending booking cannot be handed out before being confirmed.
        response = self.client.post(f"/api/manage/bookings/{self.booking.id}/handout/")
        self.assertEqual(response.status_code, 400)

    def test_manage_calendar_counts(self):
        self.client.force_login(self.admin)
        now = timezone.now()
        today = timezone.localdate()
        res = [self._extra_resource(i) for i in range(2)]
        create_reservation(self.borrower, [(res[0], now, now + timedelta(days=1))]).confirm()
        create_reservation(self.borrower, [(res[1], now - timedelta(days=2), now)]).hand_out()

        response = self.client.get(
            "/api/manage/bookings/calendar/",
            {"from": today.isoformat(), "to": (today + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        by_date = {d["date"]: d for d in response.data["days"]}
        self.assertEqual(by_date[today.isoformat()]["pickups"], 1)
        self.assertEqual(by_date[today.isoformat()]["returns"], 1)

    def test_calendar_counts_each_period_and_skips_pending(self):
        # A confirmed multi-period booking shows a pickup per period; a pending
        # (unconfirmed) reservation is not desk work yet, so it isn't counted —
        # keeping the calendar in step with the day overview.
        self.client.force_login(self.admin)
        today = timezone.localdate()
        start1 = timezone.make_aware(timezone.datetime(today.year, today.month, today.day))
        res = [self._extra_resource(i) for i in range(3)]
        create_reservation(
            self.borrower,
            [
                (res[0], start1, start1 + timedelta(days=1)),
                (res[1], start1 + timedelta(days=2), start1 + timedelta(days=3)),
            ],
        ).confirm()
        # A separate pending reservation starting today must NOT be counted.
        create_reservation(self.borrower, [(res[2], start1, start1 + timedelta(days=1))])

        response = self.client.get(
            "/api/manage/bookings/calendar/",
            {"from": today.isoformat(), "to": (today + timedelta(days=5)).isoformat()},
        )
        by_date = {d["date"]: d for d in response.data["days"]}
        day0 = today.isoformat()
        day2 = (today + timedelta(days=2)).isoformat()
        self.assertEqual(by_date[day0]["pickups"], 1)  # confirmed first period only
        self.assertEqual(by_date[day2]["pickups"], 1)  # confirmed second period

    def test_lender_can_cancel_confirmed_booking(self):
        self.client.force_login(self.admin)
        self.booking.confirm()
        response = self.client.post(f"/api/manage/bookings/{self.booking.id}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "cancelled")
        self.assertFalse(self.booking.items.filter(is_active=True).exists())

    def test_lender_cannot_cancel_handed_out_booking(self):
        self.client.force_login(self.admin)
        self.booking.confirm()
        self.booking.hand_out()  # now handed_out
        response = self.client.post(f"/api/manage/bookings/{self.booking.id}/cancel/")
        self.assertEqual(response.status_code, 400)

    def test_remind_sends_email_for_overdue(self):
        from django.core import mail

        self.borrower.email = "alice@example.org"
        self.borrower.save(update_fields=["email"])
        # An overdue pickup: confirmed, start in the past, not handed out.
        res = self._extra_resource(0)
        start = timezone.now() - timedelta(days=2)
        overdue = create_reservation(self.borrower, [(res, start, start + timedelta(days=1))])
        overdue.confirm()
        self.client.force_login(self.admin)
        mail.outbox.clear()
        response = self.client.post(f"/api/manage/bookings/{overdue.id}/remind/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        # Borrower has no language set -> institution default (German).
        self.assertIn("überfällig", mail.outbox[0].subject.lower())
        overdue.refresh_from_db()
        self.assertIsNotNone(overdue.overdue_reminded_at)
        # A reminder is recorded in the history and exposed by the API.
        self.assertEqual(overdue.reminders.count(), 1)
        self.assertEqual(len(response.data["reminders"]), 1)
        self.assertEqual(response.data["reminders"][0]["overdue_pickups"], 1)

        # A second reminder appends to the history.
        self.client.post(f"/api/manage/bookings/{overdue.id}/remind/")
        self.assertEqual(overdue.reminders.count(), 2)

    def test_remind_rejects_when_nothing_overdue(self):
        self.client.force_login(self.admin)
        self.booking.confirm()  # starts tomorrow -> not overdue
        response = self.client.post(f"/api/manage/bookings/{self.booking.id}/remind/")
        self.assertEqual(response.status_code, 400)

    def test_overdue_reminders_command_is_deduped(self):
        from django.core import mail
        from django.core.management import call_command

        self.borrower.email = "alice@example.org"
        self.borrower.save(update_fields=["email"])
        res = self._extra_resource(1)
        start = timezone.now() - timedelta(days=2)
        overdue = create_reservation(self.borrower, [(res, start, start + timedelta(days=1))])
        overdue.confirm()

        mail.outbox.clear()
        call_command("send_overdue_reminders")
        self.assertEqual(len(mail.outbox), 1)  # the overdue one (not the future booking)
        call_command("send_overdue_reminders")
        self.assertEqual(len(mail.outbox), 1)  # not resent within the window

    def test_handout_and_return_per_appointment(self):
        self.client.force_login(self.admin)
        res = [self._extra_resource(i) for i in range(2)]
        start = timezone.now() + timedelta(days=1)
        booking = create_reservation(
            self.borrower,
            [
                (res[0], start, start + timedelta(days=1)),
                (res[1], start + timedelta(days=5), start + timedelta(days=6)),
            ],
        )
        booking.confirm()
        items = list(booking.items.order_by("id"))
        base = f"/api/manage/bookings/{booking.id}"

        # Hand out only the first appointment's item.
        r = self.client.post(f"{base}/handout/", {"item_ids": [items[0].id]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "handed_out")
        items[0].refresh_from_db(); items[1].refresh_from_db()
        self.assertIsNotNone(items[0].handed_out_at)
        self.assertIsNone(items[1].handed_out_at)  # second appointment untouched

        # Return that item; nothing is out anymore -> back to confirmed.
        r = self.client.post(f"{base}/return/", {"item_ids": [items[0].id]}, format="json")
        self.assertEqual(r.data["status"], "confirmed")
        items[0].refresh_from_db()
        self.assertIsNotNone(items[0].returned_at)
        self.assertFalse(items[0].is_active)

        # Hand out and return the second -> all items returned -> returned.
        self.client.post(f"{base}/handout/", {"item_ids": [items[1].id]}, format="json")
        r = self.client.post(f"{base}/return/", {"item_ids": [items[1].id]}, format="json")
        self.assertEqual(r.data["status"], "returned")

    def test_return_shown_on_last_booked_day(self):
        # Booking with exclusive end 2099-06-20 00:00 → last booked day is the
        # 19th; the return must show on the 19th, not the (closed) 20th.
        self.client.force_login(self.admin)
        res = self._extra_resource(0)
        start = timezone.make_aware(timezone.datetime(2099, 6, 15))
        end = timezone.make_aware(timezone.datetime(2099, 6, 20))
        booking = create_reservation(self.borrower, [(res, start, end)])
        booking.hand_out()

        calendar = self.client.get(
            "/api/manage/bookings/calendar/", {"from": "2099-06-14", "to": "2099-06-25"}
        )
        by_date = {d["date"]: d for d in calendar.data["days"]}
        self.assertEqual(by_date["2099-06-19"]["returns"], 1)
        self.assertNotIn("2099-06-20", by_date)  # no activity on the exclusive end

        day = self.client.get("/api/manage/bookings/day/", {"date": "2099-06-19"})
        self.assertIn(booking.id, {b["id"] for b in day.data["returns"]})

    def test_day_overview_buckets(self):
        self.client.force_login(self.admin)
        now = timezone.now()
        today = timezone.localdate()
        res = [self._extra_resource(i) for i in range(4)]

        pickup = create_reservation(self.borrower, [(res[0], now, now + timedelta(days=2))])
        pickup.confirm()  # confirmed, starts today -> pickup
        ret = create_reservation(self.borrower, [(res[1], now - timedelta(days=2), now)])
        ret.hand_out()  # handed out, ends today -> return
        overdue = create_reservation(
            self.borrower, [(res[2], now - timedelta(days=3), now - timedelta(days=1))]
        )
        overdue.hand_out()  # handed out, ended yesterday -> overdue
        create_reservation(self.borrower, [(res[3], now + timedelta(days=5), now + timedelta(days=6))])

        response = self.client.get("/api/manage/bookings/day/", {"date": today.isoformat()})
        self.assertEqual(response.status_code, 200)
        ids = lambda key: {b["id"] for b in response.data[key]}
        self.assertIn(pickup.id, ids("pickups"))
        self.assertIn(ret.id, ids("returns"))
        self.assertIn(overdue.id, ids("overdue"))
        # setUp's pending booking + the new one.
        self.assertEqual(len(response.data["to_confirm"]), 2)

    def test_booking_exposes_borrower_name_and_id(self):
        self.borrower.first_name = "Alice"
        self.borrower.last_name = "Doe"
        self.borrower.save(update_fields=["first_name", "last_name"])
        self.client.force_login(self.admin)
        row = self.client.get("/api/manage/bookings/").data["results"][0]
        self.assertEqual(row["borrower_name"], "Alice Doe")
        self.assertEqual(row["borrower_id"], self.borrower.id)

    def test_borrower_name_falls_back_to_username(self):
        self.client.force_login(self.admin)
        row = self.client.get("/api/manage/bookings/").data["results"][0]
        self.assertEqual(row["borrower_name"], "alice")

    def test_pending_count_endpoint(self):
        self.client.force_login(self.admin)
        # setUp creates one pending (submitted) reservation.
        res = self.client.get("/api/manage/bookings/pending-count/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        # Confirming it drops the count to zero.
        self.client.post(f"/api/manage/bookings/{self.booking.id}/confirm/")
        res = self.client.get("/api/manage/bookings/pending-count/")
        self.assertEqual(res.data["count"], 0)


class ManageResourceApiTests(APITestCase):
    def setUp(self):
        self.product, resources = _make_product_with_resources(1)
        self.resource = resources[0]
        self.pool = self.resource.resource_pool
        self.borrower = User.objects.create_user(username="alice")
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)

    def _defective(self, note=None):
        body = {"note": note} if note is not None else {}
        return self.client.post(
            f"/api/manage/resources/{self.resource.id}/defective/", body, format="json"
        )

    def test_borrower_cannot_mark_defective(self):
        self.client.force_login(self.borrower)
        self.assertEqual(self._defective().status_code, 403)

    def test_lender_marks_defective_and_back(self):
        self.client.force_login(self.lender)
        response = self._defective()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "defective")
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.status, Resource.Status.DEFECTIVE)
        # A defective resource drops out of availability.
        start = timezone.now() + timedelta(days=1)
        self.assertEqual(availability(self.product, start, start + timedelta(days=1))["available"], 0)
        # Marking available restores it.
        restored = self.client.post(f"/api/manage/resources/{self.resource.id}/available/")
        self.assertEqual(restored.data["status"], "available")
        self.assertEqual(
            availability(self.product, start, start + timedelta(days=1))["available"], 1
        )

    def test_defect_note_is_stored_and_cleared_on_repair(self):
        self.client.force_login(self.lender)
        response = self._defective(note="Lens cracked")
        self.assertEqual(response.data["defect_note"], "Lens cracked")
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.defect_note, "Lens cracked")
        # Repair clears the note.
        self.client.post(f"/api/manage/resources/{self.resource.id}/available/")
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.defect_note, "")

    def test_marking_defective_emails_pool_contact(self):
        self.pool.email = "lab@uni.example"
        self.pool.save(update_fields=["email"])  # notify_on_defect defaults True
        self.client.force_login(self.lender)
        mail.outbox.clear()
        self._defective(note="Lens cracked")
        pool_mails = [m for m in mail.outbox if "lab@uni.example" in m.to]
        self.assertEqual(len(pool_mails), 1)
        # Pool has no email_language set -> institution default (German).
        self.assertIn("defekt", pool_mails[0].subject.lower())
        self.assertIn(self.resource.inventory_number, pool_mails[0].body)

    def test_defect_notice_uses_pool_email_language(self):
        self.pool.email = "lab@uni.example"
        self.pool.email_language = "en"
        self.pool.save(update_fields=["email", "email_language"])
        self.client.force_login(self.lender)
        mail.outbox.clear()
        self._defective(note="Lens cracked")
        pool_mails = [m for m in mail.outbox if "lab@uni.example" in m.to]
        self.assertEqual(len(pool_mails), 1)
        # English source text present (override("en") renders the msgid).
        self.assertIn("was marked defective", pool_mails[0].body)

    def test_pool_defect_notice_can_be_disabled(self):
        self.pool.email = "lab@uni.example"
        self.pool.notify_on_defect = False
        self.pool.save(update_fields=["email", "notify_on_defect"])
        self.client.force_login(self.lender)
        mail.outbox.clear()
        self._defective()
        self.assertEqual([m for m in mail.outbox if "lab@uni.example" in m.to], [])

    def test_no_pool_notice_without_contact_email(self):
        self.assertEqual(self.pool.email, "")  # no contact email configured
        self.client.force_login(self.lender)
        mail.outbox.clear()
        self._defective()
        self.assertEqual(mail.outbox, [])

    def test_lender_cannot_touch_other_pool(self):
        other_product, other_res = _make_product_with_resources(1, suffix="-other")
        self.client.force_login(self.lender)
        response = self.client.post(
            f"/api/manage/resources/{other_res[0].id}/defective/"
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_mark_available_resource_available(self):
        self.client.force_login(self.admin)
        # Already available -> the "available" action is rejected.
        response = self.client.post(f"/api/manage/resources/{self.resource.id}/available/")
        self.assertEqual(response.status_code, 400)


class DefectTicketTests(APITestCase):
    """Per-pool GitLab defect-ticket settings + issue creation on defect."""

    def setUp(self):
        self.product, resources = _make_product_with_resources(1)
        self.resource = resources[0]
        self.pool = self.resource.resource_pool
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)

    # --- settings endpoint -------------------------------------------------

    def test_token_is_write_only_and_reported_as_set(self):
        self.client.force_login(self.lender)
        patch = self.client.patch(
            f"/api/manage/defect-tickets/{self.pool.id}/",
            {
                "defect_gitlab_url": "https://gitlab.example.com/grp/proj",
                "defect_gitlab_token": "secret-token",
            },
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        # The response never echoes the token, only that one is stored.
        self.assertNotIn("defect_gitlab_token", patch.data)
        self.assertTrue(patch.data["defect_gitlab_token_set"])
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.defect_gitlab_token, "secret-token")

        listing = self.client.get("/api/manage/defect-tickets/")
        self.assertEqual(listing.status_code, 200)
        row = next(r for r in listing.data if r["id"] == self.pool.id)
        self.assertNotIn("defect_gitlab_token", row)
        self.assertTrue(row["defect_gitlab_token_set"])

    def test_token_kept_when_omitted_and_cleared_when_blank(self):
        self.pool.defect_gitlab_token = "keep-me"
        self.pool.defect_gitlab_url = "https://gitlab.example.com/grp/proj"
        self.pool.save()
        self.client.force_login(self.lender)
        # Omitting the token leaves it untouched.
        self.client.patch(
            f"/api/manage/defect-tickets/{self.pool.id}/",
            {"defect_gitlab_url": "https://gitlab.example.com/grp/other"},
            format="json",
        )
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.defect_gitlab_token, "keep-me")
        # An explicit empty string clears it.
        self.client.patch(
            f"/api/manage/defect-tickets/{self.pool.id}/",
            {"defect_gitlab_token": ""},
            format="json",
        )
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.defect_gitlab_token, "")

    def test_token_is_encrypted_at_rest(self):
        self.client.force_login(self.lender)
        self.client.patch(
            f"/api/manage/defect-tickets/{self.pool.id}/",
            {
                "defect_gitlab_url": "https://gitlab.example.com/g/p",
                "defect_gitlab_token": "secret-token",
            },
            format="json",
        )
        # The raw column holds ciphertext, not the plaintext token …
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT defect_gitlab_token FROM catalog_resourcepool WHERE id = %s",
                [self.pool.id],
            )
            raw = cursor.fetchone()[0]
        self.assertTrue(raw)
        self.assertNotEqual(raw, "secret-token")
        self.assertNotIn("secret-token", raw)
        # … yet the model transparently decrypts it back.
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.defect_gitlab_token, "secret-token")

    def test_lender_scoped_to_managed_pools(self):
        other_product, other_res = _make_product_with_resources(1, suffix="-other")
        other_pool = other_res[0].resource_pool
        self.client.force_login(self.lender)
        listing = self.client.get("/api/manage/defect-tickets/")
        self.assertEqual({r["id"] for r in listing.data}, {self.pool.id})
        # And cannot patch a pool they don't manage.
        denied = self.client.patch(
            f"/api/manage/defect-tickets/{other_pool.id}/",
            {"defect_gitlab_url": "https://gitlab.example.com/x/y"},
            format="json",
        )
        self.assertEqual(denied.status_code, 404)

    # --- issue creation on defect -----------------------------------------

    def _mark_defective(self):
        from lending.services import mark_resource_defective

        mark_resource_defective(self.resource, "Lens cracked")

    def test_marking_defective_opens_issue_when_configured(self):
        self.pool.defect_gitlab_url = "https://gitlab.example.com/grp/proj"
        self.pool.defect_gitlab_token = "secret-token"
        self.pool.save()
        with mock.patch("lending.gitlab_service.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"web_url": "https://gitlab.example.com/grp/proj/-/issues/1"}'
            )
            self._mark_defective()
            self.assertEqual(urlopen.call_count, 1)
            req = urlopen.call_args.args[0]
            self.assertEqual(
                req.full_url,
                "https://gitlab.example.com/api/v4/projects/grp%2Fproj/issues",
            )
            self.assertEqual(req.headers["Private-token"], "secret-token")
            # The issue body links back to the resource's manage page so whoever
            # resolves the ticket knows how to return the device to service.
            import json

            body = json.loads(req.data.decode())
            self.assertIn(
                f"/manage/inventory/{self.resource.id}", body["description"]
            )
        # The created issue URL is stored on the open defect record.
        from catalog.models import ResourceDefect

        defect = ResourceDefect.objects.get(
            resource=self.resource, resolved_at__isnull=True
        )
        self.assertEqual(
            defect.gitlab_issue_url,
            "https://gitlab.example.com/grp/proj/-/issues/1",
        )

    def test_no_issue_when_pool_not_configured(self):
        with mock.patch("lending.gitlab_service.request.urlopen") as urlopen:
            self._mark_defective()
            urlopen.assert_not_called()


class NotificationTests(APITestCase):
    def setUp(self):
        self.product, self.resources = _make_product_with_resources(2)
        self.pool = self.resources[0].resource_pool
        self.pool.address = "Building A"
        self.pool.room = "Room 1.01"
        self.pool.opening_hours = {"mon": [["09:00", "17:00"]]}
        self.pool.phone = "0541-1234"
        self.pool.save()
        self.user = User.objects.create_user(username="alice", email="alice@example.org")

    def _reserve(self, user):
        self.client.force_login(user)
        self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "start": "2099-05-01", "end": "2099-05-03"},
            format="json",
        )
        return self.client.post("/api/cart/submit/", {"note": ""}, format="json")

    def test_reservation_sends_email_with_pool_info(self):
        response = self._reserve(self.user)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["alice@example.org"])
        # Borrower has no language set -> institution default (German).
        self.assertIn("wartet auf Best", msg.subject)
        self.assertIn("Building A", msg.body)
        self.assertIn("Room 1.01", msg.body)
        self.assertIn("09:00", msg.body)
        self.assertIn("0541-1234", msg.body)

    def test_no_email_when_borrower_has_no_address(self):
        no_email = User.objects.create_user(username="bob")
        response = self._reserve(no_email)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)

    def test_borrower_email_uses_borrower_language(self):
        self.user.language = "en"
        self.user.save(update_fields=["language"])
        response = self._reserve(self.user)
        self.assertEqual(response.status_code, 201)
        # English source text present (override("en") renders the msgid).
        self.assertIn("we received your reservation", mail.outbox[0].body)

    def test_borrower_email_defaults_to_institution_language_when_unset(self):
        self.user.language = ""
        self.user.save(update_fields=["language"])
        response = self._reserve(self.user)
        self.assertEqual(response.status_code, 201)
        # Institution default is "de": the English source must NOT appear
        # verbatim, and the German catalog's own text must be present.
        self.assertNotIn("we received your reservation", mail.outbox[0].body)
        self.assertIn("wir haben deine Reservierung erhalten", mail.outbox[0].body)

    def test_reservation_email_includes_pool_note(self):
        # Only the English column is set; this checks the modeltranslation
        # fallback (content in an unset language falls back to English),
        # independent of the mail's own active language (German by default).
        self.pool.email_note_en = "Only for students of subject XY."
        self.pool.save(update_fields=["email_note_en"])
        response = self._reserve(self.user)
        self.assertEqual(response.status_code, 201)
        self.assertIn("Only for students of subject XY.", mail.outbox[0].body)

    def test_reservation_email_uses_custom_intro_and_footer(self):
        from catalog.models import NotificationSetting

        setting = NotificationSetting.load()
        # Only the English column is set; this checks the modeltranslation
        # fallback (content in an unset language falls back to English),
        # independent of the mail's own active language (German by default).
        setting.reservation_intro_en = "Thanks for booking with us!"
        setting.reservation_footer_en = "Pickup Wednesdays 10 to 12 only."
        setting.save()

        response = self._reserve(self.user)
        self.assertEqual(response.status_code, 201)
        body = mail.outbox[0].body
        self.assertIn("Thanks for booking with us!", body)
        self.assertIn("Pickup Wednesdays 10 to 12 only.", body)
        # Custom intro replaces the default boilerplate…
        self.assertNotIn("we received your reservation", body)
        # …but the reservation number and pickup details are always kept.
        # Borrower has no language set -> institution default (German).
        self.assertIn(
            f"Reservierungsnummer: {response.data['bookings'][0]['code']}", body
        )
        self.assertIn("Building A", body)
        self.assertIn("Room 1.01", body)

    def test_confirmation_sends_email(self):
        start = timezone.make_aware(timezone.datetime(2099, 5, 1))
        booking = create_reservation(
            self.user, [(self.resources[0], start, start + timedelta(days=2))]
        )
        admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.client.force_login(admin)
        mail.outbox.clear()  # create_reservation (service) sends nothing itself
        response = self.client.post(f"/api/manage/bookings/{booking.id}/confirm/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        # Borrower has no language set -> institution default (German).
        self.assertIn("bestätigt", mail.outbox[0].subject.lower())

    def test_reservation_mail_shows_inclusive_selected_days(self):
        # Reserve 1–3 May (period stored as [01, 04)); the mail must show the
        # last *selected* day (03 May), not the exclusive day after (04 May),
        # and no midnight times for a day booking.
        response = self._reserve(self.user)
        self.assertEqual(response.status_code, 201)
        body = mail.outbox[0].body
        self.assertIn("01 May 2099", body)
        self.assertIn("03 May 2099", body)
        self.assertNotIn("04 May", body)
        self.assertNotIn("00:00", body)

    def test_hourly_mail_shows_times(self):
        from lending.notifications import send_reservation_email

        pt = ProductType.objects.create(name="Beamer")
        hourly = Product.objects.create(
            product_type=pt, title="Beamer", lending_type=Product.LendingType.HOURS
        )
        pool = ResourcePool.objects.create(
            name="AV", pool_id="AV", closed_weekdays=[], max_booking_months=0
        )
        res = Resource.objects.create(
            product=hourly, resource_pool=pool,
            inventory_number="AV-1", qr_code_id="QR-AV-1",
        )
        start = timezone.make_aware(timezone.datetime(2099, 5, 1, 9, 0))
        end = timezone.make_aware(timezone.datetime(2099, 5, 1, 12, 0))
        booking = create_reservation(self.user, [(res, start, end)], status="pending")
        mail.outbox.clear()
        send_reservation_email(booking)
        body = mail.outbox[0].body
        self.assertIn("09:00", body)
        self.assertIn("12:00", body)

    def test_confirmation_ics_is_all_day_for_day_booking(self):
        start = timezone.make_aware(timezone.datetime(2099, 5, 1))
        booking = create_reservation(
            self.user, [(self.resources[0], start, start + timedelta(days=2))]
        )
        admin = User.objects.create_user(
            username="boss3", is_staff=True, is_superuser=True
        )
        self.client.force_login(admin)
        mail.outbox.clear()
        self.client.post(f"/api/manage/bookings/{booking.id}/confirm/")
        ics = next(
            content
            for (name, content, _mime) in mail.outbox[0].attachments
            if name.endswith(".ics")
        )
        # All-day event spanning 1–2 May (exclusive DTEND = 3 May per RFC 5545).
        self.assertIn("DTSTART;VALUE=DATE:20990501", ics)
        self.assertIn("DTEND;VALUE=DATE:20990503", ics)

    def test_confirmation_ics_location_has_full_address(self):
        self.pool.address = (
            "Studierendenzentrum (StudZ)\nGebäude 53\nKolpingstraße 1a\n49074 Osnabrück"
        )
        self.pool.save(update_fields=["address"])
        start = timezone.make_aware(timezone.datetime(2099, 5, 1))
        booking = create_reservation(
            self.user, [(self.resources[0], start, start + timedelta(days=2))]
        )
        admin = User.objects.create_user(
            username="boss2", is_staff=True, is_superuser=True
        )
        self.client.force_login(admin)
        mail.outbox.clear()
        self.client.post(f"/api/manage/bookings/{booking.id}/confirm/")
        ics = next(
            content
            for (name, content, _mime) in mail.outbox[0].attachments
            if name.endswith(".ics")
        )
        # LOCATION folds room + every address line into one navigable string.
        self.assertIn("Room 1.01", ics)
        self.assertIn("Kolpingstra", ics)
        self.assertIn("49074 Osnabr", ics)


class NotificationExtraTextTests(TestCase):
    """Configured per-mail notes + per-pool notes reach the other borrower mails."""

    def setUp(self):
        from catalog.models import NotificationSetting

        self.product, self.resources = _make_product_with_resources(2)
        self.pool = self.resources[0].resource_pool
        self.pool.email_note_en = "Only for subject XY students."
        self.pool.save(update_fields=["email_note_en"])
        self.user = User.objects.create_user(
            username="alice", email="alice@example.org"
        )
        setting = NotificationSetting.load()
        setting.rescheduled_note_en = "RESCHEDULE-NOTE"
        setting.cancellation_note_en = "CANCEL-NOTE"
        setting.reminder_note_en = "REMIND-NOTE"
        setting.defect_note_en = "DEFECT-NOTE"
        setting.save()
        self.start = timezone.make_aware(timezone.datetime(2099, 5, 1))
        self.end = self.start + timedelta(days=2)
        self.booking = create_reservation(
            self.user,
            [(self.resources[0], self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        self.item = self.booking.items.first()

    def _block(self):
        from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

        return Block(period=DateTimeTZRange(self.start, self.end))

    def _assert_both(self, marker):
        body = mail.outbox[0].body
        self.assertIn(marker, body)
        self.assertIn("Only for subject XY students.", body)

    def test_defect_notice(self):
        from lending.notifications import send_defect_notice

        mail.outbox.clear()
        send_defect_notice(self.booking, [self.item])
        self._assert_both("DEFECT-NOTE")

    def test_rescheduled(self):
        from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
        from lending.notifications import send_booking_rescheduled

        new = DateTimeTZRange(self.start + timedelta(days=7), self.end + timedelta(days=7))
        mail.outbox.clear()
        send_booking_rescheduled(
            self.booking, [(self.item, self.item.period, new)], self._block()
        )
        self._assert_both("RESCHEDULE-NOTE")

    def test_cancelled_closure(self):
        from lending.notifications import send_booking_cancelled_closure

        mail.outbox.clear()
        send_booking_cancelled_closure(self.booking, [self.item], self._block())
        self._assert_both("CANCEL-NOTE")

    def test_overdue_reminder(self):
        from lending.notifications import send_overdue_reminder

        mail.outbox.clear()
        send_overdue_reminder(self.booking, [self.item], [])
        self._assert_both("REMIND-NOTE")


class BookingHorizonTests(APITestCase):
    """A pool's max_booking_months caps how far ahead bookings are possible."""

    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")
        self.product_type = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(
            product_type=self.product_type, title="GoPro"
        )
        # Horizon of 1 month, open every day, no lead time.
        self.pool = ResourcePool.objects.create(
            name="DigiLab", pool_id="DigiLab", closed_weekdays=[],
            max_booking_months=1,
        )
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DigiLab-001", qr_code_id="QR-1",
        )

    def test_within_horizon_is_available(self):
        start = timezone.now() + timedelta(days=10)
        result = availability(self.product, start, start + timedelta(days=1))
        self.assertEqual(result["available"], 1)

    def test_beyond_horizon_is_unavailable(self):
        start = timezone.now() + timedelta(days=80)  # > 1 month ahead
        result = availability(self.product, start, start + timedelta(days=1))
        self.assertEqual(result["available"], 0)

    def test_cart_rejects_booking_beyond_horizon(self):
        self.client.force_login(self.borrower)
        start = (timezone.now() + timedelta(days=80)).date().isoformat()
        end = (timezone.now() + timedelta(days=81)).date().isoformat()
        res = self.client.post(
            "/api/cart/items/",
            {"product": self.product.id, "start": start, "end": end},
            format="json",
        )
        self.assertEqual(res.status_code, 409)

    def test_calendar_marks_beyond_horizon_days_closed(self):
        from .services import availability_per_day

        far = (timezone.now() + timedelta(days=80)).date()
        days = availability_per_day(self.product, far, far + timedelta(days=1))
        self.assertTrue(days[0]["closed"])


class BlockManagementTests(APITestCase):
    """Admins manage all block days; lenders only their own pools'."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.pool = ResourcePool.objects.create(name="DigiLab", pool_id="DigiLab")
        self.other_pool = ResourcePool.objects.create(name="Other", pool_id="OTHER")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)

    def test_admin_creates_and_lists_all_blocks(self):
        self.client.force_login(self.admin)
        created = self.client.post(
            "/api/manage/blocks/",
            {"start_date": "2026-08-01", "end_date": "2026-08-14",
             "reason": "Betriebsferien"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["scope"], "system")
        listing = self.client.get("/api/manage/blocks/")
        self.assertEqual(listing.json()["count"], 1)

    def test_lender_cannot_create_system_block(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/blocks/", {"start_date": "2026-08-01"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_lender_blocks_only_own_pool(self):
        self.client.force_login(self.lender)
        ok = self.client.post(
            "/api/manage/blocks/",
            {"start_date": "2026-08-01", "resource_pool": self.pool.id},
            format="json",
        )
        self.assertEqual(ok.status_code, 201)
        forbidden = self.client.post(
            "/api/manage/blocks/",
            {"start_date": "2026-08-01", "resource_pool": self.other_pool.id},
            format="json",
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_lender_list_scoped_to_own_pools(self):
        Block.objects.create(
            period=DateTimeTZRange(
                timezone.make_aware(timezone.datetime(2026, 8, 1)),
                timezone.make_aware(timezone.datetime(2026, 8, 2)),
            ),
            resource_pool=self.other_pool,
        )
        self.client.force_login(self.lender)
        self.assertEqual(self.client.get("/api/manage/blocks/").json()["count"], 0)

    def test_admin_deletes_block(self):
        block = Block.objects.create(
            period=DateTimeTZRange(
                timezone.make_aware(timezone.datetime(2026, 8, 1)),
                timezone.make_aware(timezone.datetime(2026, 8, 2)),
            ),
        )
        self.client.force_login(self.admin)
        res = self.client.delete(f"/api/manage/blocks/{block.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Block.objects.filter(pk=block.id).exists())


class HolidaySettingTests(APITestCase):
    """Setting the region loads holidays across the booking horizon."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        ResourcePool.objects.create(
            name="DigiLab", pool_id="DigiLab", max_booking_months=24
        )

    def test_put_setting_loads_holidays(self):
        self.client.force_login(self.admin)
        res = self.client.put(
            "/api/manage/holiday-setting/",
            {"country": "DE", "subdivision": "NI"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json()["loaded"], 0)
        # Holidays became system-wide blocks.
        self.assertTrue(
            Block.objects.filter(reason__startswith="Holiday:").exists()
        )

    def test_requires_admin(self):
        borrower = User.objects.create_user(username="bob")
        self.client.force_login(borrower)
        self.assertEqual(
            self.client.get("/api/manage/holiday-setting/").status_code, 403
        )


class ProductStatsTests(APITestCase):
    """Per-product lending statistics for lenders (own pools) and admins."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.create_reservation = create_reservation
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(username="alice")

        self.pt = ProductType.objects.create(name="Camera")
        self.pool_a = ResourcePool.objects.create(
            name="A", pool_id="A", closed_weekdays=[], max_booking_months=0
        )
        self.pool_b = ResourcePool.objects.create(
            name="B", pool_id="B", closed_weekdays=[], max_booking_months=0
        )
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool_a)

        self.popular = Product.objects.create(product_type=self.pt, title="Popular")
        self.rare = Product.objects.create(product_type=self.pt, title="Rare")
        self.res_a = [
            Resource.objects.create(
                product=self.popular, resource_pool=self.pool_a,
                inventory_number=f"A-{i}", qr_code_id=f"QRA-{i}",
            )
            for i in range(3)
        ]
        self.res_b = Resource.objects.create(
            product=self.popular, resource_pool=self.pool_b,
            inventory_number="B-1", qr_code_id="QRB-1",
        )
        self.res_rare = Resource.objects.create(
            product=self.rare, resource_pool=self.pool_a,
            inventory_number="A-rare", qr_code_id="QRA-rare",
        )
        self.now = timezone.now()
        self.day = timedelta(days=1)

    def _book(self, resource, days_ago):
        start = self.now - self.day * days_ago
        self.create_reservation(
            self.borrower, [(resource, start, start + self.day)],
            status=Booking.Status.CONFIRMED,
        )

    def test_admin_sees_all_pools_ranked(self):
        # Popular: 3 bookings (pool A) + 1 (pool B); Rare: 1.
        self._book(self.res_a[0], 1)
        self._book(self.res_a[1], 2)
        self._book(self.res_a[2], 3)
        self._book(self.res_b, 4)
        self._book(self.res_rare, 5)

        self.client.force_login(self.admin)
        res = self.client.get("/api/manage/stats/products/")
        self.assertEqual(res.status_code, 200)
        products = res.json()["products"]
        self.assertEqual(products[0]["title"], "Popular")
        self.assertEqual(products[0]["bookings"], 4)
        self.assertEqual(products[1]["title"], "Rare")
        self.assertEqual(products[1]["bookings"], 1)
        # Admin can filter by pool.
        scoped = self.client.get(
            "/api/manage/stats/products/", {"pool": self.pool_b.id}
        ).json()["products"]
        self.assertEqual(scoped[0]["bookings"], 1)  # only pool B's booking

    def test_lender_limited_to_own_pool(self):
        self._book(self.res_a[0], 1)  # pool A (lender's)
        self._book(self.res_b, 2)  # pool B (not lender's)
        self.client.force_login(self.lender)
        body = self.client.get("/api/manage/stats/products/").json()
        popular = next(p for p in body["products"] if p["title"] == "Popular")
        self.assertEqual(popular["bookings"], 1)  # pool B excluded
        self.assertEqual([p["name"] for p in body["pools"]], ["A"])

    def test_requires_lender_or_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/stats/products/").status_code, 403
        )

    def test_trend_compares_previous_window(self):
        # Window = last 10 days; previous = the 10 days before that.
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        # current: 1 booking 2 days ago; previous: 2 bookings ~12-13 days ago.
        for resource, offset in [
            (self.res_a[0], -2),
            (self.res_a[1], -12),
            (self.res_a[2], -13),
        ]:
            start = now + timedelta(days=offset)
            self.create_reservation(
                self.borrower, [(resource, start, start + timedelta(days=1))],
                status=Booking.Status.RETURNED,
            )
        self.client.force_login(self.admin)
        to = timezone.localdate().isoformat()
        frm = (timezone.localdate() - timedelta(days=9)).isoformat()
        body = self.client.get(
            "/api/manage/stats/products/", {"from": frm, "to": to}
        ).json()
        popular = next(p for p in body["products"] if p["title"] == "Popular")
        self.assertEqual(popular["bookings"], 1)
        self.assertEqual(popular["prev_bookings"], 2)
        self.assertEqual(popular["trend"], -1)


class ProductTimeseriesTests(APITestCase):
    """Per-product usage-over-time series, bucketed by day/week/month."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.create_reservation = create_reservation
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="GoPro")
        self.pool = ResourcePool.objects.create(
            name="A", pool_id="A", closed_weekdays=[], max_booking_months=0
        )
        self.resources = [
            Resource.objects.create(
                product=self.product, resource_pool=self.pool,
                inventory_number=f"A-{i}", qr_code_id=f"QRA-{i}",
            )
            for i in range(5)
        ]
        self.now = timezone.now()
        self.day = timedelta(days=1)

    def test_seeds_never_borrowed_products_in_stats(self):
        # No bookings at all -> product still appears with zero counts.
        self.client.force_login(self.admin)
        products = self.client.get("/api/manage/stats/products/").json()["products"]
        gopro = next(p for p in products if p["title"] == "GoPro")
        self.assertEqual(gopro["bookings"], 0)

    def test_weekly_series_counts_by_pickup(self):
        from datetime import timedelta

        from django.utils import timezone

        # Two bookings ~3 days ago, one ~10 days ago.
        for resource, days_ago in [
            (self.resources[0], 3),
            (self.resources[1], 3),
            (self.resources[2], 10),
        ]:
            start = timezone.now() - timedelta(days=days_ago)
            self.create_reservation(
                self.borrower, [(resource, start, start + timedelta(days=1))],
                status=Booking.Status.RETURNED,
            )
        self.client.force_login(self.admin)
        res = self.client.get(
            f"/api/manage/stats/products/{self.product.id}/timeseries/",
            {"bucket": "week"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["bucket"], "week")
        total = sum(point["bookings"] for point in body["series"])
        self.assertEqual(total, 3)
        # Continuous, zero-filled series (90-day default ≈ 13–14 weekly buckets).
        self.assertGreaterEqual(len(body["series"]), 12)

    def test_bad_bucket_rejected(self):
        self.client.force_login(self.admin)
        res = self.client.get(
            f"/api/manage/stats/products/{self.product.id}/timeseries/",
            {"bucket": "fortnight"},
        )
        self.assertEqual(res.status_code, 400)

    def test_requires_lender_or_admin(self):
        self.client.force_login(self.borrower)
        res = self.client.get(
            f"/api/manage/stats/products/{self.product.id}/timeseries/"
        )
        self.assertEqual(res.status_code, 403)


class LendingOverviewTests(APITestCase):
    """Pool→Product→borrower overview, scoped to the pools one manages."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.create_reservation = create_reservation
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.alice = User.objects.create_user(
            username="alice", first_name="Alice", last_name="A"
        )
        self.bob = User.objects.create_user(username="bob")

        pt = ProductType.objects.create(name="Camera")
        self.pool_a = ResourcePool.objects.create(
            name="A", pool_id="A", closed_weekdays=[], max_booking_months=0
        )
        self.pool_b = ResourcePool.objects.create(
            name="B", pool_id="B", closed_weekdays=[], max_booking_months=0
        )
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool_a)

        self.cam = Product.objects.create(product_type=pt, title="Camera X")
        self.res_a = Resource.objects.create(
            product=self.cam, resource_pool=self.pool_a,
            inventory_number="A-1", qr_code_id="QR-A-1",
        )
        self.res_b = Resource.objects.create(
            product=self.cam, resource_pool=self.pool_b,
            inventory_number="B-1", qr_code_id="QR-B-1",
        )
        now = timezone.now()
        self.create_reservation(
            self.alice, [(self.res_a, now, now + timedelta(days=1))],
            status=Booking.Status.CONFIRMED,
        )
        self.create_reservation(
            self.bob, [(self.res_b, now, now + timedelta(days=1))],
            status=Booking.Status.RETURNED,
        )

    def test_admin_tree_groups_pools_products_resources(self):
        self.client.force_login(self.admin)
        res = self.client.get("/api/manage/borrowers/")
        self.assertEqual(res.status_code, 200)
        pools = res.json()["pools"]
        self.assertEqual([p["name"] for p in pools], ["A", "B"])
        product = pools[0]["products"][0]
        self.assertEqual(product["title"], "Camera X")
        self.assertEqual(product["booking_count"], 1)
        resource = product["resources"][0]
        self.assertEqual(resource["inventory_number"], "A-1")
        self.assertEqual(resource["booking_count"], 1)
        # The tree itself carries no booking history.
        self.assertNotIn("bookings", product)

    def test_lender_tree_scoped_to_managed_pool(self):
        self.client.force_login(self.lender)
        pools = self.client.get("/api/manage/borrowers/").json()["pools"]
        self.assertEqual([p["name"] for p in pools], ["A"])

    def test_resource_borrowers_paginated_and_scoped(self):
        self.client.force_login(self.admin)
        res = self.client.get(f"/api/manage/borrowers/resources/{self.res_a.id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["borrower"], "alice")
        self.assertEqual(body["results"][0]["borrower_name"], "Alice A")

    def test_lender_cannot_read_foreign_resource(self):
        self.client.force_login(self.lender)
        # res_b lives in pool B, which the lender does not manage.
        res = self.client.get(f"/api/manage/borrowers/resources/{self.res_b.id}/")
        self.assertEqual(res.status_code, 404)

    def test_resource_borrowers_pages(self):
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        for i in range(12):  # 12 bookings on res_a across distinct days
            start = now - timedelta(days=10 + i)
            self.create_reservation(
                self.alice, [(self.res_a, start, start + timedelta(days=1))],
                status=Booking.Status.RETURNED,
            )
        self.client.force_login(self.admin)
        page1 = self.client.get(
            f"/api/manage/borrowers/resources/{self.res_a.id}/"
        ).json()
        self.assertEqual(page1["count"], 13)  # 12 + the setUp booking
        self.assertEqual(len(page1["results"]), 10)
        self.assertIsNotNone(page1["next"])

    def test_requires_lender_or_admin(self):
        self.client.force_login(self.alice)
        self.assertEqual(
            self.client.get("/api/manage/borrowers/").status_code, 403
        )


class DefectHandlingTests(APITestCase):
    """Marking a resource defective rebooks or notifies (concept §3.6)."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import PoolMembership

        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(
            username="alice", email="alice@uni.test"
        )
        self.pool = ResourcePool.objects.create(
            name="A", pool_id="A", closed_weekdays=[], max_booking_months=0
        )
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="Cam")
        self.r1 = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="A-1", qr_code_id="QR-A-1",
        )
        self.r2 = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="A-2", qr_code_id="QR-A-2",
        )
        self.start = timezone.now() + timedelta(days=2)
        self.end = self.start + timedelta(days=1)

    def _defect(self, resource):
        self.client.force_login(self.lender)
        return self.client.post(
            f"/api/manage/resources/{resource.id}/defective/",
            {"note": "broken lens"},
            format="json",
        )

    def test_future_booking_is_rebooked_to_free_unit(self):
        from lending.models import BookingItem

        booking = create_reservation(
            self.borrower, [(self.r1, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        res = self._defect(self.r1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["rebooked"], 1)
        self.assertEqual(res.json()["unfulfilled"], 0)
        item = booking.items.get()
        self.assertEqual(item.resource_id, self.r2.id)  # moved to the free unit
        self.assertEqual(len(mail.outbox), 0)  # nothing to notify

    def test_borrower_notified_when_no_replacement(self):
        from datetime import timedelta

        # Both units booked for the same window -> no free replacement for r1.
        create_reservation(
            self.borrower, [(self.r1, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        create_reservation(
            self.borrower, [(self.r2, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        mail.outbox.clear()
        res = self._defect(self.r1)
        self.assertEqual(res.json()["rebooked"], 0)
        self.assertEqual(res.json()["unfulfilled"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("alice@uni.test", mail.outbox[0].to)

    def test_past_bookings_are_left_alone(self):
        from datetime import timedelta

        from django.utils import timezone

        past_start = timezone.now() - timedelta(days=5)
        booking = create_reservation(
            self.borrower, [(self.r1, past_start, past_start + timedelta(days=1))],
            status=Booking.Status.RETURNED,
        )
        res = self._defect(self.r1)
        self.assertEqual(res.json()["rebooked"], 0)
        booking.items.get().refresh_from_db()
        self.assertEqual(booking.items.get().resource_id, self.r1.id)  # untouched

    def test_review_command_emails_lender(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        self.lender.email = "len@uni.test"
        self.lender.save()
        # Make r1 defective with an old defect record.
        from lending.services import mark_resource_defective

        mark_resource_defective(self.r1, "broken")
        defect = self.r1.defects.get(resolved_at__isnull=True)
        defect.created_at = timezone.now() - timedelta(days=30)
        defect.save(update_fields=["created_at"])
        mail.outbox.clear()
        call_command("review_defects", "--days", "14")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("len@uni.test", mail.outbox[0].to)

    def test_defect_review_email_is_german_for_pool_email_language_de(self):
        from django.utils import timezone

        from lending.notifications import send_defect_review

        self.pool.email_language = "de"
        self.pool.save(update_fields=["email_language"])
        mail.outbox.clear()
        since = timezone.now().date()
        send_defect_review("len@uni.test", self.pool, [(self.r1, since)])
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("überprüft werden", msg.subject)
        self.assertIn("außer Betrieb", msg.body)
        self.assertIn("kein Hinweis", msg.body)

    def test_defect_review_email_is_english_for_pool_email_language_en(self):
        from django.utils import timezone

        from lending.notifications import send_defect_review

        self.pool.email_language = "en"
        self.pool.save(update_fields=["email_language"])
        mail.outbox.clear()
        since = timezone.now().date()
        send_defect_review("len@uni.test", self.pool, [(self.r1, since)])
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("need review", msg.subject)
        self.assertIn("return them to service", msg.body)
        self.assertIn("no note", msg.body)


class DefectStatsTests(APITestCase):
    """Defect statistics, scoped to the requester's pools."""

    def setUp(self):
        from django.utils import timezone

        from accounts.models import PoolMembership
        from catalog.models import ResourceDefect

        self.ResourceDefect = ResourceDefect
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(username="alice")
        self.pool_a = ResourcePool.objects.create(name="A", pool_id="A")
        self.pool_b = ResourcePool.objects.create(name="B", pool_id="B")
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool_a)
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="Cam")

        # The defect-tracking signal opens a record when status=defective; plus
        # one past (resolved) record -> 2 incidents on A-1.
        self.ra = Resource.objects.create(
            product=self.product, resource_pool=self.pool_a, status="defective",
            inventory_number="A-1", qr_code_id="QR-A-1",
        )
        ResourceDefect.objects.create(
            resource=self.ra, note="y", resolved_at=timezone.now()
        )
        self.rb = Resource.objects.create(
            product=self.product, resource_pool=self.pool_b,
            inventory_number="B-1", qr_code_id="QR-B-1",
        )
        ResourceDefect.objects.create(
            resource=self.rb, note="z", resolved_at=timezone.now()
        )

    def test_admin_sees_all_pools(self):
        self.client.force_login(self.admin)
        body = self.client.get("/api/manage/stats/defects/").json()
        self.assertEqual(body["currently_defective"], 1)
        self.assertEqual(body["ever_defective"], 2)  # A-1 and B-1
        self.assertEqual(body["incidents"], 3)  # 2 on A-1 + 1 on B-1
        self.assertEqual(body["products"][0]["incidents"], 3)

    def test_lender_scoped_to_own_pool(self):
        self.client.force_login(self.lender)
        body = self.client.get("/api/manage/stats/defects/").json()
        self.assertEqual(body["incidents"], 2)  # only pool A
        self.assertEqual(body["ever_defective"], 1)

    def test_requires_lender_or_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/stats/defects/").status_code, 403
        )


class SetBookingTests(APITestCase):
    """Borrower set availability/booking: same-pool, scarcest, mixed units."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from catalog.models import ProductSet

        self.ProductSet = ProductSet
        self.borrower = User.objects.create_user(username="alice")
        pt_room = ProductType.objects.create(name="Room")
        pt_mic = ProductType.objects.create(name="Mic")
        # One pool that holds both products.
        self.pool = ResourcePool.objects.create(
            name="Studio", pool_id="STU", closed_weekdays=[], max_booking_months=0
        )
        self.other_pool = ResourcePool.objects.create(
            name="Other", pool_id="OTH", closed_weekdays=[], max_booking_months=0
        )
        # Hourly product (1 unit) — the scarce one.
        self.room = Product.objects.create(
            product_type=pt_room, title="Studio Room",
            lending_type="hours", max_duration=4,
        )
        Resource.objects.create(
            product=self.room, resource_pool=self.pool,
            inventory_number="STU-room-1", qr_code_id="QR-room-1",
        )
        # Daily product (2 units).
        self.mic = Product.objects.create(
            product_type=pt_mic, title="Mic", lending_type="days", max_duration=7,
        )
        for i in range(2):
            Resource.objects.create(
                product=self.mic, resource_pool=self.pool,
                inventory_number=f"STU-mic-{i}", qr_code_id=f"QR-mic-{i}",
            )
        self.set = ProductSet.objects.create(
            name="Podcast kit", resource_pool=self.pool
        )
        self.set.products.add(self.room, self.mic)

        self.start = timezone.now() + timedelta(days=2)
        self.start = self.start.replace(hour=10, minute=0, second=0, microsecond=0)
        self.end = self.start + timedelta(hours=2)

    def test_set_detail_exposes_products_pools_and_durations(self):
        res = self.client.get(f"/api/sets/{self.set.id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["products"]), 2)
        self.assertEqual(body["lending_type"], "hours")  # mixed -> hourly drives
        self.assertEqual(body["max_duration"], 4)  # min(7*24, 4)
        self.assertEqual(body["pool"]["name"], "Studio")

    def test_availability_follows_scarcest_product(self):
        self.client.force_login(self.borrower)
        url = f"/api/sets/{self.set.id}/availability/"
        params = {"start": self.start.isoformat(), "end": self.end.isoformat()}
        body = self.client.get(url, params).json()
        self.assertEqual(body["available"], 1)  # room has only 1 unit
        # Occupy the room for that window -> set unavailable, room is scarcest.
        create_reservation(
            self.borrower,
            [(self.room.resources.get(), self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        body = self.client.get(url, params).json()
        self.assertEqual(body["available"], 0)
        self.assertEqual(body["scarcest"], "Studio Room")

    def test_set_without_pool_is_not_bookable(self):
        self.set.resource_pool = None
        self.set.save()
        self.client.force_login(self.borrower)
        res = self.client.get(
            f"/api/sets/{self.set.id}/availability/",
            {"start": self.start.isoformat(), "end": self.end.isoformat()},
        )
        self.assertEqual(res.status_code, 404)

    def test_add_set_to_cart_books_all_with_daily_rounding(self):
        self.client.force_login(self.borrower)
        res = self.client.post(
            "/api/cart/sets/",
            {"set": self.set.id,
             "start": self.start.isoformat(), "end": self.end.isoformat()},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        cart = Booking.objects.get(borrower=self.borrower, status=Booking.Status.CART)
        items = {i.resource.product.title: i for i in cart.items.all()}
        self.assertEqual(set(items), {"Studio Room", "Mic"})
        # Hourly product keeps the exact 2-hour window.
        room_item = items["Studio Room"]
        self.assertEqual(
            (room_item.period.upper - room_item.period.lower).total_seconds(), 7200
        )
        # Daily product is rounded up to a whole day (24h).
        mic_item = items["Mic"]
        self.assertEqual(
            (mic_item.period.upper - mic_item.period.lower).total_seconds(), 86400
        )

    def test_product_detail_lists_its_sets(self):
        res = self.client.get(f"/api/products/{self.mic.id}/")
        self.assertEqual([s["name"] for s in res.json()["sets"]], ["Podcast kit"])

    def test_section_detail_exposes_assigned_sets(self):
        from catalog.models import Section

        section = Section.objects.create(title="Media")
        section.sets.add(self.set)
        body = self.client.get(f"/api/sections/{section.id}/").json()
        self.assertEqual([s["name"] for s in body["sets"]], ["Podcast kit"])
        self.assertEqual(body["sets"][0]["product_count"], 2)

    def test_per_day_calendar_is_min_over_products(self):
        from datetime import timedelta

        from django.utils import timezone

        from lending.services import set_availability_per_day

        start = (timezone.now() + timedelta(days=5)).date()
        days = set_availability_per_day(self.set, start, start + timedelta(days=2))
        # Room has 1 unit, Mic has 2 -> the set is capped at 1 per day.
        self.assertTrue(days and all(d["available"] == 1 for d in days))


class WalkinLendingTests(APITestCase):
    """Lender walk-in lending (concept §6.4): bypasses lead time, picks borrower."""

    def setUp(self):
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(
            username="alice", first_name="Alice", last_name="Borrow"
        )
        self.outsider = User.objects.create_user(username="bob")
        # A pool with a long lead time so self-service "now" bookings are blocked.
        self.pool = ResourcePool.objects.create(
            name="DeskPool", pool_id="DESK", closed_weekdays=[],
            max_booking_months=0, lead_time_hours=48,
        )
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        self.other_pool = ResourcePool.objects.create(
            name="OtherPool", pool_id="OTH", closed_weekdays=[], max_booking_months=0
        )
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(
            product_type=pt, title="GoPro", lending_type="days"
        )
        self.resource = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DESK-001", qr_code_id="QR-1",
        )
        self.start = timezone.now()
        self.end = self.start + timedelta(days=1)

    def _payload(self, **overrides):
        data = {
            "borrower": self.borrower.id,
            "pool": self.pool.id,
            "hand_out": True,
            "items": [
                {
                    "product": self.product.id,
                    "start": self.start.isoformat(),
                    "end": self.end.isoformat(),
                }
            ],
        }
        data.update(overrides)
        return data

    def test_borrower_cannot_create_walkin(self):
        self.client.force_login(self.borrower)
        res = self.client.post("/api/manage/walkin/", self._payload(), format="json")
        self.assertEqual(res.status_code, 403)

    def test_walkin_hands_out_immediately_bypassing_lead_time(self):
        self.client.force_login(self.lender)
        res = self.client.post("/api/manage/walkin/", self._payload(), format="json")
        self.assertEqual(res.status_code, 201, res.content)
        booking = Booking.objects.get(borrower=self.borrower)
        self.assertEqual(booking.status, Booking.Status.HANDED_OUT)
        item = booking.items.get()
        self.assertEqual(item.resource, self.resource)
        self.assertIsNotNone(item.handed_out_at)

    def test_walkin_stores_note(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/walkin/",
            self._payload(note="  Grund: Seminar  "),
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        booking = Booking.objects.get(borrower=self.borrower)
        self.assertEqual(booking.note, "Grund: Seminar")

    def test_walkin_reserve_only_is_confirmed(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/walkin/", self._payload(hand_out=False), format="json"
        )
        self.assertEqual(res.status_code, 201)
        booking = Booking.objects.get(borrower=self.borrower)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertIsNone(booking.items.get().handed_out_at)

    def test_walkin_returns_201_when_mail_dispatch_raises(self):
        # I1: same rationale as the confirm endpoint — a mail failure must
        # not turn an otherwise successful walk-in lending into a 500.
        from unittest.mock import patch

        self.client.force_login(self.lender)
        with patch(
            "lending.views.dispatch_confirmation_mails",
            side_effect=RuntimeError("smtp down"),
        ):
            res = self.client.post(
                "/api/manage/walkin/", self._payload(hand_out=False), format="json"
            )
        self.assertEqual(res.status_code, 201, res.content)
        booking = Booking.objects.get(borrower=self.borrower)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertIsNone(booking.confirmation_mailed_at)

    def test_walkin_rejects_pool_not_managed(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/walkin/", self._payload(pool=self.other_pool.id), format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_walkin_rejects_unavailable_product(self):
        create_reservation(
            self.borrower,
            [(self.resource, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        self.client.force_login(self.lender)
        res = self.client.post("/api/manage/walkin/", self._payload(), format="json")
        self.assertEqual(res.status_code, 409)

    def test_walkin_rejects_suspended_borrower(self):
        self.borrower.blocked_permanently = True
        self.borrower.save()
        self.client.force_login(self.lender)
        res = self.client.post("/api/manage/walkin/", self._payload(), format="json")
        self.assertEqual(res.status_code, 400)

    def test_context_lists_only_managed_pools(self):
        self.client.force_login(self.lender)
        body = self.client.get("/api/manage/walkin/context/").json()
        self.assertEqual([p["name"] for p in body["pools"]], ["DeskPool"])

    def test_products_lists_pool_stock(self):
        self.client.force_login(self.lender)
        body = self.client.get(
            f"/api/manage/walkin/products/?pool={self.pool.id}"
        ).json()
        self.assertEqual([p["title"] for p in body["products"]], ["GoPro"])

    def test_borrower_search_finds_by_name(self):
        self.client.force_login(self.lender)
        body = self.client.get("/api/manage/borrower-search/?q=alice").json()
        self.assertEqual([u["username"] for u in body], ["alice"])
        self.assertEqual(body[0]["full_name"], "Alice Borrow")

    def test_walkin_calendar_bypasses_lead_time(self):
        self.client.force_login(self.lender)
        today = timezone.localdate()
        res = self.client.get(
            "/api/manage/walkin/availability/calendar/",
            {
                "pool": self.pool.id,
                "product": self.product.id,
                "from": today.isoformat(),
                "to": (today + timedelta(days=2)).isoformat(),
            },
        )
        self.assertEqual(res.status_code, 200)
        days = res.json()["days"]
        # Today is bookable despite the pool's 48h lead time.
        self.assertEqual(days[0]["date"], today.isoformat())
        self.assertEqual(days[0]["available"], 1)

    def test_walkin_calendar_rejects_unmanaged_pool(self):
        self.client.force_login(self.lender)
        today = timezone.localdate()
        res = self.client.get(
            "/api/manage/walkin/availability/calendar/",
            {
                "pool": self.other_pool.id,
                "product": self.product.id,
                "from": today.isoformat(),
                "to": (today + timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(res.status_code, 403)

    def _resource_params(self):
        return {
            "pool": self.pool.id,
            "product": self.product.id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }

    def test_resources_endpoint_flags_conflicts(self):
        self.client.force_login(self.lender)
        body = self.client.get(
            "/api/manage/walkin/resources/", self._resource_params()
        ).json()
        self.assertEqual(
            [r["inventory_number"] for r in body["resources"]], ["DESK-001"]
        )
        self.assertFalse(body["resources"][0]["conflict"])
        # Occupy the unit for that window -> it is now flagged as a conflict.
        create_reservation(
            self.borrower,
            [(self.resource, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        body = self.client.get(
            "/api/manage/walkin/resources/", self._resource_params()
        ).json()
        self.assertTrue(body["resources"][0]["conflict"])

    def test_walkin_hands_out_chosen_resource(self):
        Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="DESK-002", qr_code_id="QR-2",
        )
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/walkin/",
            self._payload(
                items=[
                    {
                        "product": self.product.id,
                        "resource": self.resource.id,
                        "start": self.start.isoformat(),
                        "end": self.end.isoformat(),
                    }
                ]
            ),
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        booking = Booking.objects.get(borrower=self.borrower)
        self.assertEqual(booking.items.get().resource, self.resource)

    def test_walkin_rejects_conflicting_resource(self):
        create_reservation(
            self.borrower,
            [(self.resource, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )
        self.client.force_login(self.lender)
        res = self.client.post(
            "/api/manage/walkin/",
            self._payload(
                items=[
                    {
                        "product": self.product.id,
                        "resource": self.resource.id,
                        "start": self.start.isoformat(),
                        "end": self.end.isoformat(),
                    }
                ]
            ),
            format="json",
        )
        self.assertEqual(res.status_code, 409)


class QrHandoutTests(APITestCase):
    """QR device handout (concept §6.2): lookup, resolve, swap, ad-hoc, email QR."""

    def setUp(self):
        self.lender = User.objects.create_user(username="len")
        self.borrower = User.objects.create_user(username="alice", email="a@x.test")
        self.pool = ResourcePool.objects.create(
            name="DeskPool", pool_id="DESK", closed_weekdays=[], max_booking_months=0
        )
        PoolMembership.objects.create(user=self.lender, resource_pool=self.pool)
        self.other_pool = ResourcePool.objects.create(
            name="Other", pool_id="OTH", closed_weekdays=[], max_booking_months=0
        )
        pt_a = ProductType.objects.create(name="Camera")
        pt_b = ProductType.objects.create(name="Mic")
        self.cam = Product.objects.create(product_type=pt_a, title="Camera", lending_type="days")
        self.mic = Product.objects.create(product_type=pt_b, title="Mic", lending_type="days")
        self.cam1 = Resource.objects.create(
            product=self.cam, resource_pool=self.pool,
            inventory_number="DESK-cam-1", qr_code_id="QR-cam-1",
        )
        self.cam2 = Resource.objects.create(
            product=self.cam, resource_pool=self.pool,
            inventory_number="DESK-cam-2", qr_code_id="QR-cam-2",
        )
        self.mic1 = Resource.objects.create(
            product=self.mic, resource_pool=self.pool,
            inventory_number="DESK-mic-1", qr_code_id="QR-mic-1",
        )
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(days=1)
        self.booking = create_reservation(
            self.borrower, [(self.cam1, self.start, self.end)],
            status=Booking.Status.CONFIRMED,
        )

    def test_lookup_by_code_scoped(self):
        self.client.force_login(self.lender)
        res = self.client.get(f"/api/manage/bookings/by-code/?code={self.booking.code}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], self.booking.code)
        # Unknown code -> 404.
        self.assertEqual(
            self.client.get("/api/manage/bookings/by-code/?code=R-99999").status_code,
            404,
        )

    def test_lookup_requires_lender(self):
        self.client.force_login(self.borrower)
        res = self.client.get(f"/api/manage/bookings/by-code/?code={self.booking.code}")
        self.assertEqual(res.status_code, 403)

    def test_resolve_resource_by_qr(self):
        self.client.force_login(self.lender)
        body = self.client.get(
            "/api/manage/bookings/resolve-resource/?qr=QR-cam-2"
        ).json()
        self.assertEqual(body["inventory_number"], "DESK-cam-2")
        self.assertEqual(body["product"], self.cam.id)

    def test_resolve_resource_outside_pool_is_404(self):
        far = Resource.objects.create(
            product=self.cam, resource_pool=self.other_pool,
            inventory_number="OTH-cam-9", qr_code_id="QR-cam-9",
        )
        self.client.force_login(self.lender)
        self.assertEqual(
            self.client.get(
                f"/api/manage/bookings/resolve-resource/?qr={far.qr_code_id}"
            ).status_code,
            404,
        )

    def test_swap_same_product(self):
        self.client.force_login(self.lender)
        item = self.booking.items.get()
        res = self.client.post(
            f"/api/manage/bookings/{self.booking.id}/swap/",
            {"item_id": item.id, "resource": self.cam2.id}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        item.refresh_from_db()
        self.assertEqual(item.resource, self.cam2)

    def test_swap_rejects_other_product(self):
        self.client.force_login(self.lender)
        item = self.booking.items.get()
        res = self.client.post(
            f"/api/manage/bookings/{self.booking.id}/swap/",
            {"item_id": item.id, "resource": self.mic1.id}, format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_add_adhoc_item(self):
        self.client.force_login(self.lender)
        res = self.client.post(
            f"/api/manage/bookings/{self.booking.id}/add-item/",
            {"resource": self.mic1.id}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.booking.items.count(), 2)
        added = self.booking.items.get(resource=self.mic1)
        self.assertEqual(added.period.lower, self.start)

    def test_build_ics_event_per_pool(self):
        from lending.ics import build_ics

        ics = build_ics(self.booking)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 1)  # one pickup pool
        # A day booking is an all-day event (VALUE=DATE), not a timed one.
        self.assertIn("DTSTART;VALUE=DATE:", ics)
        self.assertIn("DTEND;VALUE=DATE:", ics)
        self.assertIn(self.booking.code, ics)

    def test_confirmation_email_has_qr_attachment(self):
        from django.core import mail

        pending = create_reservation(
            self.borrower, [(self.cam2, self.start, self.end)],
            status=Booking.Status.PENDING,
        )
        self.client.force_login(self.lender)
        res = self.client.post(f"/api/manage/bookings/{pending.id}/confirm/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mail.outbox)
        attachments = mail.outbox[-1].attachments
        mimetypes = {a[2] for a in attachments}
        # Pickup QR (PNG) and a calendar entry (.ics) are both attached.
        self.assertIn("image/png", mimetypes)
        self.assertIn("text/calendar", mimetypes)
        ics = next(a for a in attachments if a[2] == "text/calendar")
        self.assertIn("BEGIN:VEVENT", ics[1])
        self.assertIn(pending.code, ics[1])


class PickupDeeplinkTests(APITestCase):
    """Borrower booking-by-code lookup for the pickup deeplink (concept §6.2)."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice")
        self.bob = User.objects.create_user(username="bob")
        pt = ProductType.objects.create(name="Camera")
        product = Product.objects.create(product_type=pt, title="Camera", lending_type="days")
        pool = ResourcePool.objects.create(
            name="Pool", pool_id="P", closed_weekdays=[], max_booking_months=0
        )
        resource = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="P-1", qr_code_id="QR-1",
        )
        start = timezone.now() + timedelta(days=1)
        self.booking = create_reservation(
            self.alice, [(resource, start, start + timedelta(days=1))],
            status=Booking.Status.CONFIRMED,
        )

    def test_owner_can_fetch_by_code(self):
        self.client.force_login(self.alice)
        res = self.client.get(f"/api/bookings/by-code/?code={self.booking.code}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], self.booking.code)

    def test_other_user_gets_404(self):
        self.client.force_login(self.bob)
        res = self.client.get(f"/api/bookings/by-code/?code={self.booking.code}")
        self.assertEqual(res.status_code, 404)

    def test_unknown_code_404(self):
        self.client.force_login(self.alice)
        self.assertEqual(
            self.client.get("/api/bookings/by-code/?code=R-99999").status_code, 404
        )

    def test_pickup_url_contains_code(self):
        from lending.qr import pickup_qr_url

        self.assertIn(f"/bookings/{self.booking.code}", pickup_qr_url(self.booking))


class EmailLanguageTests(APITestCase):
    """Notification emails are sent in the borrower's chosen language (i18n)."""

    def _booking(self, language):
        borrower = User.objects.create_user(
            username=f"u{language}", email=f"{language}@x.test", language=language
        )
        pt = ProductType.objects.create(name=f"Cam{language}")
        product = Product.objects.create(product_type=pt, title="GoPro", lending_type="days")
        pool = ResourcePool.objects.create(
            name=f"Pool{language}", pool_id=f"P{language}", closed_weekdays=[],
            max_booking_months=0,
        )
        resource = Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number=f"P{language}-1", qr_code_id=f"QR{language}-1",
        )
        start = timezone.now() + timedelta(days=1)
        return create_reservation(
            borrower, [(resource, start, start + timedelta(days=1))],
            status=Booking.Status.CONFIRMED,
        )

    def test_german_confirmation_email(self):
        from django.core import mail
        from lending.notifications import send_confirmation_email

        send_confirmation_email(self._booking("de"))
        self.assertTrue(mail.outbox)
        msg = mail.outbox[-1]
        self.assertIn("bestätigt", msg.subject)        # "confirmed"
        self.assertIn("Hallo", msg.body)               # greeting

    def test_english_confirmation_email(self):
        from django.core import mail
        from lending.notifications import send_confirmation_email

        send_confirmation_email(self._booking("en"))
        msg = mail.outbox[-1]
        self.assertIn("confirmed", msg.subject)
        self.assertIn("Hi ", msg.body)


class ConfirmationDispatchTests(APITestCase):
    """When multi-pool order confirmations are mailed: full vs. held partial (#26)."""

    def setUp(self):
        import uuid
        from datetime import time
        from catalog.models import NotificationSetting

        s = NotificationSetting.load(); s.confirmation_send_time = time(17, 0); s.save()
        self.borrower = User.objects.create_user(username="alice", email="a@example.org")
        self.p1, r1 = _make_product_with_resources(1)
        self.p2, r2 = _make_product_with_resources(1, suffix="B")
        far = timezone.make_aware(datetime(2099, 5, 1, 10, 0))
        self.a = create_reservation(self.borrower, [(r1[0], far, far + timedelta(days=1))])
        self.b = create_reservation(self.borrower, [(r2[0], far, far + timedelta(days=1))])
        cid = uuid.uuid4()
        Booking.objects.filter(id__in=[self.a.id, self.b.id]).update(checkout_id=cid)
        self.a.refresh_from_db(); self.b.refresh_from_db()

    def _at(self, hour):
        return timezone.make_aware(datetime(2099, 4, 1, hour, 0))

    def _dispatch(self, booking, hour):
        from lending.confirmations import dispatch_confirmation_mails
        return dispatch_confirmation_mails(booking, now=self._at(hour))

    def test_partial_before_send_time_is_held(self):
        mail.outbox = []
        self.a.confirm()
        self.assertFalse(self._dispatch(self.a, 10))
        self.assertEqual(mail.outbox, [])

    def test_completing_the_order_sends_one_full_mail(self):
        mail.outbox = []
        self.a.confirm(); self._dispatch(self.a, 10)
        self.b.confirm("Bitte Ausweis mitbringen")
        self.assertTrue(self._dispatch(self.b, 11))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn(self.a.code, msg.body); self.assertIn(self.b.code, msg.body)
        self.assertIn("Bitte Ausweis mitbringen", msg.body)
        self.assertEqual(sum(1 for f, *_ in msg.attachments if f.endswith(".png")), 2)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertIsNotNone(self.a.confirmation_mailed_at)
        self.assertIsNotNone(self.b.confirmation_mailed_at)

    def test_send_time_flushes_partial(self):
        mail.outbox = []
        self.a.confirm(); self._dispatch(self.a, 10)
        self.assertTrue(self._dispatch(self.a, 17))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.b.code, mail.outbox[0].body)       # named as still open
        self.assertFalse(self._dispatch(self.a, 18))          # nothing left to send

    def test_confirmation_after_send_time_goes_out_now(self):
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 19))
        self.assertEqual(len(mail.outbox), 1)

    def test_urgent_pickup_goes_out_now(self):
        soon = self._at(12)
        self.a.items.update(period=DateTimeTZRange(soon, soon + timedelta(hours=3)))
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 10))            # pickup 12:00 < 17:00

    def test_single_pool_order_mails_immediately(self):
        Booking.objects.filter(id=self.b.id).update(checkout_id=None)
        Booking.objects.filter(id=self.a.id).update(checkout_id=None)
        self.a.refresh_from_db()
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 10))

    def test_command_flushes_at_send_time(self):
        from unittest.mock import patch
        from django.core.management import call_command

        self.a.confirm(); self._dispatch(self.a, 10)
        mail.outbox = []
        with patch("lending.confirmations.timezone.now", return_value=self._at(17)):
            call_command("send_confirmation_mails")
            call_command("send_confirmation_mails")      # idempotent
        self.assertEqual(len(mail.outbox), 1)

    # --- Race safety (review round 1): claiming parts before sending -------

    def test_second_dispatch_right_after_first_sends_nothing(self):
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 19))   # past send time -> immediate
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(self._dispatch(self.a, 19))  # already claimed and mailed
        self.assertEqual(len(mail.outbox), 1)

    def test_two_parts_confirmed_then_dispatched_twice_sends_one_mail(self):
        # Simulates two lenders confirming both parts at once and each
        # triggering dispatch: only one combined mail must go out.
        mail.outbox = []
        self.a.confirm(); self.b.confirm()
        self.assertTrue(self._dispatch(self.a, 11))
        self.assertFalse(self._dispatch(self.b, 11))
        self.assertEqual(len(mail.outbox), 1)

    # --- Retry on a real send failure vs. no recipient ----------------------

    def test_failed_send_releases_the_claim_for_a_later_retry(self):
        from unittest.mock import patch

        mail.outbox = []
        self.a.confirm()
        with patch("lending.confirmations.send_confirmation_email", return_value=False):
            self.assertFalse(self._dispatch(self.a, 19))  # past send time, but send fails
        self.assertEqual(mail.outbox, [])
        self.a.refresh_from_db()
        self.assertIsNone(self.a.confirmation_mailed_at)  # claim released, not stuck
        # A later dispatch (e.g. the next command run) retries and succeeds.
        self.assertTrue(self._dispatch(self.a, 19))
        self.assertEqual(len(mail.outbox), 1)
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.confirmation_mailed_at)

    def test_missing_recipient_is_settled_without_retry(self):
        self.borrower.email = ""
        self.borrower.save(update_fields=["email"])
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 19))  # nothing to send, but settled
        self.assertEqual(mail.outbox, [])
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.confirmation_mailed_at)
        self.assertFalse(self._dispatch(self.a, 19))  # not re-checked on a later run

    # --- Mail content gaps -----------------------------------------------

    def test_partial_confirmation_subject_and_marker_in_english(self):
        self.borrower.language = "en"
        self.borrower.save(update_fields=["language"])
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 19))  # past send time -> partial now
        msg = mail.outbox[0]
        self.assertIn("partial confirmation", msg.subject.lower())
        self.assertIn(self.a.code, msg.subject)
        self.assertIn("PARTIAL CONFIRMATION", msg.body)
        self.assertIn(f"Still awaiting confirmation: {self.b.resource_pool.name}", msg.body)
        self.assertIn(self.b.code, msg.body)

    def test_partial_confirmation_marker_in_german(self):
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 19))
        msg = mail.outbox[0]
        self.assertIn("Teilbestätigung", msg.subject)
        self.assertIn("TEILBESTÄTIGUNG", msg.body)

    def test_partial_mail_has_only_the_confirmed_parts_attachments(self):
        mail.outbox = []
        self.a.confirm()
        self.assertTrue(self._dispatch(self.a, 19))
        names = [f for f, *_ in mail.outbox[0].attachments]
        self.assertEqual(len(names), 2)
        self.assertTrue(any(n.startswith(f"pickup-{self.a.code}") for n in names))
        self.assertTrue(any(n.startswith(f"booking-{self.a.code}") for n in names))
        self.assertFalse(any(self.b.code in n for n in names))

    def test_cancelled_open_part_makes_held_part_a_full_mail(self):
        from unittest.mock import patch
        from django.core.management import call_command

        mail.outbox = []
        self.a.confirm()
        self.assertFalse(self._dispatch(self.a, 10))  # held: b is still open
        self.b.cancel()
        with patch("lending.confirmations.timezone.now", return_value=self._at(10)):
            call_command("send_confirmation_mails")
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("PARTIAL CONFIRMATION", mail.outbox[0].body)
        self.assertIn(self.a.code, mail.outbox[0].body)

    def test_command_holds_before_send_time_when_nothing_urgent(self):
        from unittest.mock import patch
        from django.core.management import call_command

        mail.outbox = []
        self.a.confirm()
        with patch("lending.confirmations.timezone.now", return_value=self._at(10)):
            call_command("send_confirmation_mails")
        self.assertEqual(mail.outbox, [])
        self.a.refresh_from_db()
        self.assertIsNone(self.a.confirmation_mailed_at)

    # --- I1: one failing order must not stop the rest of the run -----------

    def test_command_continues_after_one_order_fails(self):
        from unittest.mock import patch
        from django.core.management import call_command
        from lending.notifications import send_confirmation_email as real_send

        # Two further, independent (single-pool, so immediately mailable)
        # orders — one whose send is made to fail, one that should succeed
        # regardless.
        p3, r3 = _make_product_with_resources(1, suffix="C")
        p4, r4 = _make_product_with_resources(1, suffix="D")
        far = timezone.make_aware(datetime(2099, 5, 1, 10, 0))
        fail_borrower = User.objects.create_user(
            username="failer", email="fail@example.org"
        )
        ok_borrower = User.objects.create_user(username="oker", email="ok@example.org")
        failing = create_reservation(fail_borrower, [(r3[0], far, far + timedelta(days=1))])
        ok = create_reservation(ok_borrower, [(r4[0], far, far + timedelta(days=1))])
        failing.confirm()
        ok.confirm()

        def maybe_raise(parts, **kwargs):
            first = parts[0] if isinstance(parts, list) else parts
            if first.borrower_id == fail_borrower.id:
                raise RuntimeError("smtp down")
            return real_send(parts, **kwargs)

        mail.outbox = []
        with patch(
            "lending.confirmations.send_confirmation_email", side_effect=maybe_raise
        ):
            call_command("send_confirmation_mails")  # must not raise / exit non-zero

        self.assertEqual(len(mail.outbox), 1)
        failing.refresh_from_db()
        ok.refresh_from_db()
        # The failing order's part stays unmailed — retried on a later run.
        self.assertIsNone(failing.confirmation_mailed_at)
        self.assertIsNotNone(ok.confirmation_mailed_at)


class CartHoldSettingTests(APITestCase):
    """The cart-hold timeout is configurable and drives add_to_cart."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        self.product, self.resources = _make_product_with_resources(1)
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(days=2)

    def test_default_is_30_minutes(self):
        from .models import CartSetting

        self.assertEqual(CartSetting.load().hold_minutes, 30)

    def test_add_to_cart_uses_configured_hold(self):
        from .models import CartSetting
        from .services import add_to_cart

        CartSetting.objects.update_or_create(pk=1, defaults={"hold_minutes": 5})
        before = timezone.now()
        cart = add_to_cart(self.borrower, self.product, self.start, self.end)
        delta = (cart.expires_at - before).total_seconds()
        # ~5 minutes (allow a small execution window).
        self.assertGreater(delta, 4 * 60)
        self.assertLess(delta, 6 * 60)

    def test_get_and_put_setting(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get("/api/manage/cart-setting/").json()["hold_minutes"], 30
        )
        res = self.client.put(
            "/api/manage/cart-setting/", {"hold_minutes": 45}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["hold_minutes"], 45)

    def test_rejects_zero(self):
        self.client.force_login(self.admin)
        res = self.client.put(
            "/api/manage/cart-setting/", {"hold_minutes": 0}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_requires_admin(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/cart-setting/").status_code, 403
        )

    def test_release_command_frees_expired_cart(self):
        from django.core.management import call_command
        from .services import add_to_cart

        cart = add_to_cart(self.borrower, self.product, self.start, self.end)
        cart.expires_at = timezone.now() - timedelta(minutes=1)
        cart.save(update_fields=["expires_at"])
        call_command("release_cart_holds")
        cart.refresh_from_db()
        self.assertEqual(cart.status, Booking.Status.CANCELLED)
        self.assertFalse(
            BookingItem.objects.filter(booking=cart, is_active=True).exists()
        )


class BlockRescheduleTests(APITestCase):
    """Creating a closure (Block) reschedules or cancels colliding bookings and
    notifies the borrowers (concept §3.5)."""

    def setUp(self):
        from accounts.models import PoolMembership

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(
            username="alice", email="alice@uni.test"
        )
        # Pool open every weekday so only a block closes a day.
        self.pool = ResourcePool.objects.create(
            name="A", pool_id="A", closed_weekdays=[], max_booking_months=0
        )
        PoolMembership.objects.create(user=self.admin, resource_pool=self.pool)
        pt = ProductType.objects.create(name="Camera")
        self.product = Product.objects.create(product_type=pt, title="Cam")
        self.r1 = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="A-1", qr_code_id="QR-A-1",
        )
        self.r2 = Resource.objects.create(
            product=self.product, resource_pool=self.pool,
            inventory_number="A-2", qr_code_id="QR-A-2",
        )

    def _day(self, d):
        return timezone.make_aware(timezone.datetime(2099, 6, d))

    def _booking(self, resource, d_start, d_end, status=Booking.Status.CONFIRMED):
        return create_reservation(
            self.borrower, [(resource, self._day(d_start), self._day(d_end))],
            status=status,
        )

    def _block(self, d_start, d_end=None):
        period = DateTimeTZRange(self._day(d_start), self._day((d_end or d_start) + 1))
        block = Block.objects.create(
            period=period, resource_pool=self.pool, reason="Closure"
        )
        mail.outbox.clear()
        return apply_block_to_bookings(block)

    def _upper_day(self, item):
        item.refresh_from_db()
        return timezone.localtime(item.period.upper - timedelta(microseconds=1)).day

    def _lower_day(self, item):
        item.refresh_from_db()
        return timezone.localtime(item.period.lower).day

    def test_blocked_return_day_shifts_return(self):
        # Booking covers 1–2 June; block the 2nd → return moves to the 3rd.
        booking = self._booking(self.r1, 1, 3)  # [01, 03) = days 1,2
        item = booking.items.get()
        summary = self._block(2)
        self.assertEqual(summary, {"rescheduled": 1, "cancelled": 0})
        self.assertEqual(self._lower_day(item), 1)
        self.assertEqual(self._upper_day(item), 3)  # last booked day = 3rd
        self.assertEqual(len(mail.outbox), 1)
        # Borrower has no language set -> institution default (German).
        self.assertIn("umgebucht", mail.outbox[0].subject.lower())

    def test_blocked_pickup_day_shifts_pickup(self):
        # Booking covers 1–2 June; block the 1st → pickup moves to the 2nd.
        booking = self._booking(self.r1, 1, 3)
        item = booking.items.get()
        summary = self._block(1)
        self.assertEqual(summary["rescheduled"], 1)
        self.assertEqual(self._lower_day(item), 2)
        self.assertEqual(self._upper_day(item), 2)

    def test_whole_day_booking_cancelled(self):
        booking = self._booking(self.r1, 1, 2)  # single day, the 1st
        summary = self._block(1)
        self.assertEqual(summary, {"rescheduled": 0, "cancelled": 1})
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(len(mail.outbox), 1)
        # Borrower has no language set -> institution default (German).
        self.assertIn("storniert", mail.outbox[0].subject.lower())

    def test_hourly_booking_cancelled(self):
        pt = ProductType.objects.create(name="Beamer")
        hourly = Product.objects.create(
            product_type=pt, title="Beamer", lending_type=Product.LendingType.HOURS
        )
        res = Resource.objects.create(
            product=hourly, resource_pool=self.pool,
            inventory_number="AV-1", qr_code_id="QR-AV-1",
        )
        start = timezone.make_aware(timezone.datetime(2099, 6, 1, 9, 0))
        end = timezone.make_aware(timezone.datetime(2099, 6, 1, 12, 0))
        booking = create_reservation(
            self.borrower, [(res, start, end)], status=Booking.Status.CONFIRMED
        )
        summary = self._block(1)
        self.assertEqual(summary["cancelled"], 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_mid_loan_closure_leaves_booking_unchanged(self):
        booking = self._booking(self.r1, 1, 4)  # days 1,2,3
        item = booking.items.get()
        summary = self._block(2)  # middle day
        self.assertEqual(summary, {"rescheduled": 0, "cancelled": 0})
        self.assertEqual(self._lower_day(item), 1)
        self.assertEqual(self._upper_day(item), 3)

    def test_collision_moves_to_another_unit(self):
        booking = self._booking(self.r1, 1, 3)   # r1 days 1,2
        self._booking(self.r1, 3, 4)             # r1 occupied on the 3rd
        item = booking.items.get()
        summary = self._block(2)                 # return shifts to the 3rd → r1 clash
        self.assertEqual(summary["rescheduled"], 1)
        item.refresh_from_db()
        self.assertEqual(item.resource_id, self.r2.id)  # moved to the free unit
        self.assertEqual(self._upper_day(item), 3)

    def test_collision_without_free_unit_cancels(self):
        pt = ProductType.objects.create(name="Solo")
        solo = Product.objects.create(product_type=pt, title="Solo")
        s1 = Resource.objects.create(
            product=solo, resource_pool=self.pool,
            inventory_number="S-1", qr_code_id="QR-S-1",
        )
        booking = create_reservation(
            self.borrower, [(s1, self._day(1), self._day(3))],
            status=Booking.Status.CONFIRMED,
        )
        create_reservation(
            self.borrower, [(s1, self._day(3), self._day(4))],
            status=Booking.Status.CONFIRMED,
        )
        summary = self._block(2)  # return→3rd clashes with the only unit
        self.assertEqual(summary["cancelled"], 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_create_block_via_api_returns_summary(self):
        booking = self._booking(self.r1, 1, 2)  # single day → will cancel
        self.client.force_login(self.admin)
        res = self.client.post(
            "/api/manage/blocks/",
            {"start_date": "2099-06-01", "resource_pool": self.pool.id},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["adjusted"], {"rescheduled": 0, "cancelled": 1})
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)


class CapacityStatsTests(APITestCase):
    """Deployment-wide counts vs. the optional creation caps."""

    def setUp(self):
        from catalog.models import Product, ProductType, Resource, ResourcePool

        self.admin = User.objects.create_user(
            username="boss", is_staff=True, is_superuser=True
        )
        self.borrower = User.objects.create_user(username="alice")
        pt = ProductType.objects.create(name="Camera")
        pool = ResourcePool.objects.create(name="Lab", pool_id="lab")
        product = Product.objects.create(product_type=pt, title="A7")
        Product.objects.create(product_type=pt, title="GoPro")
        Resource.objects.create(
            product=product, resource_pool=pool,
            inventory_number="L-1", qr_code_id="qr-1",
        )

    def test_counts_and_unlimited_by_default(self):
        self.client.force_login(self.admin)
        body = self.client.get("/api/manage/stats/capacity/").json()
        self.assertEqual(body["products"]["count"], 2)
        self.assertEqual(body["resources"]["count"], 1)
        self.assertEqual(body["users"]["count"], 2)  # admin + borrower
        self.assertIsNone(body["products"]["max"])
        self.assertIsNone(body["resources"]["max"])
        self.assertIsNone(body["users"]["max"])

    @override_settings(MAX_PRODUCTS=10, MAX_RESOURCES=50)
    def test_reports_configured_caps(self):
        self.client.force_login(self.admin)
        body = self.client.get("/api/manage/stats/capacity/").json()
        self.assertEqual(body["products"]["max"], 10)
        self.assertEqual(body["resources"]["max"], 50)

    def test_anonymized_users_not_counted(self):
        from django.utils import timezone

        ghost = User.objects.create_user(username="ghost")
        ghost.anonymized_at = timezone.now()
        ghost.save(update_fields=["anonymized_at"])
        self.client.force_login(self.admin)
        body = self.client.get("/api/manage/stats/capacity/").json()
        self.assertEqual(body["users"]["count"], 2)  # ghost excluded

    def test_borrower_denied(self):
        self.client.force_login(self.borrower)
        self.assertEqual(
            self.client.get("/api/manage/stats/capacity/").status_code, 403
        )


class AllocationOrderTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")
        self.start = timezone.now() + timedelta(days=3)
        self.end = self.start + timedelta(days=1)

    def test_best_condition_is_allocated_first(self):
        product, resources = _make_product_with_resources(2)
        low, high = resources
        low.condition_rating = 2
        low.save(update_fields=["condition_rating"])
        high.condition_rating = 5
        high.save(update_fields=["condition_rating"])
        picked = available_resources(product, self.start, self.end).first()
        self.assertEqual(picked.id, high.id)

    def test_same_rating_picks_longest_idle(self):
        product, resources = _make_product_with_resources(2)
        r_recent, r_old = resources
        # r_recent was returned yesterday; r_old two weeks ago -> r_old first.
        for res, days_ago in ((r_recent, 1), (r_old, 14)):
            past = timezone.now() - timedelta(days=days_ago + 1)
            booking = create_reservation(
                self.borrower, [(res, past, past + timedelta(days=1))],
            )
            item = booking.items.first()
            item.returned_at = timezone.now() - timedelta(days=days_ago)
            item.is_active = False
            item.save(update_fields=["returned_at", "is_active"])
        picked = available_resources(product, self.start, self.end).first()
        self.assertEqual(picked.id, r_old.id)

    def test_min_gap_excludes_too_close_neighbour(self):
        product, resources = _make_product_with_resources(1)
        product.min_gap = 1  # 1 day (lending_type defaults to days)
        product.save(update_fields=["min_gap"])
        res = resources[0]
        # Existing booking ends at self.start; a new booking starting the same
        # day violates the 1-day gap.
        prev_start = self.start - timedelta(days=2)
        create_reservation(self.borrower, [(res, prev_start, self.start)])
        self.assertEqual(available_resources(product, self.start, self.end).count(), 0)

    def test_exact_gap_is_available(self):
        product, resources = _make_product_with_resources(1)
        product.min_gap = 1
        product.save(update_fields=["min_gap"])
        res = resources[0]
        prev_start = self.start - timedelta(days=3)
        prev_end = self.start - timedelta(days=1)  # exactly 1 day before start
        create_reservation(self.borrower, [(res, prev_start, prev_end)])
        self.assertEqual(available_resources(product, self.start, self.end).count(), 1)


class CalendarGapTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")

    def test_gap_marks_neighbouring_day_unavailable(self):
        product, resources = _make_product_with_resources(1)
        product.min_gap = 1
        product.save(update_fields=["min_gap"])
        # Book the single unit for a 2-day slot.
        day0 = timezone.localdate() + timedelta(days=5)
        start = timezone.make_aware(datetime.combine(day0, time.min))
        end = start + timedelta(days=2)
        create_reservation(self.borrower, [(resources[0], start, end)])
        # Ask for the day immediately after the booking's return: still blocked
        # by the 1-day gap.
        days = availability_per_day(product, day0, day0 + timedelta(days=4))
        by_date = {d["date"]: d["available"] for d in days}
        gap_day = (day0 + timedelta(days=2)).isoformat()  # first day after return
        self.assertEqual(by_date[gap_day], 0)
        clear_day = (day0 + timedelta(days=3)).isoformat()  # gap satisfied
        self.assertEqual(by_date[clear_day], 1)

    def test_gap_blocks_day_when_window_starts_after_return(self):
        # The calendar window starts exactly on the booking's return day, so the
        # booking's raw period lies entirely *before* the queried window. The
        # gap must still block day D — this only works if the DB fetch window is
        # widened by the gap so the near-boundary booking is returned at all.
        product, resources = _make_product_with_resources(1)
        product.min_gap = 1
        product.save(update_fields=["min_gap"])
        day_d = timezone.localdate() + timedelta(days=10)
        start = timezone.make_aware(datetime.combine(day_d - timedelta(days=2), time.min))
        end = timezone.make_aware(datetime.combine(day_d, time.min))
        create_reservation(self.borrower, [(resources[0], start, end)])
        days = availability_per_day(product, day_d, day_d + timedelta(days=3))
        by_date = {d["date"]: d["available"] for d in days}
        self.assertEqual(by_date[day_d.isoformat()], 0)  # blocked by 1-day gap
        self.assertEqual(by_date[(day_d + timedelta(days=1)).isoformat()], 1)  # gap ok


class ListAvailabilityGapTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")

    def test_gap_excludes_resource_in_list_count(self):
        product, resources = _make_product_with_resources(1)
        product.min_gap = 1  # 1 day (days lending_type)
        product.save(update_fields=["min_gap"])
        day = timezone.localdate() + timedelta(days=10)
        # Booking ends at midnight of `day`; a same-day pickup violates the gap.
        start = timezone.make_aware(datetime.combine(day - timedelta(days=2), time.min))
        end = timezone.make_aware(datetime.combine(day, time.min))
        create_reservation(self.borrower, [(resources[0], start, end)])

        blocked = availability_on_date([product.id], day)
        self.assertEqual(blocked[product.id]["available"], 0)
        clear = availability_on_date([product.id], day + timedelta(days=1))
        self.assertEqual(clear[product.id]["available"], 1)

    def test_no_gap_is_unchanged(self):
        product, resources = _make_product_with_resources(1)  # min_gap defaults to 0
        day = timezone.localdate() + timedelta(days=10)
        start = timezone.make_aware(datetime.combine(day - timedelta(days=2), time.min))
        end = timezone.make_aware(datetime.combine(day, time.min))
        create_reservation(self.borrower, [(resources[0], start, end)])
        # No gap: the day immediately after the booking's return is free.
        result = availability_on_date([product.id], day)
        self.assertEqual(result[product.id]["available"], 1)

    def test_gap_is_per_product_not_global(self):
        # Two independent products scored in one call: A has a 1-day gap, B has
        # none. Both have a booking ending exactly at `day`. A's own gap blocks
        # the same-day pickup (0), but B has no gap so it stays free (1). A buggy
        # global-max_gap implementation would inherit A's 1-day gap and wrongly
        # mark B occupied too — this locks in the per-product scoping.
        product_a, res_a = _make_product_with_resources(1)
        product_a.min_gap = 1
        product_a.save(update_fields=["min_gap"])
        product_b, res_b = _make_product_with_resources(1, "B")  # min_gap == 0

        day = timezone.localdate() + timedelta(days=10)
        start = timezone.make_aware(datetime.combine(day - timedelta(days=2), time.min))
        end = timezone.make_aware(datetime.combine(day, time.min))
        create_reservation(self.borrower, [(res_a[0], start, end)])
        create_reservation(self.borrower, [(res_b[0], start, end)])

        result = availability_on_date([product_a.id, product_b.id], day)
        self.assertEqual(result[product_a.id]["available"], 0)  # 1-day gap blocks
        self.assertEqual(result[product_b.id]["available"], 1)  # no gap → free


class MissingProductNoticeTests(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(username="alice", email="a@x.test")
        self.holder = User.objects.create_user(username="bob", email="b@x.test")

    def _overdue_holder(self, product, resource):
        """A prior booking that is handed out and not returned.

        Its own booked period has already elapsed (that's what makes it
        overdue) — the resource is still physically out even though the
        system's booking calendar considers the slot free again. This must
        not overlap the upcoming booking's period: two active items on the
        same resource can never overlap (the no-overlap exclusion
        constraint), just like in production the next reservation is only
        ever booked for a period starting after the previous one's end.
        """
        start = timezone.now() - timedelta(days=2)
        end = timezone.now() - timedelta(hours=1)
        booking = create_reservation(
            self.holder, [(resource, start, end)], status=Booking.Status.CONFIRMED,
        )
        item = booking.items.first()
        item.handed_out_at = start
        item.save(update_fields=["handed_out_at"])
        return booking

    def _upcoming(self, product, resource):
        """An upcoming, not-yet-collected booking for the same unit, within lead."""
        start = timezone.now() + timedelta(hours=2)
        end = start + timedelta(days=1)
        return create_reservation(
            self.borrower, [(resource, start, end)], status=Booking.Status.CONFIRMED,
        )

    def test_notifies_when_no_alternative(self):
        product, resources = _make_product_with_resources(1)
        product.missing_notice_lead = 1  # 1 day lead (days lending_type)
        product.save(update_fields=["missing_notice_lead"])
        res = resources[0]
        self._overdue_holder(product, res)
        upcoming = self._upcoming(product, res)
        result = notify_missing_products()
        self.assertEqual(result["notified"], 1)
        self.assertEqual(result["rebooked"], 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("a@x.test", mail.outbox[0].to)
        item = upcoming.items.first()
        item.refresh_from_db()
        self.assertIsNotNone(item.missing_notified_at)
        # Booking is not cancelled.
        upcoming.refresh_from_db()
        self.assertEqual(upcoming.status, Booking.Status.CONFIRMED)

    def test_idempotent_second_run_is_silent(self):
        product, resources = _make_product_with_resources(1)
        product.missing_notice_lead = 1
        product.save(update_fields=["missing_notice_lead"])
        res = resources[0]
        self._overdue_holder(product, res)
        self._upcoming(product, res)
        notify_missing_products()
        mail.outbox.clear()
        result = notify_missing_products()
        self.assertEqual(result["notified"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_rebooks_to_free_alternative_without_mail(self):
        product, resources = _make_product_with_resources(2)
        product.missing_notice_lead = 1
        product.save(update_fields=["missing_notice_lead"])
        busy, spare = resources
        self._overdue_holder(product, busy)
        upcoming = self._upcoming(product, busy)
        result = notify_missing_products()
        self.assertEqual(result["rebooked"], 1)
        self.assertEqual(result["notified"], 0)
        self.assertEqual(len(mail.outbox), 0)
        item = upcoming.items.first()
        item.refresh_from_db()
        self.assertEqual(item.resource_id, spare.id)

    def test_lead_zero_never_notifies(self):
        product, resources = _make_product_with_resources(1)
        # missing_notice_lead stays 0
        res = resources[0]
        self._overdue_holder(product, res)
        self._upcoming(product, res)
        result = notify_missing_products()
        self.assertEqual(result["notified"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_on_time_holder_does_not_notify(self):
        """A holder still within their booked period (due back before the next
        pickup) is on time, not overdue — no notice, no rebooking."""
        product, resources = _make_product_with_resources(1)
        product.missing_notice_lead = 5  # wide enough that now is within lead
        product.save(update_fields=["missing_notice_lead"])
        res = resources[0]
        # Holder is out but due in 2 days — before the upcoming pickup.
        holder_start = timezone.now() - timedelta(days=1)
        holder_end = timezone.now() + timedelta(days=2)
        holder = create_reservation(
            self.holder, [(res, holder_start, holder_end)],
            status=Booking.Status.CONFIRMED,
        )
        hitem = holder.items.first()
        hitem.handed_out_at = holder_start
        hitem.save(update_fields=["handed_out_at"])
        # Upcoming pickup starts after the holder is due back (non-overlapping).
        up_start = timezone.now() + timedelta(days=2, hours=1)
        up_end = up_start + timedelta(days=1)
        upcoming = create_reservation(
            self.borrower, [(res, up_start, up_end)],
            status=Booking.Status.CONFIRMED,
        )
        result = notify_missing_products()
        self.assertEqual(result["notified"], 0)
        self.assertEqual(result["rebooked"], 0)
        self.assertEqual(len(mail.outbox), 0)
        item = upcoming.items.first()
        item.refresh_from_db()
        self.assertIsNone(item.missing_notified_at)


class DeskScopingTests(APITestCase):
    """A lender may only see/act on reservations of pools they manage (#26)."""

    def setUp(self):
        self.borrower = User.objects.create_user(username="alice")
        self.lender_a = User.objects.create_user(username="lena")
        self.admin = User.objects.create_user(username="boss", is_staff=True, is_superuser=True)
        self.p1, r1 = _make_product_with_resources(2)
        self.p2, r2 = _make_product_with_resources(1, suffix="B")
        self.pool_a, self.pool_b = r1[0].resource_pool, r2[0].resource_pool
        PoolMembership.objects.create(user=self.lender_a, resource_pool=self.pool_a)
        start = timezone.now() + timedelta(days=2)
        self.part_a = create_reservation(self.borrower, [(r1[0], start, start + timedelta(days=1))])
        self.part_b = create_reservation(self.borrower, [(r2[0], start, start + timedelta(days=1))])
        self.r_a_spare, self.r_b = r1[1], r2[0]

    def test_lender_sees_only_own_pool(self):
        self.client.force_login(self.lender_a)
        ids = [b["id"] for b in self.client.get("/api/manage/bookings/").data["results"]]
        self.assertEqual(ids, [self.part_a.id])

    def test_lender_cannot_act_on_other_pool(self):
        self.client.force_login(self.lender_a)
        for action in ("confirm", "cancel"):
            res = self.client.post(f"/api/manage/bookings/{self.part_b.id}/{action}/", {}, format="json")
            self.assertEqual(res.status_code, 404, action)

    def test_admin_can_act_on_both(self):
        self.client.force_login(self.admin)
        res = self.client.post(f"/api/manage/bookings/{self.part_b.id}/confirm/", {}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_add_item_rejects_other_pool(self):
        self.part_a.confirm()
        self.client.force_login(self.admin)
        res = self.client.post(f"/api/manage/bookings/{self.part_a.id}/add-item/",
                               {"resource": self.r_b.id}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_swap_rejects_other_pool(self):
        # A unit of the same product (p1) but sitting in pool_b -> rejected,
        # even though product + availability would otherwise allow it.
        self.part_a.confirm()
        cross_pool_resource = Resource.objects.create(
            product=self.p1,
            resource_pool=self.pool_b,
            inventory_number="cross-pool-1",
            qr_code_id="QR-cross-pool-1",
        )
        self.client.force_login(self.admin)
        item = self.part_a.items.get()
        res = self.client.post(
            f"/api/manage/bookings/{self.part_a.id}/swap/",
            {"item_id": item.id, "resource": cross_pool_resource.id}, format="json",
        )
        self.assertEqual(res.status_code, 400)


class SplitMigrationTests(TestCase):
    """`lending.splitting.split_multi_pool_bookings` (#26 data migration)."""

    def test_split_keeps_code_and_strike_and_rolls_up_status(self):
        from accounts.models import Strike
        from lending.splitting import split_multi_pool_bookings
        borrower = User.objects.create_user(username="alice")
        lender = User.objects.create_user(username="lena")
        _, r1 = _make_product_with_resources(1)
        _, r2 = _make_product_with_resources(1, suffix="B")
        r1[0].resource_pool.position = 1; r1[0].resource_pool.save(update_fields=["position"])
        r2[0].resource_pool.position = 2; r2[0].resource_pool.save(update_fields=["position"])
        start = timezone.now() + timedelta(days=1)
        b = create_reservation(borrower, [(r1[0], start, start + timedelta(days=1)),
                                          (r2[0], start, start + timedelta(days=1))])
        b.confirm()
        b.items.filter(resource=r1[0]).update(handed_out_at=timezone.now())
        Booking.objects.filter(id=b.id).update(status=Booking.Status.HANDED_OUT, resource_pool=None)
        Strike.objects.create(user=borrower, reason="late", issued_by=lender, booking=b,
                              expires_at=timezone.now() + timedelta(days=30))
        code = b.code

        created = split_multi_pool_bookings(Booking, BookingItem, ResourcePool)

        self.assertEqual(created, 1)
        b.refresh_from_db()
        self.assertEqual(b.code, code)
        self.assertEqual(b.resource_pool_id, r1[0].resource_pool_id)
        self.assertEqual(b.status, Booking.Status.HANDED_OUT)
        self.assertEqual(b.strikes.count(), 1)
        other = Booking.objects.exclude(id=b.id).exclude(status="cart").get(borrower=borrower)
        self.assertEqual(other.resource_pool_id, r2[0].resource_pool_id)
        self.assertEqual(other.status, Booking.Status.CONFIRMED)   # nothing out in pool B
        self.assertNotEqual(other.code, code)
        self.assertEqual(other.checkout_id, b.checkout_id)
        self.assertIsNotNone(other.confirmation_mailed_at)          # no resend

    def test_single_pool_booking_gets_pool_set_and_carts_untouched(self):
        from lending.splitting import split_multi_pool_bookings
        borrower = User.objects.create_user(username="bob")
        _, r1 = _make_product_with_resources(1)
        start = timezone.now() + timedelta(days=1)

        pending = create_reservation(borrower, [(r1[0], start, start + timedelta(days=1))])
        Booking.objects.filter(id=pending.id).update(resource_pool=None)

        confirmed = create_reservation(
            borrower, [(r1[0], start + timedelta(days=10), start + timedelta(days=11))]
        )
        confirmed.confirm()
        Booking.objects.filter(id=confirmed.id).update(resource_pool=None)

        cart = create_reservation(
            borrower, [(r1[0], start + timedelta(days=20), start + timedelta(days=21))],
            status=Booking.Status.CART,
        )
        Booking.objects.filter(id=cart.id).update(resource_pool=None)

        created = split_multi_pool_bookings(Booking, BookingItem, ResourcePool)

        self.assertEqual(created, 0)

        pending.refresh_from_db()
        self.assertEqual(pending.resource_pool_id, r1[0].resource_pool_id)
        self.assertIsNone(pending.confirmed_at)   # pending stays unconfirmed

        confirmed.refresh_from_db()
        self.assertEqual(confirmed.resource_pool_id, r1[0].resource_pool_id)
        self.assertIsNotNone(confirmed.confirmed_at)
        self.assertEqual(confirmed.confirmed_at, confirmed.updated_at)
        self.assertEqual(confirmed.confirmation_mailed_at, confirmed.updated_at)

        cart.refresh_from_db()
        self.assertIsNone(cart.resource_pool_id)   # carts left untouched
