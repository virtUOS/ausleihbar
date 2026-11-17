# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date

from django.test import TestCase

from desksharing import cycles
from desksharing.models import DeskSettings
from desksharing.serializers import DeskSettingsSerializer
from desksharing.tests.test_rights import make_pool


class WindowTests(TestCase):
    def setUp(self):
        self.pool = make_pool("Cycles", enabled=False)

    def window(self, today, **settings):
        DeskSettings.objects.filter(pool=self.pool).update(**settings)
        return cycles.booking_window(self.pool, today=today)

    def test_quarter_before_transition(self):
        w = self.window(date(2026, 11, 17))
        self.assertEqual((w.cycle_end, w.transition_from, w.open_until),
                         (date(2026, 12, 31), date(2026, 12, 4), date(2026, 12, 31)))
        self.assertEqual(w.next_cycle_end, date(2027, 3, 31))

    def test_transition_starts_on_its_first_day_and_crosses_the_year(self):
        self.assertEqual(self.window(date(2026, 12, 3)).open_until, date(2026, 12, 31))
        self.assertEqual(self.window(date(2026, 12, 4)).open_until, date(2027, 3, 31))
        self.assertEqual(self.window(date(2026, 12, 31)).open_until, date(2027, 3, 31))

    def test_yearly_cycle(self):
        w = self.window(date(2026, 12, 10), cycle_months=12)
        self.assertEqual((w.cycle_end, w.open_until), (date(2026, 12, 31), date(2027, 12, 31)))

    def test_monthly_cycle_without_transition(self):
        w = self.window(date(2026, 2, 28), cycle_months=1, transition_weeks=0)
        self.assertEqual(w.open_until, date(2026, 2, 28))

    def test_advance_until_respects_pool_horizon(self):
        self.assertEqual(self.window(date(2026, 11, 17)).advance_until, date(2027, 11, 17))
        self.pool.max_booking_months = 6
        self.pool.save()
        self.assertEqual(self.window(date(2026, 11, 17)).advance_until, date(2027, 5, 17))

    def test_no_pool_horizon_uses_advance_months_only(self):
        self.pool.max_booking_months = 0
        self.pool.save()
        self.assertEqual(self.window(date(2026, 11, 17)).advance_until, date(2027, 11, 17))

    def test_settings_validation(self):
        # serializer: transition must be shorter than a cycle; advance >= cycle
        for bad, field in (({"cycle_months": 1, "transition_weeks": 4}, "transition_weeks"),
                           ({"cycle_months": 6, "advance_months": 3}, "advance_months"),
                           ({"cycle_months": 5}, "cycle_months")):
            ser = DeskSettingsSerializer(DeskSettings.for_pool(self.pool), data=bad, partial=True)
            self.assertFalse(ser.is_valid(), bad)
            self.assertIn(field, ser.errors, bad)

    def test_settings_validation(self):
        # serializer: transition must be shorter than a cycle; advance >= cycle
        for bad in ({"cycle_months": 1, "transition_weeks": 4},
                    {"cycle_months": 6, "advance_months": 3},
                    {"cycle_months": 5}):
            ser = DeskSettingsSerializer(DeskSettings.for_pool(self.pool), data=bad, partial=True)
            self.assertFalse(ser.is_valid(), bad)

    def test_settings_valid(self):
        ser = DeskSettingsSerializer(
            DeskSettings.for_pool(self.pool), data={"cycle_months": 6}, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)
