# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import absences, booking, hours
from desksharing.booking import BookingError
from desksharing.models import Absence, DeskSettings, Reservation
from desksharing.tests.test_booking import API, setup_department
from lending.models import Block

User = get_user_model()
NOW = datetime(2027, 3, 1, 8, 0, tzinfo=hours.TZ)  # a Monday
TUE = date(2027, 3, 2)
WED = date(2027, 3, 3)


class AbsenceTests(TestCase):
    def setUp(self):
        setup_department(self)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch("desksharing.notify.notify")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)
        self.assistant = User.objects.create_user("assistant", password="x")
        self.assistants = AccessGroup.objects.create(name="Assistants")
        self.assistants.members.add(self.assistant)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.assistant_group = self.assistants
        settings_.save()

    def reserve(self, place, day=TUE, start=9, end=12, holder=None, **kw):
        holder = holder or self.member
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(day, start, end), **kw,
        )

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    # absences

    def test_absence_releases_only_holders_reservations(self):
        mine = self.reserve(self.d1)
        later = self.reserve(self.d1, day=WED)
        outside = self.reserve(self.d2, day=date(2027, 3, 4))
        theirs = self.reserve(self.d3, holder=self.other)
        absences.add_absence(
            actor=self.member, user=self.member, start_date=TUE, end_date=WED, kind="vacation"
        )
        for res in (mine, later, outside, theirs):
            res.refresh_from_db()
        self.assertEqual(mine.status, Reservation.Status.RELEASED)
        self.assertEqual(later.status, Reservation.Status.RELEASED)
        self.assertEqual(mine.release_reason, Reservation.ReleaseReason.ABSENCE)
        self.assertEqual(mine.period, hours.local_range(TUE, 9, 12))
        self.assertEqual(mine.released_at, NOW)
        self.assertEqual(outside.status, Reservation.Status.ACTIVE)
        self.assertEqual(theirs.status, Reservation.Status.ACTIVE)
        # Self-service: no notification to oneself.
        self.notify.assert_not_called()

    def test_absence_not_no_show(self):
        res = self.reserve(self.d1)
        absences.add_absence(
            actor=self.member, user=self.member, start_date=TUE, end_date=TUE, kind="absent"
        )
        res.refresh_from_db()
        self.assertFalse(res.no_show)
        self.assertIsNone(res.potentially_free_at)

    def test_in_progress_reservation_is_released(self):
        res = self.reserve(self.d1, day=NOW.date(), start=6, end=12)
        absences.add_absence(
            actor=self.member, user=self.member, start_date=NOW.date(), end_date=WED,
            kind="absent",
        )
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertFalse(res.no_show)

    def test_assistant_marks_absent(self):
        res = self.reserve(self.d1)
        client = self.api(self.assistant)
        with self.captureOnCommitCallbacks(execute=True):
            r = client.post(
                f"{API}/manage/absences/",
                {"user": self.member.pk, "start_date": "2027-03-02", "end_date": "2027-03-03",
                 "kind": "absent"},
                format="json",
            )
            self.assertEqual(r.status_code, 201, r.data)
        res.refresh_from_db()
        self.assertEqual(res.release_reason, Reservation.ReleaseReason.ABSENCE)
        [call] = self.notify.call_args_list
        self.assertEqual(call.args[:2], (self.member, "released_other"))
        self.assertEqual(call.args[2]["reason"], "absence")
        self.assertEqual(call.args[2]["reservation"].pk, res.pk)
        self.assertEqual([a["user"] for a in client.get(f"{API}/manage/absences/").data],
                         [self.member.pk])
        # A person outside every department of the assistant: refused.
        stranger = User.objects.create_user("stranger", password="x")
        r = client.post(
            f"{API}/manage/absences/",
            {"user": stranger.pk, "start_date": "2027-03-02", "end_date": "2027-03-03",
             "kind": "absent"},
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        # Delete only within the departments.
        own = Absence.objects.create(
            user=stranger, start_date=TUE, end_date=TUE, kind="vacation"
        )
        self.assertEqual(client.delete(f"{API}/manage/absences/{own.pk}/").status_code, 404)
        mine = Absence.objects.get(user=self.member)
        self.assertEqual(client.delete(f"{API}/manage/absences/{mine.pk}/").status_code, 204)

    def test_colleague_cannot_see_absence(self):
        Absence.objects.create(user=self.member, start_date=TUE, end_date=TUE, kind="vacation")
        for user in (self.other, self.member):
            client = self.api(user)
            self.assertEqual(client.get(f"{API}/manage/absences/").status_code, 403)
            r = client.post(
                f"{API}/manage/absences/",
                {"user": self.member.pk, "start_date": "2027-03-02", "end_date": "2027-03-02",
                 "kind": "absent"},
                format="json",
            )
            self.assertEqual(r.status_code, 403)
        # A department admin (lender) sees it.
        self.assertEqual(len(self.api(self.lender).get(f"{API}/manage/absences/").data), 1)
        # Colleagues' own list never shows it.
        self.assertEqual(self.api(self.other).get(f"{API}/absences/").data, [])

    def test_own_api(self):
        client = self.api(self.member)
        r = client.post(
            f"{API}/absences/",
            {"start_date": "2027-03-02", "end_date": "2027-03-04", "kind": "vacation"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["user"], self.member.pk)
        self.assertEqual(len(client.get(f"{API}/absences/").data), 1)
        bad = {"start_date": "2027-03-04", "end_date": "2027-03-02", "kind": "vacation"}
        self.assertEqual(client.post(f"{API}/absences/", bad, format="json").status_code, 400)
        long = {"start_date": "2027-03-02", "end_date": "2028-03-02", "kind": "vacation"}
        self.assertEqual(client.post(f"{API}/absences/", long, format="json").status_code, 400)
        bad = {"start_date": "2027-03-02", "end_date": "2027-03-02", "kind": "sick"}
        self.assertEqual(client.post(f"{API}/absences/", bad, format="json").status_code, 400)
        # Others' absences are 404; own ones can be deleted.
        theirs = Absence.objects.create(user=self.other, start_date=TUE, end_date=TUE, kind="absent")
        self.assertEqual(client.delete(f"{API}/absences/{theirs.pk}/").status_code, 404)
        self.assertEqual(client.delete(f"{API}/absences/{r.data['id']}/").status_code, 204)
        # Past absences cannot be deleted and are not listed.
        past = Absence.objects.create(
            user=self.member, start_date=date(2027, 2, 1), end_date=date(2027, 2, 2), kind="absent"
        )
        self.assertEqual(client.delete(f"{API}/absences/{past.pk}/").status_code, 404)
        self.assertEqual(client.get(f"{API}/absences/").data, [])

    def test_service_validation(self):
        with self.assertRaises(BookingError):
            absences.add_absence(
                actor=self.member, user=self.other, start_date=TUE, end_date=TUE, kind="vacation"
            )
        with self.assertRaises(BookingError):
            absences.add_absence(
                actor=self.member, user=self.member, start_date=WED, end_date=TUE, kind="vacation"
            )

    # fixed places

    def test_fixed_place_bookable_during_owner_absence(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        with self.assertRaises(BookingError):
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1], day=TUE,
                start_hour=9, end_hour=11,
            )
        Absence.objects.create(user=self.other, start_date=TUE, end_date=TUE, kind="vacation")
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=TUE,
            start_hour=9, end_hour=11,
        )
        self.assertEqual(res.place, self.d1)
        # The day after is still the owner's.
        with self.assertRaises(BookingError):
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1], day=WED,
                start_hour=9, end_hour=11,
            )
        self.assertIn(self.d1, booking.free_places(self.pool, "desk", TUE, 12, 14, for_user=self.member))
        self.assertNotIn(self.d1, booking.free_places(self.pool, "desk", WED, 12, 14, for_user=self.member))

    def test_fixed_place_available_needs_whole_period(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        Absence.objects.create(user=self.other, start_date=TUE, end_date=TUE, kind="vacation")
        two_days = DateTimeTZRange(hours.local_dt(TUE, 20), hours.local_dt(WED, 8))
        self.assertFalse(absences.fixed_place_available(self.d1, two_days))
        Absence.objects.create(user=self.other, start_date=WED, end_date=WED, kind="absent")
        self.assertTrue(absences.fixed_place_available(self.d1, two_days))
        self.assertFalse(absences.fixed_place_available(self.d2, two_days))

    # blocks

    def test_block_releases_reservations(self):
        a = self.reserve(self.d1, start=9, end=12)
        b = self.reserve(self.d2, start=13, end=15)
        c = self.reserve(self.d3, day=WED)
        with self.captureOnCommitCallbacks(execute=True):
            block = Block.objects.create(period=hours.local_range(TUE, 11, 14), reason="x")
        for res in (a, b, c):
            res.refresh_from_db()
        self.assertEqual((a.status, a.release_reason), ("released", "block"))
        self.assertEqual((b.status, b.release_reason), ("released", "block"))
        self.assertEqual(c.status, "active")
        self.assertFalse(a.no_show)
        self.assertEqual(a.period, hours.local_range(TUE, 9, 12))
        self.assertEqual(
            sorted(call.args[2]["reservation"].pk for call in self.notify.call_args_list),
            sorted([a.pk, b.pk]),
        )
        self.assertEqual(block.pk and absences.on_block_saved(block), 0)

    def test_block_scopes(self):
        from catalog.models import Product, ProductType

        other_pool = AccessGroup.objects.create(name="X")
        from desksharing.tests.test_rights import make_pool

        pool2 = make_pool("PoolB", other_pool)
        res = self.reserve(self.d1)
        period = hours.local_range(TUE, 6, 20)
        with self.captureOnCommitCallbacks(execute=True):
            Block.objects.create(period=period, resource_pool=pool2)
        res.refresh_from_db()
        self.assertEqual(res.status, "active")
        product = Product.objects.create(
            title="P", product_type=ProductType.objects.create(name="T")
        )
        with self.captureOnCommitCallbacks(execute=True):
            Block.objects.create(period=period, product=product)
        res.refresh_from_db()
        self.assertEqual(res.status, "active")
        with self.captureOnCommitCallbacks(execute=True):
            Block.objects.create(period=period, resource_pool=self.pool)
        res.refresh_from_db()
        self.assertEqual(res.status, "released")

    def test_notify_failure_does_not_abort_block(self):
        a = self.reserve(self.d1)
        b = self.reserve(self.d2, holder=self.other)
        self.notify.side_effect = RuntimeError("smtp down")
        with self.assertLogs("desksharing.absences", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                Block.objects.create(period=hours.local_range(TUE, 6, 20))
        for res in (a, b):
            res.refresh_from_db()
            self.assertEqual(res.status, "released")

    # lost rights

    def test_rights_lost_cancels_future(self):
        future = self.reserve(self.d1)
        started = self.reserve(self.d2, day=NOW.date(), start=6, end=12)
        theirs = self.reserve(self.d3, holder=self.other)
        with self.captureOnCommitCallbacks(execute=True):
            self.group.members.remove(self.member)  # m2m signal
        for res in (future, started, theirs):
            res.refresh_from_db()
        self.assertEqual((future.status, future.release_reason), ("cancelled", "rights"))
        self.assertEqual(future.released_at, NOW)
        self.assertEqual(started.status, "active")
        self.assertEqual(theirs.status, "active")
        [call] = self.notify.call_args_list
        self.assertEqual(call.args[:2], (self.member, "released_other"))
        self.assertEqual(call.args[2]["reason"], "rights")

    def test_rights_lost_via_place_access_groups(self):
        res = self.reserve(self.d1)
        keep = self.reserve(self.d2)
        special = AccessGroup.objects.create(name="Special")
        special.members.add(self.other)
        with self.captureOnCommitCallbacks(execute=True):
            self.d1.access_groups.add(special)
        res.refresh_from_db()
        keep.refresh_from_db()
        self.assertEqual(res.status, "cancelled")
        self.assertEqual(keep.status, "active")

    def test_daily_command_revokes_claim_changes(self):
        res = self.reserve(self.d1)
        # Bypass signals, as a claim change on login would.
        AccessGroup.members.through.objects.filter(user=self.member).delete()
        res.refresh_from_db()
        self.assertEqual(res.status, "active")
        out = StringIO()
        call_command("desks_daily", stdout=out)
        res.refresh_from_db()
        self.assertEqual(res.status, "cancelled")
        self.assertIn("1 reservation", out.getvalue())

    def test_rights_notify_failure_continues(self):
        a = self.reserve(self.d1)
        b = self.reserve(self.d2, day=WED)
        self.notify.side_effect = RuntimeError("smtp down")
        with self.assertLogs("desksharing.absences", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                self.group.members.remove(self.member)
        for res in (a, b):
            res.refresh_from_db()
            self.assertEqual(res.status, "cancelled")


class HardeningTests(AbsenceTests):
    """Round-1 review fixes (inherits the fixtures; the inherited tests rerun)."""

    def commit(self):
        return self.captureOnCommitCallbacks(execute=True)

    def test_set_replacing_group_keeps_reservation(self):
        other_group = AccessGroup.objects.create(name="Dept A2")
        other_group.pools.add(self.pool)
        res = self.reserve(self.d1)
        with self.commit():
            self.member.access_groups.set([other_group])
        res.refresh_from_db()
        self.assertEqual(res.status, "active")
        # Removing the only granting group still cancels.
        with self.commit():
            self.member.access_groups.set([])
        res.refresh_from_db()
        self.assertEqual((res.status, res.release_reason), ("cancelled", "rights"))

    def test_pool_groups_set_is_evaluated_after_commit(self):
        other_group = AccessGroup.objects.create(name="Dept A2")
        other_group.members.add(self.member)
        res = self.reserve(self.d1)
        outsider = self.reserve(self.d2, holder=self.other)
        with self.commit():
            self.pool.access_groups.set([other_group])
        res.refresh_from_db()
        self.assertEqual(res.status, "active")
        outsider.refresh_from_db()
        self.assertEqual(outsider.status, "cancelled")

    def test_rights_revocation_is_deduplicated(self):
        self.reserve(self.d1)
        with mock.patch("desksharing.absences.revoke_lost_rights") as m:
            with self.commit():
                self.group.members.remove(self.member)
                self.group.members.add(self.member)
        self.assertEqual(m.call_count, 1)

    def test_disabled_department_keeps_reservations(self):
        res = self.reserve(self.d1)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.enabled = False
        settings_.save()
        self.assertEqual(absences.revoke_lost_rights(), 0)
        res.refresh_from_db()
        self.assertEqual(res.status, "active")

    def test_booking_warns_about_absence(self):
        Absence.objects.create(user=self.member, start_date=WED, end_date=WED, kind="vacation")
        client = self.api(self.member)
        body = {"place_ids": [self.d1.pk], "day": "2027-03-03", "start_hour": 9, "end_hour": 11}
        r = client.post(f"{API}/reservations/", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["warnings"], ["absent"])
        self.assertEqual(len(r.data["reservations"]), 1)
        body.update(day="2027-03-04", place_ids=[self.d2.pk])
        r = client.post(f"{API}/reservations/", body, format="json")
        self.assertEqual(r.data["warnings"], [])
        # Range bookings and series warn too.
        body = {"place_ids": [self.m1.pk], "day": "2027-03-02", "last_day": "2027-03-03",
                "start_hour": 9, "end_hour": 11}
        r = client.post(f"{API}/reservations/", body, format="json")
        self.assertEqual(r.data["warnings"], ["absent"])
        r = client.post(
            f"{API}/series/",
            {"place_id": self.d3.pk, "weekdays": [2], "start_hour": 9, "end_hour": 11,
             "valid_from": "2027-03-02", "valid_until": "2027-03-31"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["warnings"], ["absent"])

    def test_notifications_wait_for_commit(self):
        self.reserve(self.d1)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            absences.add_absence(
                actor=self.assistant, user=self.member, start_date=TUE, end_date=TUE,
                kind="absent",
            )
        self.notify.assert_not_called()
        for cb in callbacks:
            cb()
        self.assertEqual(self.notify.call_count, 1)

    def test_block_failure_does_not_break_block_save(self):
        with mock.patch("desksharing.absences.on_block_saved", side_effect=RuntimeError("x")):
            with self.assertLogs("desksharing.signals", level="ERROR"):
                with self.commit():
                    block = Block.objects.create(period=hours.local_range(TUE, 6, 20))
        self.assertTrue(Block.objects.filter(pk=block.pk).exists())

    def test_own_absence_response_has_released_count(self):
        self.reserve(self.d1)
        self.reserve(self.d2, day=WED)
        self.reserve(self.d3, holder=self.other)
        r = self.api(self.member).post(
            f"{API}/absences/",
            {"start_date": "2027-03-02", "end_date": "2027-03-03", "kind": "vacation"},
            format="json",
        )
        self.assertEqual(r.data["released_count"], 2)
