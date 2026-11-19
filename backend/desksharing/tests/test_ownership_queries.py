# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Department lookups after the ownership change: places and new bookings
follow ``Place.pool``, existing bookings ``Reservation.pool``."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import (
    absences, assignment, booking, checkin, hours, overview, privacy, release, requests, stats,
)
from desksharing import series as series_svc
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, Place, Reservation, Room
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday
from desksharing.tests.test_rights import make_pool

User = get_user_model()


def fresh(user):
    """A new instance: the rights helpers memoise per user instance."""
    return User.objects.get(pk=user.pk)


class OwnershipQueryBase(TestCase):
    def setUp(self):
        setup_department(self)
        self.group_b = AccessGroup.objects.create(name="Dept B")
        self.pool_b = make_pool("PoolB", self.group_b)
        self.member_b = User.objects.create_user("member_b", password="x", first_name="Bea")
        self.group_b.members.add(self.member_b)
        self.lender_b = User.objects.create_user("lender_b", password="x")
        self.pool_b.lender_group.members.add(self.lender_b)
        self.staff = User.objects.create_user("staff", password="x", is_staff=True)
        self.day = next_weekday(1)  # a Tuesday, open 06-20 by default
        patcher = mock.patch("desksharing.notify.notify")
        patcher.start()
        self.addCleanup(patcher.stop)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def move_place(self, place, pool):
        assignment.assign_places([place], pool, actor=self.staff)
        place.refresh_from_db()

    def overview_places(self, user, pool):
        r = self.client_for(user).get(
            f"{API}/overview/", {"pool": pool.pk, "day": self.day.isoformat()}
        )
        self.assertEqual(r.status_code, 200, r.content)
        return r.json(), {p["id"]: p for f in r.json()["floors"] for p in f["places"]}


class ReassignedPlaceTests(OwnershipQueryBase):
    def test_reassigned_place_keeps_booking(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=self.day,
            start_hour=9, end_hour=12,
        )
        self.assertEqual(res.pool, self.pool)
        self.move_place(self.d1, self.pool_b)
        # The lost-rights step of desks_daily lets the booking run: the
        # holder is still a member of the booking's department.
        self.assertEqual(absences.revoke_lost_rights(), 0)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertEqual(res.pool, self.pool)
        # A's admins still see it in their reservation list ...
        r = self.client_for(self.lender).get(
            f"{API}/manage/reservations/", {"pool": self.pool.pk, "day": self.day.isoformat()}
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn(res.pk, [row["id"] for row in r.json()])
        # ... and B's admins don't.
        r = self.client_for(self.lender_b).get(
            f"{API}/manage/reservations/", {"pool": self.pool_b.pk, "day": self.day.isoformat()}
        )
        self.assertNotIn(res.pk, [row["id"] for row in r.json()])
        # B's overview shows the place as taken.
        _data, places = self.overview_places(self.member_b, self.pool_b)
        self.assertEqual(places[self.d1.pk]["hours"][9 - 6]["state"], "booked")
        self.assertNotIn(self.d1.pk, self.overview_places(self.member, self.pool)[1])
        # A's admin still manages the booking.
        booking.cancel(res, actor=fresh(self.lender), reason="Umzug")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.CANCELLED)

    def test_lost_rights_judged_by_booking_department(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=self.day,
            start_hour=9, end_hour=12,
        )
        self.move_place(self.d1, self.pool_b)
        # Leaving the booking's department ends it.
        self.group.members.remove(self.member)
        self.assertEqual(absences.revoke_lost_rights(), 1)
        res.refresh_from_db()
        self.assertEqual(res.release_reason, Reservation.ReleaseReason.RIGHTS)

    def test_move_stays_in_department(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=self.day,
            start_hour=9, end_hour=12,
        )
        self.group_b.members.add(self.member)
        b_room = Room.objects.create(floor=self.floor, pool=self.pool_b, name="RB")
        e1 = Place.objects.create(room=b_room, name="E1")
        with self.assertRaises(BookingError) as ctx:
            booking.move(res, actor=fresh(self.staff), to_place=e1)
        self.assertEqual(ctx.exception.code, "not_allowed")
        self.assertNotIn(e1.pk, [p.pk for p in booking.move_targets(res, actor=fresh(self.member))])
        res.refresh_from_db()
        self.assertEqual(res.place, self.d1)

    def test_swap_stays_in_department(self):
        # Both may book both places: only the departments differ.
        self.group_b.members.add(self.member)
        self.group.members.add(self.member_b)
        b_room = Room.objects.create(floor=self.floor, pool=self.pool_b, name="RB")
        e1 = Place.objects.create(room=b_room, name="E1")
        [mine] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=self.day,
            start_hour=9, end_hour=12,
        )
        [theirs] = booking.book(
            actor=self.member_b, holder=self.member_b, places=[e1], day=self.day,
            start_hour=9, end_hour=12,
        )
        with self.assertRaises(BookingError) as ctx:
            requests.request_swap(user=fresh(self.member), mine=mine, theirs=theirs)
        self.assertEqual(ctx.exception.code, "not_allowed")

    def test_check_in_on_moved_place(self):
        now = timezone.now()
        res = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=(now - timedelta(minutes=5), now + timedelta(hours=1)),
        )
        self.move_place(self.d1, self.pool_b)
        result = checkin.check_in_place(self.d1, user=fresh(self.member), now=now)
        self.assertEqual(result.action, "checked_in")
        res.refresh_from_db()
        self.assertIsNotNone(res.checked_in_at)


    def test_series_managed_by_booking_department(self):
        result = series_svc.create_series(
            actor=self.member, holder=self.member, place=self.d1, weekdays=[1],
            start_hour=9, end_hour=12, valid_from=self.day,
            valid_until=self.day + timedelta(days=14),
        )
        self.move_place(self.d1, self.pool_b)
        series = result.series
        self.assertEqual(series_svc.department_id(series), self.pool.pk)
        url = f"{API}/series/{series.pk}/conflicts/"
        self.assertEqual(self.client_for(self.lender_b).get(url).status_code, 404)
        self.assertEqual(self.client_for(self.lender).get(url).status_code, 200)
        with self.assertRaises(BookingError):
            series_svc.delete_series(series, actor=fresh(self.lender_b), reason="x")
        self.assertGreater(series_svc.delete_series(series, actor=fresh(self.lender), reason="x"), 0)


