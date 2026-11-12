# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase

from accounts.models import AccessGroup
from desksharing import hours
from desksharing.models import DeskSettings
from desksharing.tests.test_rights import make_pool
from lending.models import Block

BERLIN = ZoneInfo("Europe/Berlin")


def next_weekday(weekday: int, weeks_ahead: int = 1) -> date:
    """The given weekday (0=Monday) at least ``weeks_ahead`` weeks from today."""
    today = date.today() + timedelta(days=7 * weeks_ahead)
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def whole_day(day: date) -> DateTimeTZRange:
    start = datetime.combine(day, time.min, tzinfo=BERLIN)
    return DateTimeTZRange(start, start + timedelta(days=1))


class HoursTests(TestCase):
    def setUp(self):
        self.pool = make_pool("PoolA", AccessGroup.objects.create(name="Dept A"))

    def test_dst_day_hours_are_local(self):
        for day in (date(2027, 3, 28), date(2027, 10, 31)):
            rng = hours.local_range(day, 6, 20)
            lower, upper = rng.lower.astimezone(BERLIN), rng.upper.astimezone(BERLIN)
            self.assertEqual(lower.strftime("%H:%M"), "06:00")
            self.assertEqual(upper.strftime("%H:%M"), "20:00")
            self.assertEqual(lower.date(), day)
            # Real elapsed time (UTC), not wall-clock arithmetic.
            elapsed = rng.upper.astimezone(ZoneInfo("UTC")) - rng.lower.astimezone(
                ZoneInfo("UTC")
            )
            self.assertEqual(elapsed, timedelta(hours=14))

    def test_business_hours_clamped_to_6_20(self):
        monday = next_weekday(0)
        DeskSettings.objects.filter(pool=self.pool).update(
            business_hours={**{str(d): None for d in range(7)}, "0": [5, 22]}
        )
        self.assertEqual(hours.business_hours(self.pool, monday), (6, 20))
        self.assertIsNone(hours.business_hours(self.pool, monday + timedelta(days=1)))
        DeskSettings.objects.filter(pool=self.pool).update(
            business_hours={**{str(d): None for d in range(7)}, "0": [8, 17]}
        )
        self.assertEqual(hours.business_hours(self.pool, monday), (8, 17))

    def test_holiday_block_closes_hours(self):
        day = next_weekday(2)
        other = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        # Blocks of another pool do not apply.
        Block.objects.create(period=whole_day(day), resource_pool=other)
        self.assertEqual(hours.closed_hours(self.pool, day), set())
        # A pool-scoped block over part of the day closes exactly those hours.
        Block.objects.create(
            period=hours.local_range(day, 12, 14), resource_pool=self.pool
        )
        self.assertEqual(hours.closed_hours(self.pool, day), {12, 13})
        # A system-wide block (public holiday) closes the whole day.
        Block.objects.create(period=whole_day(day), reason="Holiday")
        self.assertEqual(hours.closed_hours(self.pool, day), set(range(6, 20)))
        self.assertEqual(hours.closed_hours(self.pool, day + timedelta(days=1)), set())
