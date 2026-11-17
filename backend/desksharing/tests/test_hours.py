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

    def test_blocked_days_only_fully_closed_days(self):
        monday = next_weekday(0)
        DeskSettings.objects.filter(pool=self.pool).update(
            business_hours={**{str(d): [8, 17] for d in range(5)}, "5": None, "6": None}
        )
        other = make_pool("PoolC", AccessGroup.objects.create(name="Dept C"))
        # Holiday on Monday, pool closure Tuesday, partial block Wednesday
        # (12-14 only), a block covering Thursday's business hours, a block on
        # Saturday (closed weekday) and one of another pool on Friday.
        Block.objects.create(period=whole_day(monday), reason="Holiday")
        Block.objects.create(period=whole_day(monday + timedelta(days=1)), resource_pool=self.pool)
        Block.objects.create(
            period=hours.local_range(monday + timedelta(days=2), 12, 14), resource_pool=self.pool
        )
        Block.objects.create(
            period=hours.local_range(monday + timedelta(days=3), 8, 17), resource_pool=self.pool
        )
        Block.objects.create(period=whole_day(monday + timedelta(days=4)), resource_pool=other)
        Block.objects.create(period=whole_day(monday + timedelta(days=5)), reason="Holiday")
        last = monday + timedelta(days=6)
        self.assertEqual(
            hours.blocked_days(self.pool, monday, last),
            [monday, monday + timedelta(days=1), monday + timedelta(days=3)],
        )
        # Without a pool: system-wide blocks covering the whole grid.
        self.assertEqual(
            hours.blocked_days(None, monday, last), [monday, monday + timedelta(days=5)]
        )


class ClosedDaysViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        group = AccessGroup.objects.create(name="Dept A")
        self.pool = make_pool("PoolA", group)
        self.member = get_user_model().objects.create_user("cd_member", password="x")
        group.members.add(self.member)
        self.outsider = get_user_model().objects.create_user("cd_out", password="x")
        self.client = APIClient()
        self.day = next_weekday(1)
        Block.objects.create(period=whole_day(self.day), reason="Holiday")

    def get(self, user, **q):
        self.client.force_authenticate(user)
        return self.client.get("/api/desks/closed-days/", q)

    def test_lists_closed_days(self):
        span = {"from": self.day.isoformat(), "to": (self.day + timedelta(days=3)).isoformat()}
        r = self.get(self.member, pool=self.pool.pk, **span)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"days": [self.day.isoformat()]})
        # Without a pool any signed-in user gets the system-wide closures.
        self.assertEqual(self.get(self.outsider, **span).json(), {"days": [self.day.isoformat()]})

    def test_validation_and_membership(self):
        span = {"from": self.day.isoformat(), "to": self.day.isoformat()}
        self.assertEqual(self.get(self.outsider, pool=self.pool.pk, **span).status_code, 404)
        self.assertEqual(self.get(self.member, **{"from": self.day.isoformat()}).status_code, 400)
        too_long = {"from": self.day.isoformat(), "to": (self.day + timedelta(days=401)).isoformat()}
        self.assertEqual(self.get(self.member, **too_long).status_code, 400)
        backwards = {"from": self.day.isoformat(), "to": (self.day - timedelta(days=1)).isoformat()}
        self.assertEqual(self.get(self.member, **backwards).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/desks/closed-days/", span).status_code, 403)
