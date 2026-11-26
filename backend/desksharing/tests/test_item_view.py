# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Item door signs: the data model (spec §6.5)."""
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase

from catalog.models import Product, ProductType, Resource, ResourcePool
from desksharing.hours import TZ
from desksharing.item_view import build_item_view
from lending import opening
from lending.models import Block, Booking, BookingItem

User = get_user_model()

ALL_WEEK = {key: [["08:00", "18:00"]] for key in opening.WEEKDAY_KEYS}


def at(hour, minute=0, day=2):
    return datetime(2027, 3, day, hour, minute, tzinfo=TZ)  # 2 March 2027 = Tuesday


def make_item_fixture(test, *, checkin=True, opening_hours=None, closed_weekdays=()):
    test.pool = ResourcePool.objects.create(
        name="Werkstatt", pool_id="Werkstatt", closed_weekdays=list(closed_weekdays),
        opening_hours=ALL_WEEK if opening_hours is None else opening_hours,
    )
    ptype = ProductType.objects.create(name="Lasercutter-Typ")
    test.product = Product.objects.create(
        product_type=ptype, title="Lasercutter Epilog Fusion Pro 32",
        lending_type=Product.LendingType.HOURS, use_type=Product.UseType.ONSITE,
        requires_handout=False, checkin_required=checkin, checkin_release_minutes=30,
    )
    test.resource = Resource.objects.create(
        product=test.product, resource_pool=test.pool, inventory_number="WS-0042",
        qr_code_id="QR-WS-0042",
    )
    test.borrower = User.objects.create_user(
        "zzz", password="x", first_name="Zzzunique", last_name="Borrower",
        email="zzzunique@example.org",
    )
    test.codes = iter(f"R-{n:05d}" for n in range(42, 100))


def add_item(test, start, end, *, status=Booking.Status.CONFIRMED, **fields):
    booking = Booking.objects.create(
        borrower=test.borrower, status=status, code=next(test.codes),
        resource_pool=test.pool, submitted_at=at(6), note="Zzzunique note",
    )
    return BookingItem.objects.create(
        booking=booking, resource=test.resource, period=DateTimeTZRange(start, end), **fields
    )


