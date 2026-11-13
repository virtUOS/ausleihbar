# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Rights of bookers and admins on others' reservations, same-kind rules,
series ended by lost rights or retired places, inactive pools."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import roles
from accounts.models import AccessGroup
from desksharing import absences, booking, hours, reminders, rights
from desksharing import series as series_svc
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, Place, Reservation, Series
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday

User = get_user_model()


def fresh(user):
    """A new instance: no memoised rights."""
    return User.objects.get(pk=user.pk)


class BookerAndAdminTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)
        self.assistants = AccessGroup.objects.create(name="Assistants")
        self.assistant = User.objects.create_user("asst", password="x")
        self.assistants.members.add(self.assistant)
        settings = DeskSettings.for_pool(self.pool)
        settings.assistant_group = self.assistants
        settings.save()

    def book_for_member(self, place=None):
        [res] = booking.book(
            actor=self.assistant, holder=self.member, places=[place or self.d1],
            day=self.day, start_hour=9, end_hour=12, notify_holder=False,
        )
        return res

    def drop_assistant_rights(self):
        self.assistants.members.remove(self.assistant)
        roles.invalidate_cache()
        self.assistant = fresh(self.assistant)

    def test_booker_cancel_notifies_holder(self):
        res = self.book_for_member()
        with mock.patch("desksharing.notify.notify") as notify:
            booking.cancel(res, actor=fresh(self.assistant))
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[:2], (self.member, "admin_changed"))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.CANCELLED)
        self.assertEqual(res.release_reason, "holder")

    def test_booker_move_notifies_holder(self):
        res = self.book_for_member()
        with mock.patch("desksharing.notify.notify") as notify:
            booking.move(res, actor=fresh(self.assistant), to_place=self.d2)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[1], "admin_changed")
        self.assertEqual(notify.call_args.args[2]["action"], "move")

    def test_booker_without_assistant_rights_loses_control(self):
        res = self.book_for_member()
        self.drop_assistant_rights()
        with self.assertRaises(BookingError) as cm:
            booking.cancel(res, actor=self.assistant)
        self.assertEqual(cm.exception.code, "not_allowed")
        with self.assertRaises(BookingError):
            booking.move(res, actor=self.assistant, to_place=self.d2)

    def test_series_booker_without_assistant_rights_loses_control(self):
        result = series_svc.create_series(
            actor=self.assistant, holder=self.member, place=self.d1,
            weekdays=[self.day.weekday()], start_hour=9, end_hour=12,
            valid_from=self.day, valid_until=self.day + timedelta(days=14),
        )
        self.drop_assistant_rights()
        with self.assertRaises(BookingError) as cm:
            series_svc.delete_series(result.series, actor=self.assistant)
        self.assertEqual(cm.exception.code, "not_allowed")
        # The holder still may (no reason needed).
        series_svc.delete_series(result.series, actor=fresh(self.member))

    def test_admin_cancel_of_started_reservation_releases_from_current_hour(self):
        now = timezone.now()
        full = timezone.localtime(now, hours.TZ).replace(minute=0, second=0, microsecond=0)
        res = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=(full - timedelta(hours=1), full + timedelta(hours=2)),
        )
        res.refresh_from_db()
        with mock.patch("desksharing.notify.notify") as notify:
            booking.cancel(res, actor=self.lender, reason="Repair")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.release_reason, "admin")
        self.assertEqual(res.released_at, full)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[2]["reason"], "Repair")

    def test_admin_move_requires_holder_rights_on_target(self):
        gf = AccessGroup.objects.create(name="GF")
        self.d2.access_groups.add(gf)
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=self.day, start_hour=9, end_hour=12,
        )
        # The admin may book the restricted place, the holder may not.
        self.assertTrue(rights.can_book_place(self.lender, self.d2))
        with self.assertRaises(BookingError) as cm:
            booking.move(res, actor=self.lender, to_place=self.d2)
        self.assertEqual(cm.exception.code, "not_allowed")
        res.refresh_from_db()
        self.assertEqual(res.place, self.d1)

    def test_move_targets_use_holder_rights_and_same_kind(self):
        gf = AccessGroup.objects.create(name="GF")
        self.d2.access_groups.add(gf)
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=self.day, start_hour=9, end_hour=12,
        )
        client = APIClient()
        client.force_authenticate(self.lender)
        r = client.get(f"{API}/reservations/{res.pk}/move-targets/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([p["id"] for p in r.json()], [self.d3.pk])
        client.force_authenticate(self.other)
        self.assertEqual(client.get(f"{API}/reservations/{res.pk}/move-targets/").status_code, 404)


class MoveTargetsPrivacyTests(TestCase):
    def setUp(self):
        setup_department(self)
        from desksharing import privacy

        self.day = next_weekday(1)
        self.d3.fixed_owner = self.member
        self.d3.save()
        privacy.set_hide_name(self.member, True)
        [self.res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=self.day, start_hour=9, end_hour=10,
        )

    def targets(self, user):
        client = APIClient()
        client.force_authenticate(user)
        r = client.get(f"{API}/reservations/{self.res.pk}/move-targets/")
        self.assertEqual(r.status_code, 200, r.content)
        return {p["id"] for p in r.json()}

    def test_admin_does_not_see_hidden_holders_fixed_place(self):
        self.assertEqual(self.targets(self.lender), {self.d2.pk})

    def test_holder_sees_own_fixed_place(self):
        self.assertEqual(self.targets(self.member), {self.d2.pk, self.d3.pk})


class ManageListMineTests(TestCase):
    def test_manage_list_marks_own_reservations(self):
        setup_department(self)
        day = next_weekday(1)
        booking.book(actor=self.lender, holder=self.lender, places=[self.d1], day=day, start_hour=9, end_hour=10)
        booking.book(actor=self.member, holder=self.member, places=[self.d2], day=day, start_hour=9, end_hour=10)
        client = APIClient()
        client.force_authenticate(self.lender)
        rows = client.get(f"{API}/manage/reservations/?pool={self.pool.pk}&day={day.isoformat()}").json()
        self.assertEqual({r["place"]["name"]: r["mine"] for r in rows}, {"D1": True, "D2": False})


class SameKindTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)

    def test_book_rejects_mixed_kinds(self):
        with self.assertRaises(BookingError) as cm:
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1, self.m1],
                day=self.day, start_hour=9, end_hour=10,
            )
        self.assertEqual(cm.exception.code, "not_allowed")
        self.assertFalse(Reservation.objects.exists())

    def test_move_requires_same_kind(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=self.day, start_hour=9, end_hour=10,
        )
        with self.assertRaises(BookingError):
            booking.move(res, actor=self.member, to_place=self.m1)
        with self.assertRaises(BookingError):
            booking.move(res, actor=self.lender, to_place=self.m1)

    def test_resolve_conflict_requires_same_kind(self):
        result = series_svc.create_series(
            actor=self.member, holder=self.member, place=self.d1,
            weekdays=[self.day.weekday()], start_hour=9, end_hour=10,
            valid_from=self.day, valid_until=self.day,
        )
        result.series.reservations.update(status=Reservation.Status.CANCELLED)
        Reservation.objects.filter(series=result.series).delete()
        with self.assertRaises(BookingError):
            series_svc.resolve_conflict(result.series, self.day, self.m1, actor=self.member)
        series_svc.resolve_conflict(result.series, self.day, self.d2, actor=self.member)


class SeriesEndTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)

    def make_series(self, place=None):
        return series_svc.create_series(
            actor=self.member, holder=self.member, place=place or self.d1,
            weekdays=[self.day.weekday()], start_hour=9, end_hour=12,
            valid_from=self.day, valid_until=self.day + timedelta(days=21),
        ).series

    def test_lost_rights_end_the_series(self):
        series = self.make_series()
        self.group.members.remove(self.member)
        roles.invalidate_cache()
        with mock.patch("desksharing.notify.notify_grouped"):
            self.assertGreater(absences.revoke_lost_rights(user=fresh(self.member)), 0)
        series.refresh_from_db()
        self.assertIsNotNone(series.cancelled_at)

    def test_occurrence_on_other_place_does_not_end_series(self):
        series = self.make_series()
        gf = AccessGroup.objects.create(name="GF")
        # A resolved conflict on a restricted place; the holder loses only that.
        first = series.reservations.order_by("period").first()
        first.place = self.d2
        first.save()
        self.d2.access_groups.add(gf)
        with mock.patch("desksharing.notify.notify_grouped"):
            self.assertEqual(absences.revoke_lost_rights(user=fresh(self.member)), 1)
        series.refresh_from_db()
        self.assertIsNone(series.cancelled_at)

    def test_retired_place_ends_the_series(self):
        series = self.make_series()
        with mock.patch("desksharing.notify.notify_grouped"):
            booking.retire_places([self.d1])
        series.refresh_from_db()
        self.assertIsNotNone(series.cancelled_at)

    def test_reminders_skip_retired_place_and_lost_rights(self):
        series = self.make_series()
        now = hours.local_dt(series.valid_until - timedelta(days=7), 12)
        Place.objects.filter(pk=self.d1.pk).update(is_active=False)
        with mock.patch("desksharing.notify.notify", return_value=True) as notify:
            self.assertEqual(reminders.send_series_reminders(now=now), 0)
        notify.assert_not_called()
        Place.objects.filter(pk=self.d1.pk).update(is_active=True)
        self.group.members.remove(self.member)
        roles.invalidate_cache()
        with mock.patch("desksharing.notify.notify", return_value=True) as notify:
            self.assertEqual(reminders.send_series_reminders(now=now), 0)
        series.refresh_from_db()
        self.assertFalse(series.reminder_7_sent)
        self.group.members.add(self.member)
        roles.invalidate_cache()
        with mock.patch("desksharing.notify.notify", return_value=True):
            self.assertEqual(reminders.send_series_reminders(now=now), 1)

    def test_cancelled_series_gets_no_reminder(self):
        series = self.make_series()
        Series.objects.filter(pk=series.pk).update(cancelled_at=timezone.now())
        now = hours.local_dt(series.valid_until - timedelta(days=7), 12)
        with mock.patch("desksharing.notify.notify", return_value=True) as notify:
            self.assertEqual(reminders.send_series_reminders(now=now), 0)
        notify.assert_not_called()


