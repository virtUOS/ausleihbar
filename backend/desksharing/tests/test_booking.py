# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import threading
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import booking, hours
from desksharing.booking import BookingError
from desksharing.models import Floor, Place, Reservation, Room
from desksharing.tests.test_hours import next_weekday
from desksharing.tests.test_rights import make_pool

User = get_user_model()
API = "/api/desks"


def setup_department(test):
    test.group = AccessGroup.objects.create(name="Dept A")
    test.pool = make_pool("PoolA", test.group)
    test.lender = User.objects.create_user("lender", password="x", first_name="Lea")
    test.pool.lender_group.members.add(test.lender)
    test.member = User.objects.create_user("member", password="x", first_name="Max")
    test.other = User.objects.create_user("other", password="x", first_name="Ola")
    test.group.members.add(test.member, test.other)
    test.floor = Floor.objects.create(pool=test.pool, building="B1", name="EG")
    test.room = Room.objects.create(floor=test.floor, name="R1")
    test.d1 = Place.objects.create(room=test.room, name="D1")
    test.d2 = Place.objects.create(room=test.room, name="D2")
    test.d3 = Place.objects.create(room=test.room, name="D3")
    meeting = Room.objects.create(floor=test.floor, name="M", kind=Room.Kind.MEETING)
    test.m1 = Place.objects.create(
        room=meeting, name="M1", kind=Place.Kind.MEETING_ROOM, capacity=8
    )


class BookingTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)  # a Tuesday, open 06-20 by default

    def book(self, places, holder=None, actor=None, start=9, end=12, **kw):
        holder = holder or self.member
        return booking.book(
            actor=actor or holder, holder=holder, places=places, day=self.day,
            start_hour=start, end_hour=end, **kw,
        )

    def test_book_single(self):
        [res] = self.book([self.d1], comment="Sprint")
        self.assertEqual(res.place, self.d1)
        self.assertEqual(res.holder, self.member)
        self.assertEqual(res.booked_by, self.member)
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertEqual(res.period, hours.local_range(self.day, 9, 12))
        self.assertEqual(res.comment, "Sprint")

    def test_book_several_places_one_group(self):
        res = self.book([self.d2, self.d1])
        self.assertEqual(len(res), 2)
        self.assertEqual(len({r.group for r in res}), 1)
        self.assertEqual({r.place for r in res}, {self.d1, self.d2})

    def test_all_or_nothing_when_one_taken(self):
        self.book([self.d2], holder=self.other, start=10, end=11)
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1, self.d2])
        self.assertEqual(cm.exception.code, "taken")
        self.assertEqual(cm.exception.alternatives, [self.d3])
        self.assertEqual(Reservation.objects.filter(holder=self.member).count(), 0)
        # Same over the API: 409 with alternatives.
        client = APIClient()
        client.force_authenticate(self.member)
        r = client.post(f"{API}/reservations/", {
            "place_ids": [self.d1.pk, self.d2.pk], "day": self.day.isoformat(),
            "start_hour": 9, "end_hour": 12,
        }, format="json")
        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertEqual(body["code"], "taken")
        self.assertEqual(
            body["alternatives"],
            [{"id": self.d3.pk, "name": "D3", "room": "R1", "floor": "EG"}],
        )
        self.assertEqual(Reservation.objects.filter(holder=self.member).count(), 0)

    def test_adjacent_hours_do_not_conflict(self):
        self.book([self.d1], start=9, end=12)
        self.book([self.d1], holder=self.other, start=12, end=14)

    def test_outside_business_hours_rejected(self):
        for start, end in ((5, 9), (19, 21), (10, 10), (12, 9)):
            with self.assertRaises(BookingError) as cm:
                self.book([self.d1], start=start, end=end)
            self.assertEqual(cm.exception.code, "outside_hours")
        settings_ = self.pool.desk_settings
        settings_.business_hours[str(self.day.weekday())] = [8, 17]
        settings_.save()
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1], start=7, end=10)
        self.assertEqual(cm.exception.code, "outside_hours")
        self.book([self.d1], start=8, end=17)
        # A weekday without business hours is closed.
        with self.assertRaises(BookingError) as cm:
            booking.book(
                actor=self.member, holder=self.member, places=[self.d2],
                day=next_weekday(5), start_hour=9, end_hour=12,
            )
        self.assertEqual(cm.exception.code, "closed")

    def test_past_period_rejected(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(BookingError) as cm:
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1],
                day=yesterday, start_hour=9, end_hour=12,
            )
        self.assertEqual(cm.exception.code, "horizon")

    def test_horizon_uses_max_booking_months(self):
        self.pool.max_booking_months = 1
        self.pool.save()
        far = next_weekday(1, weeks_ahead=6)
        with self.assertRaises(BookingError) as cm:
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1],
                day=far, start_hour=9, end_hour=12,
            )
        self.assertEqual(cm.exception.code, "horizon")
        self.pool.max_booking_months = 3
        self.pool.save()
        booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=far, start_hour=9, end_hour=12,
        )

    def test_holiday_block_rejects(self):
        from lending.models import Block

        Block.objects.create(period=hours.local_range(self.day, 6, 20), reason="Holiday")
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1])
        self.assertEqual(cm.exception.code, "closed")

    def test_multi_day_room_only_open_days(self):
        friday = next_weekday(4)
        res = booking.book_range(
            actor=self.member, holder=self.member, places=[self.m1],
            day=friday, last_day=friday + timedelta(days=3),
            start_hour=9, end_hour=17,
        )
        self.assertEqual(len(res), 2)
        self.assertEqual(len({r.group for r in res}), 1)
        self.assertEqual(
            [r.period for r in res],
            [hours.local_range(friday, 9, 17),
             hours.local_range(friday + timedelta(days=3), 9, 17)],
        )
        # Only meeting rooms span days.
        with self.assertRaises(BookingError) as cm:
            booking.book_range(
                actor=self.member, holder=self.member, places=[self.d1],
                day=friday, last_day=friday + timedelta(days=3),
                start_hour=9, end_hour=17,
            )
        self.assertEqual(cm.exception.code, "not_allowed")
        # A range without any open day is closed.
        saturday = friday + timedelta(days=1)
        with self.assertRaises(BookingError) as cm:
            booking.book_range(
                actor=self.member, holder=self.member, places=[self.m1],
                day=saturday, last_day=saturday + timedelta(days=1),
                start_hour=9, end_hour=17,
            )
        self.assertEqual(cm.exception.code, "closed")

    def test_book_for_other_requires_assistant(self):
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1], holder=self.other, actor=self.member)
        self.assertEqual(cm.exception.code, "not_allowed")
        # Assistants of the department may.
        assistants = AccessGroup.objects.create(name="Assist")
        assistant = User.objects.create_user("assist", password="x")
        assistants.members.add(assistant)
        settings_ = self.pool.desk_settings
        settings_.assistant_group = assistants
        settings_.save()
        [res] = self.book([self.d1], holder=self.other, actor=assistant)
        self.assertEqual(res.booked_by, assistant)
        self.assertEqual(res.holder, self.other)
        # The holder must still be eligible.
        outsider = User.objects.create_user("out", password="x")
        with self.assertRaises(BookingError) as cm:
            self.book([self.d2], holder=outsider, actor=assistant)
        self.assertEqual(cm.exception.code, "not_allowed")
        # Over the API, holder_id is refused for non-assistants.
        client = APIClient()
        client.force_authenticate(self.member)
        r = client.post(f"{API}/reservations/", {
            "place_ids": [self.d3.pk], "day": self.day.isoformat(),
            "start_hour": 9, "end_hour": 12, "holder_id": self.other.pk,
        }, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "not_allowed")
        client.force_authenticate(assistant)
        r = client.post(f"{API}/reservations/", {
            "place_ids": [self.d3.pk], "day": self.day.isoformat(),
            "start_hour": 9, "end_hour": 12, "holder_id": self.other.pk,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_restricted_place_not_bookable(self):
        board = AccessGroup.objects.create(name="Board")
        self.d1.access_groups.add(board)
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1])
        self.assertEqual(cm.exception.code, "not_allowed")
        free = booking.free_places(
            self.pool, Place.Kind.DESK, self.day, 9, 12, for_user=self.member
        )
        self.assertNotIn(self.d1, free)
        # The department admin may book it.
        self.book([self.d1], holder=self.lender)

    def test_fixed_place_not_bookable_by_others(self):
        self.d1.fixed_owner = self.other
        self.d1.save()
        with self.assertRaises(BookingError) as cm:
            self.book([self.d1])
        self.assertEqual(cm.exception.code, "taken")
        self.assertNotIn(
            self.d1,
            booking.free_places(self.pool, Place.Kind.DESK, self.day, 9, 12, for_user=self.member),
        )
        self.book([self.d1], holder=self.other)

    def test_free_places_filters_features_and_taken(self):
        from desksharing.models import Feature

        dock = Feature.objects.create(pool=self.pool, name="Dock")
        self.d2.features.add(dock)
        self.d3.features.add(dock)
        self.book([self.d3], holder=self.other)
        free = booking.free_places(
            self.pool, Place.Kind.DESK, self.day, 9, 12,
            for_user=self.member, features=[dock.pk],
        )
        self.assertEqual(free, [self.d2])
        client = APIClient()
        client.force_authenticate(self.member)
        r = client.get(f"{API}/free/", {
            "pool": self.pool.pk, "kind": "desk", "day": self.day.isoformat(),
            "start_hour": 9, "end_hour": 12,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["id"] for p in r.json()], [self.d1.pk, self.d2.pk])

    def test_place_delete_cancels_future_keeps_past(self):
        past = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=hours.local_range(timezone.localdate() - timedelta(days=7), 9, 12),
        )
        [future] = self.book([self.d1])
        client = APIClient()
        client.force_authenticate(self.lender)
        r = client.delete(f"{API}/manage/places/{self.d1.pk}/")
        self.assertEqual(r.status_code, 204)
        self.d1.refresh_from_db()
        self.assertFalse(self.d1.is_active)
        past.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(past.status, Reservation.Status.ACTIVE)
        self.assertEqual(future.status, Reservation.Status.CANCELLED)
        self.assertEqual(future.release_reason, "admin")
        # An inactive place is not bookable any more.
        with self.assertRaises(BookingError):
            self.book([self.d1])

    def test_holder_cancels_own(self):
        [res] = self.book([self.d1])
        with self.assertRaises(BookingError) as cm:
            booking.cancel(res, actor=self.other)
        self.assertEqual(cm.exception.code, "not_allowed")
        client = APIClient()
        client.force_authenticate(self.member)
        r = client.delete(f"{API}/reservations/{res.pk}/")
        self.assertEqual(r.status_code, 204)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.CANCELLED)
        self.assertEqual(res.release_reason, "holder")
        # The place is free again.
        self.book([self.d1], holder=self.other)

    def test_started_release_keeps_used_hours(self):
        now = timezone.now()
        full = timezone.localtime(now, hours.TZ).replace(minute=0, second=0, microsecond=0)
        res = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=(full - timedelta(hours=1), full + timedelta(hours=2)),
        )
        res.refresh_from_db()
        booking.cancel(res, actor=self.member)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.release_reason, "holder")
        self.assertEqual(res.released_at, full)
        # A not yet started one is cancelled as before.
        future = Reservation.objects.create(
            place=self.d2, holder=self.member, booked_by=self.member,
            period=(full + timedelta(hours=3), full + timedelta(hours=4)),
        )
        future.refresh_from_db()
        booking.cancel(future, actor=self.member)
        future.refresh_from_db()
        self.assertEqual(future.status, Reservation.Status.CANCELLED)

    def test_admin_cancel_requires_reason(self):
        [res] = self.book([self.d1])
        with mock.patch("desksharing.notify.notify") as notify:
            with self.assertRaises(BookingError) as cm:
                booking.cancel(res, actor=self.lender)
            self.assertEqual(cm.exception.code, "reason_required")
            notify.assert_not_called()
            client = APIClient()
            client.force_authenticate(self.lender)
            r = client.delete(f"{API}/reservations/{res.pk}/")
            self.assertEqual(r.status_code, 400)
            r = client.delete(f"{API}/reservations/{res.pk}/", {"reason": "Fire drill"}, format="json")
            self.assertEqual(r.status_code, 204, r.content)
            notify.assert_called_once()
            self.assertEqual(notify.call_args.args[:2], (self.member, "admin_changed"))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.CANCELLED)
        self.assertEqual(res.release_reason, "admin")

    def test_admin_moves_any_reservation_in_pool(self):
        [res] = self.book([self.d1])
        self.book([self.d3], holder=self.other)
        client = APIClient()
        client.force_authenticate(self.other)
        r = client.post(f"{API}/reservations/{res.pk}/move/", {"place_id": self.d2.pk}, format="json")
        self.assertEqual(r.status_code, 404)
        client.force_authenticate(self.lender)
        with mock.patch("desksharing.notify.notify") as notify:
            r = client.post(f"{API}/reservations/{res.pk}/move/", {"place_id": self.d3.pk}, format="json")
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json()["code"], "taken")
            r = client.post(f"{API}/reservations/{res.pk}/move/", {"place_id": self.d2.pk}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
            notify.assert_called_once()
            self.assertEqual(notify.call_args.args[:2], (self.member, "admin_changed"))
        res.refresh_from_db()
        self.assertEqual(res.place, self.d2)
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        # The admin of another pool cannot.
        other_admin = User.objects.create_user("l2", password="x")
        other_pool = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        other_pool.lender_group.members.add(other_admin)
        with self.assertRaises(BookingError):
            booking.move(res, actor=other_admin, to_place=self.d1)

    def test_mine_and_manage_list(self):
        [res] = self.book([self.d1])
        self.book([self.d2], holder=self.other)
        client = APIClient()
        client.force_authenticate(self.member)
        r = client.get(f"{API}/reservations/mine/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["id"] for x in r.json()], [res.pk])
        self.assertEqual(r.json()[0]["start_hour"], 9)
        self.assertEqual(r.json()[0]["end_hour"], 12)
        url = f"{API}/manage/reservations/?pool={self.pool.pk}&day={self.day.isoformat()}"
        self.assertEqual(client.get(url).status_code, 403)
        client.force_authenticate(self.lender)
        rows = client.get(url).json()
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {(x["holder_id"], x["holder_name"]) for x in rows},
            {(self.member.pk, "Max"), (self.other.pk, "Ola")},
        )
        other_pool = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        r = client.get(f"{API}/manage/reservations/?pool={other_pool.pk}&day={self.day.isoformat()}")
        self.assertEqual(r.status_code, 404)


class RangeTodayAndSoftDeleteTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)
        self.client = APIClient()

    def test_book_range_api_and_horizon(self):
        self.client.force_authenticate(self.member)
        friday = next_weekday(4)
        data = {
            "place_ids": [self.m1.pk], "day": friday.isoformat(),
            "last_day": (friday + timedelta(days=3)).isoformat(),
            "start_hour": 9, "end_hour": 17,
        }
        r = self.client.post(f"{API}/reservations/", data, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(len(r.json()["reservations"]), 2)
        for last_day in ("9999-12-31", (friday + timedelta(days=800)).isoformat()):
            data["last_day"] = last_day
            r = self.client.post(f"{API}/reservations/", data, format="json")
            self.assertEqual(r.status_code, 409, r.content)
            self.assertEqual(r.json()["code"], "horizon")
        # No horizon on the pool: the range length is still capped.
        self.pool.max_booking_months = 0
        self.pool.save()
        data["last_day"] = (friday + timedelta(days=400)).isoformat()
        r = self.client.post(f"{API}/reservations/", data, format="json")
        self.assertEqual(r.json()["code"], "horizon")
        # Rights are checked before the range is walked.
        outsider = User.objects.create_user("out", password="x")
        self.client.force_authenticate(outsider)
        data["last_day"] = "9999-12-31"
        r = self.client.post(f"{API}/reservations/", data, format="json")
        self.assertEqual(r.json()["code"], "not_allowed")

    def test_today_past_hour_rejected(self):
        now = hours.local_dt(self.day, 10) + timedelta(minutes=30)
        with mock.patch("django.utils.timezone.now", return_value=now):
            with self.assertRaises(BookingError) as cm:
                booking.book(
                    actor=self.member, holder=self.member, places=[self.d1],
                    day=self.day, start_hour=9, end_hour=12,
                )
            self.assertEqual(cm.exception.code, "horizon")
            # The current hour itself is allowed.
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1],
                day=self.day, start_hour=10, end_hour=12,
            )

    def _history(self, place):
        past = Reservation.objects.create(
            place=place, holder=self.member, booked_by=self.member,
            period=hours.local_range(timezone.localdate() - timedelta(days=7), 9, 12),
        )
        [future] = booking.book(
            actor=self.member, holder=self.member, places=[place],
            day=self.day, start_hour=9, end_hour=12,
        )
        return past, future

    def _ids(self, url):
        body = self.client.get(url).json()
        rows = body["results"] if isinstance(body, dict) else body
        return [row["id"] for row in rows]

    def _assert_soft_deleted(self, obj, url, past, future):
        self.client.force_authenticate(self.lender)
        self.assertEqual(self.client.delete(url).status_code, 204)
        obj.refresh_from_db()
        self.assertFalse(obj.is_active)
        past.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(past.status, Reservation.Status.ACTIVE)
        self.assertEqual(future.status, Reservation.Status.CANCELLED)
        self.assertEqual(future.release_reason, "admin")
        for place in (self.d1, self.d2, self.d3):
            place.refresh_from_db()
            self.assertFalse(place.is_active)

    def test_room_delete_with_history_is_soft(self):
        past, future = self._history(self.d1)
        self._assert_soft_deleted(self.room, f"{API}/manage/rooms/{self.room.pk}/", past, future)
        self.assertNotIn(self.room.pk, self._ids(f"{API}/manage/rooms/"))
        self.assertIn(self.room.pk, self._ids(f"{API}/manage/rooms/?include_inactive=1"))
        self.assertNotIn(self.d2.pk, self._ids(f"{API}/manage/places/"))

    def test_room_delete_without_history_is_hard(self):
        self.client.force_authenticate(self.lender)
        r = self.client.delete(f"{API}/manage/rooms/{self.room.pk}/")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Room.objects.filter(pk=self.room.pk).exists())
        self.assertFalse(Place.objects.filter(pk=self.d1.pk).exists())

    def test_floor_delete_with_history_is_soft(self):
        past, future = self._history(self.d1)
        self._assert_soft_deleted(self.floor, f"{API}/manage/floors/{self.floor.pk}/", past, future)
        self.m1.refresh_from_db()
        self.assertFalse(self.m1.is_active)
        self.assertNotIn(self.floor.pk, self._ids(f"{API}/manage/floors/"))

    def test_floor_delete_without_history_is_hard(self):
        self.client.force_authenticate(self.lender)
        r = self.client.delete(f"{API}/manage/floors/{self.floor.pk}/")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Floor.objects.filter(pk=self.floor.pk).exists())

    def test_inactive_room_not_bookable(self):
        Room.objects.filter(pk=self.room.pk).update(is_active=False)
        self.room.refresh_from_db()
        with self.assertRaises(BookingError) as cm:
            booking.book(
                actor=self.member, holder=self.member, places=[self.d1],
                day=self.day, start_hour=9, end_hour=12,
            )
        self.assertEqual(cm.exception.code, "not_allowed")
        self.assertEqual(
            booking.free_places(self.pool, Place.Kind.DESK, self.day, 9, 12, for_user=self.member),
            [],
        )

    def test_cancel_with_non_object_body_is_400(self):
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d1],
            day=self.day, start_hour=9, end_hour=12,
        )
        self.client.force_authenticate(self.member)
        r = self.client.delete(f"{API}/reservations/{res.pk}/", ["x"], format="json")
        self.assertEqual(r.status_code, 400)

    def test_other_integrity_errors_propagate(self):
        from django.db import IntegrityError

        with mock.patch.object(
            Reservation.objects, "create", side_effect=IntegrityError("other")
        ):
            with self.assertRaises(IntegrityError):
                booking.book(
                    actor=self.member, holder=self.member, places=[self.d1],
                    day=self.day, start_hour=9, end_hour=12,
                )


class ConcurrentBookingTests(TransactionTestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)

    def test_concurrent_booking_one_wins(self):
        barrier = threading.Barrier(2)
        results = []

        def run(user):
            try:
                barrier.wait(timeout=10)
                booking.book(
                    actor=user, holder=user, places=[Place.objects.get(pk=self.d1.pk)],
                    day=self.day, start_hour=9, end_hour=12,
                )
                results.append("ok")
            except BookingError as exc:
                results.append(exc.code)
            finally:
                connection.close()

        # Skip the friendly pre-check so both reach the database constraint.
        with mock.patch.object(booking, "_taken_place_ids", return_value=set()):
            threads = [
                threading.Thread(target=run, args=(User.objects.get(pk=u.pk),))
                for u in (self.member, self.other)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
        self.assertEqual(sorted(results), ["ok", "taken"])
        self.assertEqual(Reservation.objects.filter(place=self.d1).count(), 1)