class UnassignedPlaceTests(OwnershipQueryBase):
    def test_unassigned_place_invisible_and_unbookable(self):
        self.move_place(self.d1, None)
        self.assertIsNone(self.d1.pool)
        self.assertFalse(self.d1.is_bookable)
        member = fresh(self.member)
        # Free now, overview and availability leave it out.
        free = overview.free_now(
            self.pool, viewer=member, now=hours.local_dt(self.day, 10)
        )
        self.assertNotIn(self.d1.pk, [row["id"] for row in free])
        self.assertNotIn(self.d1.pk, self.overview_places(self.member, self.pool)[1])
        r = self.client_for(self.member).get(f"{API}/availability/", {
            "pool": self.pool.pk, "kind": "desk", "days": self.day.isoformat(),
            "start_hour": 9, "end_hour": 11,
        })
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn(self.d1.pk, [row["id"] for row in r.json()])
        # Booking it is refused; its day view is not found.
        r = self.client_for(self.member).post(f"{API}/reservations/", {
            "place_ids": [self.d1.pk], "day": self.day.isoformat(),
            "start_hour": 9, "end_hour": 10,
        }, format="json")
        self.assertEqual(r.status_code, 409, r.content)
        r = self.client_for(self.member).get(
            f"{API}/places/{self.d1.pk}/days/",
            {"from": self.day.isoformat(), "to": self.day.isoformat()},
        )
        self.assertEqual(r.status_code, 404)
        # The other booking paths refuse it, too (never a crash).
        self.move_place(self.m1, None)
        for call in (
            lambda: booking.book_range(
                actor=member, holder=member, places=[self.m1], day=self.day,
                last_day=self.day + timedelta(days=1), start_hour=9, end_hour=10,
            ),
            lambda: booking.book_days(
                actor=member, holder=member, places=[self.d1], days=[self.day],
                start_hour=9, end_hour=10,
            ),
            lambda: series_svc.create_series(
                actor=member, holder=member, place=self.d1, weekdays=[1],
                start_hour=9, end_hour=10, valid_from=self.day, valid_until=self.day,
            ),
        ):
            with self.assertRaises(BookingError):
                call()
        # The place status (displays) is closed, not a crash.
        status_ = overview.place_status(self.d1, at=hours.local_dt(self.day, 10), anonymous=True)
        self.assertEqual(status_["state"], "closed")

    def test_running_booking_on_unassigned_place_survives_tick(self):
        now = hours.local_dt(self.day, 10)
        res = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=hours.local_range(self.day, 9, 12),
        )
        self.move_place(self.d1, None)
        # No crash; the booking's grace applies (60 min passed: potentially
        # free), an unassigned place is never scarce (not released).
        self.assertEqual(release.tick(now).marked, 1)
        res.refresh_from_db()
        self.assertEqual(res.pool, self.pool)
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertIsNotNone(res.potentially_free_at)