class InactivePoolTests(TestCase):
    def setUp(self):
        setup_department(self)

    def test_inactive_pool_grants_nothing(self):
        self.assertTrue(rights.can_book_place(self.member, self.d1))
        self.pool.is_active = False
        self.pool.save()
        roles.invalidate_cache()
        member = fresh(self.member)
        self.assertFalse(rights.can_book_place(member, self.d1))
        self.assertNotIn(self.pool.pk, rights.member_pool_ids(member))
        self.assertEqual(rights.member_user_ids(self.pool.pk), set())

    def test_inactive_pool_keeps_its_reservations(self):
        day = next_weekday(1)
        booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=day, start_hour=9, end_hour=10,
        )
        self.pool.is_active = False
        self.pool.save()
        roles.invalidate_cache()
        self.assertEqual(absences.revoke_lost_rights(), 0)


class DjangoAdminMaskingTests(TestCase):
    """Operators' admin lists show hidden desk holders and anonymous
    requesters as in the app."""

    def setUp(self):
        setup_department(self)
        from desksharing import privacy

        self.member.username = "zwiebelkuchen"
        self.member.save()
        privacy.set_hide_name(self.member, True)
        self.day = next_weekday(1)
        [self.res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=self.day, start_hour=9, end_hour=10,
        )
        self.admin_user = User.objects.create_superuser("root", password="x")
        self.client.force_login(self.admin_user)

    def test_reservation_and_series_lists_mask_hidden_holder(self):
        series_svc.create_series(
            actor=self.member, holder=self.member, place=self.d2,
            weekdays=[self.day.weekday()], start_hour=9, end_hour=10,
            valid_from=self.day, valid_until=self.day,
        )
        for url in ("/django-admin/desksharing/reservation/", "/django-admin/desksharing/series/"):
            body = self.client.get(url).content.decode()
            self.assertIn("Person (verborgen)", body, url)
            self.assertNotIn("zwiebelkuchen", body, url)

    def test_release_request_list_masks_anonymous_requester(self):
        from desksharing.models import ReleaseRequest

        self.other.username = "pflaumenmus"
        self.other.save()
        ReleaseRequest.objects.create(reservation=self.res, requester=self.other, show_name=False)
        body = self.client.get("/django-admin/desksharing/releaserequest/").content.decode()
        self.assertIn("Person (verborgen)", body)
        self.assertNotIn("pflaumenmus", body)
