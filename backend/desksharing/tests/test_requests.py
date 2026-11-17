# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import datetime, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import booking, cycles, hours, notify, requests as svc
from desksharing.booking import BookingError
from desksharing.models import DeskSettings, ReleaseRequest, Reservation, SwapRequest
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday

User = get_user_model()


class RequestTestBase(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)
        patcher = mock.patch("desksharing.notify.notify")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)

    def at(self, hour, minute=0):
        return datetime(self.day.year, self.day.month, self.day.day, hour, minute, tzinfo=hours.TZ)

    def reserve(self, place, holder, start=9, end=12, **kw):
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(self.day, start, end), **kw,
        )

    def events(self, event):
        return [c for c in self.notify.call_args_list if c.args[1] == event]


class SwapTests(RequestTestBase):
    def test_swap_accept_exchanges_places(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        with self.captureOnCommitCallbacks(execute=True):
            req = svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(len(self.events("swap_request")), 1)
        self.assertEqual(self.notify.call_args_list[0].args[0], self.other)
        with self.captureOnCommitCallbacks(execute=True):
            svc.answer_swap(req, user=self.other, accept=True)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.place, b.place), (self.d2, self.d1))
        self.assertEqual((a.status, b.status), (Reservation.Status.ACTIVE,) * 2)
        self.assertEqual((a.holder, b.holder), (self.member, self.other))
        req.refresh_from_db()
        self.assertEqual(req.status, "accepted")
        [answer] = self.events("swap_answer")
        self.assertEqual(answer.args[0], self.member)

    def test_swap_with_different_hours_and_taken(self):
        a = self.reserve(self.d1, self.member, 9, 11)
        b = self.reserve(self.d2, self.other, 10, 12)
        req = svc.request_swap(user=self.member, mine=a, theirs=b)
        svc.answer_swap(req, user=self.other, accept=True)
        a.refresh_from_db()
        self.assertEqual(a.place, self.d2)
        self.assertEqual(hours.local_day_hours(a.period)[1:], (9, 11))

    def test_swap_refused_when_place_not_free_for_other_period(self):
        a = self.reserve(self.d1, self.member, 9, 11)
        b = self.reserve(self.d2, self.other, 10, 12)
        self.reserve(self.d2, self.lender, 9, 10)  # blocks a's period on d2
        with self.assertRaises(BookingError) as cm:
            svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(cm.exception.code, "taken")

    def test_swap_accept_rechecks_and_rolls_back(self):
        a = self.reserve(self.d1, self.member, 9, 11)
        b = self.reserve(self.d2, self.other, 10, 12)
        req = svc.request_swap(user=self.member, mine=a, theirs=b)
        self.reserve(self.d2, self.lender, 9, 10)
        with self.assertRaises(BookingError) as cm:
            svc.answer_swap(req, user=self.other, accept=True)
        self.assertEqual(cm.exception.code, "taken")
        a.refresh_from_db()
        self.assertEqual(a.place, self.d1)
        self.assertEqual(a.status, Reservation.Status.ACTIVE)
        req.refresh_from_db()
        self.assertEqual(req.status, "open")

    def test_swap_requires_rights_both_ways(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        only_other = AccessGroup.objects.create(name="Only other")
        only_other.members.add(self.other)
        self.d2.access_groups.add(only_other)
        with self.assertRaises(BookingError) as cm:
            svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(cm.exception.code, "not_allowed")
        self.d2.access_groups.clear()
        only_member = AccessGroup.objects.create(name="Only member")
        only_member.members.add(self.member)
        self.d1.access_groups.add(only_member)
        with self.assertRaises(BookingError) as cm:
            svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(cm.exception.code, "not_allowed")
        self.assertFalse(SwapRequest.objects.exists())

    def test_swap_kind_mismatch(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.m1, self.other)
        with self.assertRaises(BookingError) as cm:
            svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(cm.exception.code, "kind_mismatch")

    def test_swap_rules(self):
        a = self.reserve(self.d1, self.member)
        mine2 = self.reserve(self.d3, self.member, 13, 14)
        b = self.reserve(self.d2, self.other)
        with self.assertRaises(BookingError):  # own reservation
            svc.request_swap(user=self.member, mine=a, theirs=mine2)
        with self.assertRaises(BookingError):  # not overlapping
            svc.request_swap(user=self.member, mine=mine2, theirs=b)
        with self.assertRaises(BookingError):  # not mine
            svc.request_swap(user=self.lender, mine=a, theirs=b)
        svc.request_swap(user=self.member, mine=a, theirs=b)
        with self.assertRaises(BookingError) as cm:
            svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(cm.exception.code, "duplicate_request")

    def test_swap_decline_and_wrong_answerer(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        req = svc.request_swap(user=self.member, mine=a, theirs=b)
        with self.assertRaises(BookingError):
            svc.answer_swap(req, user=self.member, accept=True)
        svc.answer_swap(req, user=self.other, accept=False)
        req.refresh_from_db()
        self.assertEqual(req.status, "declined")
        a.refresh_from_db()
        self.assertEqual(a.place, self.d1)
        with self.assertRaises(BookingError) as cm:
            svc.answer_swap(req, user=self.other, accept=True)
        self.assertEqual(cm.exception.code, "not_open")

    def test_swap_notifications_hide_requester_name(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        with self.captureOnCommitCallbacks(execute=True):
            svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertNotIn("Max", repr(self.notify.call_args_list[0].args[2]))
        self.assertNotIn("member", repr(self.notify.call_args_list[0].args[2]))

    def test_notify_failure_does_not_break(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        self.notify.side_effect = RuntimeError("mail down")
        with self.captureOnCommitCallbacks(execute=True):
            req = svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(req.status, "open")


class ReleaseRequestTests(RequestTestBase):
    def test_release_request_passes_to_requester(self):
        res = self.reserve(self.d1, self.member, 9, 12)
        req = svc.request_release(user=self.other, reservation=res)
        now = self.at(10, 30)
        with self.captureOnCommitCallbacks(execute=True):
            svc.answer_release(req, user=self.member, accept=True, now=now)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.release_reason, "request")
        new = Reservation.objects.get(holder=self.other, status="active")
        self.assertEqual(new.place, self.d1)
        self.assertEqual(new.period, hours.local_range(self.day, 10, 12))
        self.assertEqual(len(self.events("release_answer")), 1)

    def test_release_mid_reservation_grace_and_released_at(self):
        from desksharing import release
        res = self.reserve(self.d1, self.member, 9, 12)
        self.reserve(self.d2, self.lender, 9, 12)
        self.reserve(self.d3, self.lender, 9, 12)  # scarce: no free desk
        req = svc.request_release(user=self.other, reservation=res)
        svc.answer_release(req, user=self.member, accept=True, now=self.at(10, 50))
        new = Reservation.objects.get(holder=self.other, status="active")
        res.refresh_from_db()
        self.assertEqual(res.released_at, new.period.lower)
        self.assertEqual(new.late_until, self.at(10, 50))
        release.tick(self.at(10, 55))
        new.refresh_from_db()
        self.assertEqual(new.status, Reservation.Status.ACTIVE)
        self.assertFalse(new.no_show)

    def test_release_before_start_takes_whole_reservation(self):
        res = self.reserve(self.d1, self.member, 9, 12)
        req = svc.request_release(user=self.other, reservation=res)
        svc.answer_release(req, user=self.member, accept=True, now=self.at(7))
        new = Reservation.objects.get(holder=self.other, status="active")
        self.assertEqual(new.period, hours.local_range(self.day, 9, 12))

    def test_release_decline(self):
        res = self.reserve(self.d1, self.member)
        req = svc.request_release(user=self.other, reservation=res)
        svc.answer_release(req, user=self.member, accept=False, now=self.at(7))
        req.refresh_from_db()
        self.assertEqual(req.status, "declined")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)

    def test_release_accept_fails_when_requester_lost_rights(self):
        res = self.reserve(self.d1, self.member)
        req = svc.request_release(user=self.other, reservation=res)
        self.group.members.remove(self.other)
        with self.assertRaises(BookingError) as cm:
            svc.answer_release(req, user=self.member, accept=True, now=self.at(7))
        self.assertEqual(cm.exception.code, "not_allowed")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        self.assertFalse(Reservation.objects.filter(holder=self.other).exists())
        req.refresh_from_db()
        self.assertEqual(req.status, "open")

    def test_release_rules(self):
        res = self.reserve(self.d1, self.member)
        with self.assertRaises(BookingError):
            svc.request_release(user=self.member, reservation=res)
        svc.request_release(user=self.other, reservation=res)
        with self.assertRaises(BookingError) as cm:
            svc.request_release(user=self.other, reservation=res)
        self.assertEqual(cm.exception.code, "duplicate_request")
        outsider = User.objects.create_user("outsider", password="x")
        with self.assertRaises(BookingError):
            svc.request_release(user=outsider, reservation=res)

    def test_release_request_anonymous_by_default(self):
        res = self.reserve(self.d1, self.member)
        with self.captureOnCommitCallbacks(execute=True):
            anon = svc.request_release(user=self.other, reservation=res)
        self.assertNotIn("Ola", repr(self.notify.call_args_list[0].args[2]))
        self.assertIsNone(svc.serialize_release(anon, self.member)["requester_name"])
        self.assertNotIn("Ola", repr(svc.serialize_release(anon, self.member)))
        anon.status = "declined"
        anon.save()
        named = svc.request_release(user=self.other, reservation=res, show_name=True)
        self.assertEqual(svc.serialize_release(named, self.member)["requester_name"], "Ola")

    def test_hidden_desk_holder_not_revealed_to_requester(self):
        res = self.reserve(self.d1, self.member, holder_hidden=True)
        req = svc.request_release(user=self.other, reservation=res)
        self.assertIsNone(svc.serialize_release(req, self.other)["other_holder_name"])
        b = self.reserve(self.d2, self.other, 9, 12)
        swap = svc.request_swap(user=self.other, mine=b, theirs=res)
        self.assertIsNone(svc.serialize_swap(swap, self.other)["other_holder_name"])
        self.assertNotIn("Max", repr(svc.serialize_swap(swap, self.other)))
        visible = self.reserve(self.d3, self.lender, 9, 12)
        swap2 = svc.request_swap(user=self.other, mine=b, theirs=visible)
        self.assertEqual(svc.serialize_swap(swap2, self.other)["other_holder_name"], "Lea")

    def test_meeting_room_holder_shown(self):
        res = self.reserve(self.m1, self.member, holder_hidden=True)
        req = svc.request_release(user=self.other, reservation=res)
        self.assertEqual(svc.serialize_release(req, self.other)["other_holder_name"], "Max")


class ExpiryTests(RequestTestBase):
    def test_requests_expire_at_start(self):
        a = self.reserve(self.d1, self.member, 9, 12)
        b = self.reserve(self.d2, self.other, 10, 12)
        swap = svc.request_swap(user=self.member, mine=a, theirs=b)
        self.assertEqual(svc.expire_requests(self.at(8, 59)), 0)
        self.assertEqual(svc.expire_requests(self.at(9)), 1)
        swap.refresh_from_db()
        self.assertEqual(swap.status, "expired")

    def test_answer_after_start_expires(self):
        a = self.reserve(self.d1, self.member, 9, 12)
        b = self.reserve(self.d2, self.other, 10, 12)
        swap = svc.request_swap(user=self.member, mine=a, theirs=b)
        with self.assertRaises(BookingError) as cm:
            svc.answer_swap(swap, user=self.other, accept=True, now=self.at(9, 30))
        self.assertEqual(cm.exception.code, "expired")
        swap.refresh_from_db()
        self.assertEqual(swap.status, "expired")
        self.assertEqual(Reservation.objects.get(pk=a.pk).place, self.d1)

    def test_release_expires_at_end_and_when_cancelled(self):
        res = self.reserve(self.d1, self.member, 9, 12)
        req = svc.request_release(user=self.other, reservation=res)
        self.assertEqual(svc.expire_requests(self.at(11, 59)), 0)
        self.assertEqual(svc.expire_requests(self.at(12)), 1)
        req.refresh_from_db()
        self.assertEqual(req.status, "expired")
        res2 = self.reserve(self.d2, self.member, 14, 16)
        req2 = svc.request_release(user=self.other, reservation=res2)
        res2.status = Reservation.Status.CANCELLED
        res2.save()
        self.assertEqual(svc.expire_requests(self.at(7)), 1)
        req2.refresh_from_db()
        self.assertEqual(req2.status, "expired")

    def test_release_answer_after_end_expires(self):
        res = self.reserve(self.d1, self.member, 9, 12)
        req = svc.request_release(user=self.other, reservation=res)
        with self.assertRaises(BookingError) as cm:
            svc.answer_release(req, user=self.member, accept=True, now=self.at(12, 5))
        self.assertEqual(cm.exception.code, "expired")

    def test_desks_tick_expires_requests(self):
        past = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member,
            period=hours.local_range(self.day - timedelta(days=60), 9, 10),
        )
        ReleaseRequest.objects.create(reservation=past, requester=self.other)
        out = StringIO()
        call_command("desks_tick", stdout=out)
        self.assertEqual(ReleaseRequest.objects.get().status, "expired")
        self.assertIn("expired 1 request", out.getvalue())

    def test_accepted_swap_supersedes_other_open_requests(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        c = self.reserve(self.d3, self.lender)
        s1 = svc.request_swap(user=self.member, mine=a, theirs=b)
        s2 = svc.request_swap(user=self.lender, mine=c, theirs=b)
        svc.answer_swap(s1, user=self.other, accept=True)
        s2.refresh_from_db()
        self.assertEqual(s2.status, "expired")


class RequestApiTests(RequestTestBase):
    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_swap_api_flow(self):
        a = self.reserve(self.d1, self.member)
        b = self.reserve(self.d2, self.other)
        res = self.api(self.member).post(
            f"{API}/swap-requests/", {"mine_id": a.pk, "theirs_id": b.pk}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        rid = res.json()["id"]
        incoming = self.api(self.other).get(f"{API}/requests/mine/").json()
        self.assertEqual(len(incoming["incoming"]), 1)
        self.assertNotIn("Max", repr(incoming))
        outgoing = self.api(self.member).get(f"{API}/requests/mine/").json()
        self.assertEqual(len(outgoing["outgoing"]), 1)
        # Uninvolved users see nothing and cannot answer.
        self.assertEqual(
            self.api(self.lender).post(
                f"{API}/swap-requests/{rid}/answer/", {"accept": True}, format="json"
            ).status_code, 404,
        )
        self.assertEqual(
            self.api(self.member).post(
                f"{API}/swap-requests/{rid}/answer/", {"accept": True}, format="json"
            ).status_code, 409,
        )
        ok = self.api(self.other).post(
            f"{API}/swap-requests/{rid}/answer/", {"accept": True}, format="json"
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        a.refresh_from_db()
        self.assertEqual(a.place, self.d2)
        self.assertEqual(self.api(self.other).get(f"{API}/requests/mine/").json()["incoming"], [])

    def test_swap_api_validation_and_conflict(self):
        a = self.reserve(self.d1, self.member)
        c = self.api(self.member)
        self.assertEqual(c.post(f"{API}/swap-requests/", {"mine_id": a.pk}, format="json").status_code, 400)
        self.assertEqual(
            c.post(f"{API}/swap-requests/", {"mine_id": a.pk, "theirs_id": a.pk}, format="json").status_code,
            409,
        )

    def test_release_api_flow(self):
        res = self.reserve(self.d1, self.member)
        r = self.api(self.other).post(
            f"{API}/release-requests/", {"reservation_id": res.pk, "show_name": True}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["id"]
        mine = self.api(self.member).get(f"{API}/requests/mine/").json()
        self.assertEqual(mine["incoming"][0]["requester_name"], "Ola")
        ok = self.api(self.member).post(
            f"{API}/release-requests/{rid}/answer/", {"accept": False}, format="json"
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["status"], "declined")
        bad = self.api(self.member).post(
            f"{API}/release-requests/{rid}/answer/", {"accept": "yes"}, format="json"
        )
        self.assertEqual(bad.status_code, 400)


class BatchRequestTests(RequestTestBase):
    def setUp(self):
        super().setUp()
        self.days = [self.day + timedelta(weeks=i) for i in range(3)]

    def hold(self, place, day, holder=None):
        holder = holder or self.other
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=holder,
            period=hours.local_range(day, 10, 11),
        )

    def book(self, places, days=None, **kw):
        return booking.book_days(
            actor=self.member, holder=self.member, places=places, days=days or self.days,
            start_hour=9, end_hour=12, on_taken="request", **kw,
        )

    def test_book_days_request_books_free_and_requests_taken(self):
        blocker = self.hold(self.d1, self.days[1])
        with self.captureOnCommitCallbacks(execute=True):
            rows, reqs = self.book([self.d1], show_name=True)
        self.assertEqual(len(rows), 2)
        [req] = reqs
        self.assertEqual(req.reservation, blocker)
        self.assertEqual(req.requester, self.member)
        self.assertEqual(req.wanted_period, hours.local_range(self.days[1], 9, 12))
        self.assertIsNotNone(req.batch)
        self.assertTrue(req.show_name)
        data = svc.serialize_release(req, self.member)
        self.assertEqual(data["wanted"], {"day": self.days[1].isoformat(), "start_hour": 9, "end_hour": 12})
        self.assertEqual(data["batch"], str(req.batch))

    def test_only_requests_when_nothing_free(self):
        for day in self.days:
            self.hold(self.d1, day)
        rows, reqs = self.book([self.d1])
        self.assertEqual((rows, len(reqs)), ([], 3))
        self.assertEqual(len({r.batch for r in reqs}), 1)

    def test_one_mail_per_holder_per_batch(self):
        third = User.objects.create_user("third", password="x")
        self.group.members.add(third)
        self.hold(self.d1, self.days[0])
        self.hold(self.d1, self.days[1])
        self.hold(self.d2, self.days[2], holder=third)
        with self.captureOnCommitCallbacks(execute=True):
            _, reqs = self.book([self.d1, self.d2], days=self.days[:3])
        mails = self.events(notify.RELEASE_REQUEST)
        self.assertEqual(len(mails), 2)
        by_user = {c.args[0]: c.args[2] for c in mails}
        self.assertEqual(len(by_user[self.other]["reservations"]), 2)
        self.assertEqual(len(by_user[self.other]["request_ids"]), 2)
        self.assertEqual(len(by_user[third]["reservations"]), 1)
        self.assertNotIn("requester_name", by_user[self.other])

    def test_batch_mail_text_lists_all_dates(self):
        from desksharing.notify import _render_release_request

        self.hold(self.d1, self.days[0])
        self.hold(self.d1, self.days[1])
        with self.captureOnCommitCallbacks(execute=True):
            self.book([self.d1], show_name=True)
        [ctx] = [c.args[2] for c in self.events(notify.RELEASE_REQUEST)]
        _, text = _render_release_request(self.other, ctx)
        self.assertEqual(text.count("\n- "), 2)

    def test_duplicate_open_request_refuses_batch(self):
        blocker = self.hold(self.d1, self.days[1])
        ReleaseRequest.objects.create(reservation=blocker, requester=self.member)
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(BookingError) as cm:
                self.book([self.d1])
        self.assertEqual(cm.exception.code, "duplicate_request")
        self.assertEqual(self.events(notify.RELEASE_REQUEST), [])
        self.assertEqual(Reservation.objects.filter(holder=self.member).count(), 0)
        self.assertEqual(ReleaseRequest.objects.count(), 1)

    def test_wanted_request_expires_when_date_begins(self):
        blocker = self.hold(self.d1, self.day)
        wanted = hours.local_range(self.day, 9, 12)
        req = ReleaseRequest.objects.create(
            reservation=blocker, requester=self.member, wanted_period=wanted
        )
        svc.expire_requests(self.at(8))
        req.refresh_from_db()
        self.assertEqual(req.status, ReleaseRequest.Status.OPEN)
        svc.expire_requests(self.at(9))
        req.refresh_from_db()
        self.assertEqual(req.status, ReleaseRequest.Status.EXPIRED)

    def test_legacy_request_unchanged(self):
        blocker = self.hold(self.d1, self.day)
        req = ReleaseRequest.objects.create(reservation=blocker, requester=self.member)
        svc.expire_requests(self.at(10, 30))
        req.refresh_from_db()
        self.assertEqual(req.status, ReleaseRequest.Status.OPEN)
        svc.expire_requests(self.at(11))
        req.refresh_from_db()
        self.assertEqual(req.status, ReleaseRequest.Status.EXPIRED)
        self.assertIsNone(svc.serialize_release(req, self.member)["wanted"])

    def test_pending_requests_count_toward_quota(self):
        with mock.patch("desksharing.cycles.today", return_value=cycles.today()):
            DeskSettings.objects.filter(pool=self.pool).update(advance_days=1)
            window = cycles.booking_window(self.pool)
            first = window.open_until + timedelta(days=1)
            first += timedelta(days=(1 - first.weekday()) % 7)
            far, far2 = first, first + timedelta(weeks=1)
            self.hold(self.d1, far)
            rows, reqs = self.book([self.d1], days=[far])
            self.assertEqual((rows, len(reqs)), ([], 1))
            with self.assertRaises(BookingError) as cm:
                booking.book(
                    actor=self.member, holder=self.member, places=[self.d2],
                    day=far2, start_hour=9, end_hour=10,
                )
            self.assertEqual(cm.exception.code, "advance_days")
            # The request's own day is still bookable (same day, other place).
            booking.book(
                actor=self.member, holder=self.member, places=[self.d2],
                day=far, start_hour=9, end_hour=10,
            )

    def test_requested_slots_count_in_one_check(self):
        with mock.patch("desksharing.cycles.today", return_value=cycles.today()):
            DeskSettings.objects.filter(pool=self.pool).update(advance_days=1)
            window = cycles.booking_window(self.pool)
            first = window.open_until + timedelta(days=1)
            first += timedelta(days=(1 - first.weekday()) % 7)
            self.hold(self.d1, first)
            with self.assertRaises(BookingError) as cm:
                self.book([self.d1], days=[first, first + timedelta(weeks=1)])
        self.assertEqual(cm.exception.code, "advance_days")
        self.assertEqual(ReleaseRequest.objects.count(), 0)
        self.assertEqual(Reservation.objects.filter(holder=self.member).count(), 0)

    def test_endpoint_returns_requests(self):
        self.hold(self.d1, self.days[1])
        client = APIClient()
        client.force_authenticate(self.member)
        resp = client.post(
            "/api/desks/reservations/days/",
            {"place_ids": [self.d1.pk], "days": [d.isoformat() for d in self.days],
             "start_hour": 9, "end_hour": 12, "on_taken": "request"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.data["reservations"]), 2)
        self.assertEqual(len(resp.data["requests"]), 1)
        self.assertEqual(resp.data["requests"][0]["wanted"]["start_hour"], 9)


class WantedHandoverTests(RequestTestBase):
    """Accepting a request with wanted hours hands over the whole reservation
    and books the requester for the wanted hours."""

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def ask(self, res, start, end, requester=None, batch=None):
        return ReleaseRequest.objects.create(
            reservation=res, requester=requester or self.member,
            wanted_period=hours.local_range(res.period.lower.astimezone(hours.TZ).date(), start, end),
            batch=batch,
        )

    def test_accept_releases_whole_reservation_and_books_wanted_hours(self):
        res = self.reserve(self.d1, self.other, 8, 18)
        other_req = self.ask(res, 14, 16, requester=self.lender)
        req = self.ask(res, 10, 12)
        with self.captureOnCommitCallbacks(execute=True):
            svc.answer_release(req, user=self.other, accept=True, now=self.at(7))
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.RELEASED)
        self.assertEqual(res.release_reason, Reservation.ReleaseReason.REQUEST)
        self.assertEqual(res.released_at, res.period.lower)
        req.refresh_from_db()
        self.assertEqual(req.status, ReleaseRequest.Status.ACCEPTED)
        new = req.result
        self.assertEqual(new.holder, self.member)
        self.assertEqual(new.booked_by, self.member)
        self.assertEqual(new.place, self.d1)
        self.assertEqual(new.period, hours.local_range(self.day, 10, 12))
        self.assertEqual(new.status, Reservation.Status.ACTIVE)
        other_req.refresh_from_db()
        self.assertEqual(other_req.status, ReleaseRequest.Status.EXPIRED)
        [answer] = self.events(notify.RELEASE_ANSWER)
        self.assertEqual(answer.args[0], self.member)
        self.assertTrue(answer.args[2]["accepted"])
        self.assertEqual(answer.args[2]["reservation"]["id"], new.pk)

    def test_accept_after_start_releases_from_now(self):
        res = self.reserve(self.d1, self.other, 8, 18)
        req = self.ask(res, 14, 16)
        svc.answer_release(req, user=self.other, accept=True, now=self.at(9, 20))
        res.refresh_from_db()
        self.assertEqual(res.released_at, self.at(9, 20))

    def assert_handover_failed(self, res, req, call):
        with self.captureOnCommitCallbacks(execute=True):
            resp = call()
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "handover_failed")
        self.assertEqual(
            resp.json()["detail"], "The request could not be completed. Nothing was changed."
        )
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        req.refresh_from_db()
        self.assertEqual(req.status, ReleaseRequest.Status.EXPIRED)
        self.assertIsNone(req.result)
        self.assertFalse(Reservation.objects.filter(holder=self.member).exclude(pk=res.pk).filter(place=self.d1).exists())
        [answer] = self.events(notify.RELEASE_ANSWER)
        self.assertEqual(answer.args[0], self.member)
        self.assertFalse(answer.args[2]["accepted"])
        self.assertTrue(answer.args[2]["failed"])
        self.assertEqual(answer.args[2]["reservation"]["start_hour"], 9)

    def answer_call(self, req, accept=True):
        return lambda: self.api(self.other).post(
            f"{API}/release-requests/{req.pk}/answer/", {"accept": accept}, format="json"
        )

    def test_accept_fails_when_meanwhile_taken(self):
        res = self.reserve(self.d1, self.other, 10, 11)
        req = self.ask(res, 9, 12)
        self.reserve(self.d1, self.lender, 9, 10)
        self.assert_handover_failed(res, req, self.answer_call(req))

    def test_accept_fails_on_requester_quota(self):
        with mock.patch("desksharing.cycles.today", return_value=cycles.today()):
            DeskSettings.objects.filter(pool=self.pool).update(advance_days=1)
            window = cycles.booking_window(self.pool)
            first = window.open_until + timedelta(days=1)
            first += timedelta(days=(1 - first.weekday()) % 7)
            self.day = first
            res = self.reserve(self.d1, self.other, 8, 18)
            req = self.ask(res, 9, 12)
            # The requester filled the quota meanwhile on another day.
            Reservation.objects.create(
                place=self.d2, holder=self.member, booked_by=self.member,
                period=hours.local_range(first + timedelta(weeks=1), 9, 10),
            )
            self.assert_handover_failed(res, req, self.answer_call(req))

    def test_accept_fails_when_requester_lost_rights(self):
        res = self.reserve(self.d1, self.other, 8, 18)
        req = self.ask(res, 9, 12)
        self.group.members.remove(self.member)
        self.assert_handover_failed(res, req, self.answer_call(req))

    def test_decline_notifies(self):
        res = self.reserve(self.d1, self.other, 8, 18)
        req = self.ask(res, 10, 12)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.answer_call(req, accept=False)()
        self.assertEqual(resp.json()["status"], "declined")
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        [answer] = self.events(notify.RELEASE_ANSWER)
        self.assertEqual(answer.args[0], self.member)
        self.assertFalse(answer.args[2]["accepted"])
        self.assertNotIn("failed", answer.args[2])
        self.assertEqual(answer.args[2]["reservation"]["start_hour"], 10)

    def test_failed_mail_text(self):
        from desksharing.notify import _render_release_answer

        res = self.reserve(self.d1, self.other, 8, 18)
        ctx = {"request_id": 1, "accepted": False, "failed": True, "reservation": svc._brief(res)}
        _, text = _render_release_answer(self.member, ctx)
        self.assertIn(
            "your request could not be completed because the place or your quota no longer allowed it:",
            text,
        )

    def test_answer_batch_accepts_only_own(self):
        import uuid

        batch = uuid.uuid4()
        third = User.objects.create_user("third", password="x")
        self.group.members.add(third)
        mine1 = self.reserve(self.d1, self.other, 8, 18)
        self.day = self.day + timedelta(weeks=1)
        mine2 = self.reserve(self.d1, self.other, 8, 18)
        foreign = self.reserve(self.d2, third, 8, 18)
        r1, r2 = self.ask(mine1, 10, 12, batch=batch), self.ask(mine2, 10, 12, batch=batch)
        r3 = self.ask(foreign, 10, 12, batch=batch)
        resp = self.api(self.other).post(
            f"{API}/release-requests/answer-batch/", {"batch": str(batch), "accept": True}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"done": [r1.pk, r2.pk], "failed": []})
        for r, expected in ((r1, "accepted"), (r2, "accepted"), (r3, "open")):
            r.refresh_from_db()
            self.assertEqual(r.status, expected)
        self.assertEqual(
            self.api(self.other).post(
                f"{API}/release-requests/answer-batch/", {"batch": "nope", "accept": True}, format="json"
            ).status_code, 400,
        )

    def test_answer_batch_continues_after_failure(self):
        import uuid

        batch = uuid.uuid4()
        first = self.reserve(self.d1, self.other, 10, 11)
        self.day = self.day + timedelta(weeks=1)
        second = self.reserve(self.d1, self.other, 8, 18)
        r1, r2 = self.ask(first, 9, 12, batch=batch), self.ask(second, 10, 12, batch=batch)
        Reservation.objects.create(
            place=self.d1, holder=self.lender, booked_by=self.lender,
            period=hours.local_range(first.period.lower.astimezone(hours.TZ).date(), 9, 10),
        )
        result = svc.answer_release_batch(batch, user=self.other, accept=True)
        self.assertEqual(result, {"done": [r2.pk], "failed": [r1.pk]})
        r1.refresh_from_db()
        self.assertEqual(r1.status, ReleaseRequest.Status.EXPIRED)
        first.refresh_from_db()
        self.assertEqual(first.status, Reservation.Status.ACTIVE)

    def test_withdraw_by_requester_only(self):
        import uuid

        res = self.reserve(self.d1, self.other, 8, 18)
        req = self.ask(res, 10, 12)
        self.assertEqual(
            self.api(self.other).post(f"{API}/release-requests/{req.pk}/withdraw/").status_code, 404,
        )
        with self.assertRaises(BookingError) as cm:
            svc.withdraw_release(req, user=self.other)
        self.assertEqual(cm.exception.code, "not_allowed")
        ok = self.api(self.member).post(f"{API}/release-requests/{req.pk}/withdraw/")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["status"], "withdrawn")
        again = self.api(self.member).post(f"{API}/release-requests/{req.pk}/withdraw/")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "not_open")
        answered = self.answer_call(req)()
        self.assertEqual(answered.status_code, 409)
        self.assertEqual(answered.json()["code"], "not_open")

        batch = uuid.uuid4()
        b1, b2 = self.ask(res, 13, 14, batch=batch), self.ask(res, 15, 16, batch=batch)
        foreign = self.ask(res, 16, 17, requester=self.lender, batch=batch)
        resp = self.api(self.member).post(
            f"{API}/release-requests/withdraw-batch/", {"batch": str(batch)}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"withdrawn": 2})
        for r, expected in ((b1, "withdrawn"), (b2, "withdrawn"), (foreign, "open")):
            r.refresh_from_db()
            self.assertEqual(r.status, expected)