class ItemViewTests(TestCase):
    def setUp(self):
        make_item_fixture(self)

    def view(self, now):
        return build_item_view(self.resource, now=now)

    # rule 1
    def test_defective_or_blocked_is_out_of_service(self):
        add_item(self, at(9), at(10))
        for status in (Resource.Status.DEFECTIVE, Resource.Status.BLOCKED):
            self.resource.status = status
            self.resource.save()
            self.assertEqual(self.view(at(9, 20)).state, "out_of_service")

    def test_resource_block_is_out_of_service(self):
        Block.objects.create(resource=self.resource, period=DateTimeTZRange(at(0), at(23)))
        self.assertEqual(self.view(at(12)).state, "out_of_service")

    # rule 2
    def test_checked_in_running_item_is_in_use(self):
        item = add_item(self, at(9), at(11), checked_in_at=at(9, 5))
        view = self.view(at(10))
        self.assertEqual(view.state, "in_use")
        self.assertEqual(view.slot.end, item.period.upper)
        self.assertEqual(view.slot.code, "R-00042")

    def test_flagged_not_checked_in_is_late(self):
        add_item(self, at(9), at(10))
        view = self.view(at(9, 20))
        self.assertEqual(view.state, "late")
        self.assertEqual(view.late_minutes, 20)
        self.assertEqual(view.release_at, at(9, 30))
        self.assertEqual(view.slot.code, "R-00042")

    def test_adjacent_items_late_then_upcoming(self):
        add_item(self, at(9), at(10))
        add_item(self, at(10), at(11))
        view = self.view(at(9, 20))
        self.assertEqual(view.state, "late")
        self.assertEqual(view.slot.start, at(9))
        self.assertEqual(view.upcoming[0].start, at(10))
        self.assertEqual(view.upcoming[0].code, "R-00043")

    def test_unflagged_running_item_is_in_use_never_late(self):
        self.product.checkin_required = False
        self.product.save()
        add_item(self, at(9), at(10))
        for minute in (0, 20, 45, 59):
            view = self.view(at(9, minute))
            self.assertEqual(view.state, "in_use", minute)
            self.assertIsNone(view.late_minutes)

    # rule 3
    def test_item_starting_within_15_minutes_is_reserved(self):
        add_item(self, at(10), at(11))
        view = self.view(at(9, 45))
        self.assertEqual(view.state, "reserved")
        self.assertEqual((view.slot.start, view.slot.end), (at(10), at(11)))
        self.assertEqual(view.slot.code, "R-00042")
        self.assertEqual(self.view(at(9, 44)).state, "free")

    # rule 4
    def test_closed_outside_opening_hours(self):
        view = self.view(at(19))
        self.assertEqual(view.state, "closed")
        self.assertEqual(view.next_open, at(8, day=3))

    def test_closed_on_pool_block_and_weekday(self):
        Block.objects.create(resource_pool=self.pool, period=DateTimeTZRange(at(0), at(0, day=3)))
        self.assertEqual(self.view(at(12)).state, "closed")
        self.pool.closed_weekdays = [2]  # Wednesday
        self.pool.save()
        self.assertEqual(self.view(at(12)).next_open, at(8, day=4))

    def test_empty_opening_hours_never_closed(self):
        self.pool.opening_hours = {}
        self.pool.save()
        for hour in (0, 6, 12, 23):
            self.assertEqual(self.view(at(hour)).state, "free", hour)

    # rule 5
    def test_free_with_next_start(self):
        add_item(self, at(14), at(15))
        add_item(self, at(16), at(17))
        view = self.view(at(9))
        self.assertEqual(view.state, "free")
        self.assertEqual(view.next_start, at(14))
        self.assertEqual([s.start for s in view.upcoming], [at(14), at(16)])

    def test_free_without_reservation(self):
        add_item(self, at(10, day=3), at(11, day=3))  # tomorrow
        view = self.view(at(9))
        self.assertEqual(view.state, "free")
        self.assertIsNone(view.next_start)
        self.assertEqual(view.upcoming, [])

    def test_ignored_items(self):
        add_item(self, at(9), at(10), status=Booking.Status.CANCELLED, is_active=False)
        add_item(self, at(9), at(10), is_active=False, released_at=at(9, 30))
        add_item(self, at(9), at(10), status=Booking.Status.CART)
        self.assertEqual(self.view(at(9, 40)).state, "free")

    def test_upcoming_at_most_three(self):
        for hour in (11, 12, 13, 14, 15):
            add_item(self, at(hour), at(hour + 1))
        self.assertEqual(len(self.view(at(9)).upcoming), 3)

    # wake
    def test_next_wake_clamped_to_transition(self):
        add_item(self, at(10), at(11))
        self.assertEqual(self.view(at(9, 44)).next_wake, 60)
        self.assertEqual(self.view(at(9, 40)).next_wake, 300)
        self.assertEqual(self.view(at(9, 43)).next_wake, 120)

    def test_next_wake_when_closed(self):
        self.assertEqual(self.view(at(19)).next_wake, 14400)
        self.assertEqual(self.view(at(7)).next_wake, 55 * 60)

    def test_no_borrower_data_in_view(self):
        add_item(self, at(9), at(10))
        add_item(self, at(10), at(11))
        text = repr(self.view(at(9, 20)))
        for needle in ("Zzzunique", "zzzunique", "Borrower", "note"):
            self.assertNotIn(needle, text)


class OpeningTests(TestCase):
    def setUp(self):
        make_item_fixture(self, opening_hours={"tue": [["08:00", "12:00"], ["13:00", "18:00"]]})

    def test_breaks_are_closed(self):
        self.assertTrue(opening.is_open(self.pool, at(11, 59)))
        self.assertFalse(opening.is_open(self.pool, at(12, 30)))
        self.assertEqual(opening.next_opening(self.pool, at(12, 30)), at(13))

    def test_next_opening_next_week(self):
        self.assertEqual(opening.next_opening(self.pool, at(19)), at(8, day=9))

    def test_product_blocks_do_not_close_the_pool(self):
        Block.objects.create(product=self.product, period=DateTimeTZRange(at(0), at(23)))
        self.assertTrue(opening.is_open(self.pool, at(9)))

    def test_services_alias_kept(self):
        from lending import services

        self.assertIs(services._within_opening_hours, opening.within_opening_hours)