class StatsByReservationPoolTests(OwnershipQueryBase):
    def test_stats_count_by_reservation_pool(self):
        Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=hours.local_range(self.day, 9, 12),
        )
        self.move_place(self.d1, self.pool_b)
        Reservation.objects.create(
            place=self.d1, holder=self.member_b, booked_by=self.member_b,
            period=hours.local_range(self.day, 13, 15),
        )
        a = stats.department_stats(self.pool, self.day, self.day)
        b = stats.department_stats(self.pool_b, self.day, self.day)
        self.assertEqual(a["quota"]["desk"]["booked_h"], 3)
        self.assertEqual(b["quota"]["desk"]["booked_h"], 2)
        # An unassigned place isn't counted anywhere.
        self.move_place(self.d2, None)
        Reservation.objects.filter(place=self.d1).update(place=self.d2, pool=None)
        a = stats.department_stats(self.pool, self.day, self.day)
        self.assertEqual(a["quota"]["desk"]["booked_h"], 0)


class RetentionByReservationPoolTests(OwnershipQueryBase):
    def test_retention_uses_reservation_pool(self):
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.retention_days = 30
        settings_.save()
        now = timezone.now()
        ended = now - timedelta(days=60)
        res = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=(ended - timedelta(hours=2), ended),
        )
        # The place now belongs to B (default 90 days): A's 30 days apply.
        self.move_place(self.d1, self.pool_b)
        # A booking without department: the default retention (90 days).
        old = now - timedelta(days=100)
        orphan = Reservation.objects.create(
            place=self.d2, holder=self.other, booked_by=self.other,
            period=(old - timedelta(hours=2), old),
        )
        recent_orphan = Reservation.objects.create(
            place=self.d2, holder=self.other, booked_by=self.other,
            period=(ended - timedelta(hours=2), ended),
        )
        Reservation.objects.filter(pk__in=[orphan.pk, recent_orphan.pk]).update(pool=None)
        privacy.anonymize_due(now)
        for r in (res, orphan, recent_orphan):
            r.refresh_from_db()
        self.assertIsNone(res.holder)
        self.assertIsNone(orphan.holder)
        self.assertEqual(recent_orphan.holder, self.other)


class SharedFloorOverviewTests(OwnershipQueryBase):
    def test_overview_draws_only_own_places_on_shared_floor(self):
        b_room = Room.objects.create(floor=self.floor, pool=self.pool_b, name="RB")
        e1 = Place.objects.create(room=b_room, name="E1")
        # A place of B in A's room R1.
        e2 = Place.objects.create(room=self.room, name="E2")
        self.move_place(e2, self.pool_b)
        data, places = self.overview_places(self.member, self.pool)
        [floor] = data["floors"]
        self.assertEqual({r["name"] for r in floor["rooms"]}, {"R1", "M"})
        self.assertEqual(set(places), {self.d1.pk, self.d2.pk, self.d3.pk, self.m1.pk})
        data, places = self.overview_places(self.member_b, self.pool_b)
        [floor] = data["floors"]
        self.assertEqual({r["name"] for r in floor["rooms"]}, {"R1", "RB"})
        self.assertEqual(set(places), {e1.pk, e2.pk})
        # The member floor list holds the shared floor for both.
        for user, pool in ((self.member, self.pool), (self.member_b, self.pool_b)):
            r = self.client_for(user).get(f"{API}/floors/", {"pool": pool.pk})
            self.assertEqual([f["id"] for f in r.json()["floors"]], [self.floor.pk])
