# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import json
from datetime import datetime, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing import booking, hours, privacy, requests as requests_svc
from desksharing.models import (
    Absence, DeskProfile, DeskSettings, Place, ReleaseRequest, Reservation, Series,
    SwapRequest,
)
from desksharing.overview import place_status
from desksharing.serializers import ReservationSerializer, SeriesSerializer
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday

User = get_user_model()

HIDDEN_PK = 987654
HIDDEN_TOKENS = ("Hildegard", "Zwiebelkuchen", "hiddenuser_zq", "hidden.zq@example.org")
# Keys that carry a user id somewhere in the API.
USER_ID_KEYS = {
    "holder_id", "booked_by_id", "user", "user_id", "requester_id", "fixed_owner",
    "holder", "booked_by", "requester", "owner_id",
}


def user_ids_in(data, keys=USER_ID_KEYS):
    """All values of user-id keys anywhere in a JSON structure."""
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k in keys and isinstance(v, int) and not isinstance(v, bool):
                found.append(v)
            found.extend(user_ids_in(v, keys))
    elif isinstance(data, list):
        for v in data:
            found.extend(user_ids_in(v, keys))
    return found


class PrivacyBase(TestCase):
    def setUp(self):
        setup_department(self)
        self.day = next_weekday(1)
        patcher = mock.patch("desksharing.notify.notify")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)
        self.hidden = User.objects.create_user(
            "hiddenuser_zq", password="x", first_name="Hildegard",
            last_name="Zwiebelkuchen", email="hidden.zq@example.org", pk=HIDDEN_PK,
        )
        self.group.members.add(self.hidden)
        helpers = AccessGroup.objects.create(name="Helpers")
        self.assistant = User.objects.create_user("assi", password="x", first_name="Asta")
        helpers.members.add(self.assistant)
        self.group.members.add(self.assistant)
        settings_ = DeskSettings.for_pool(self.pool)
        settings_.assistant_group = helpers
        settings_.save()
        self.d4 = Place.objects.create(room=self.room, name="D4")
        self.d5 = Place.objects.create(room=self.room, name="D5")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def reserve(self, place, holder, start=9, end=12, day=None, **kw):
        kw.setdefault("booked_by", holder)
        return Reservation.objects.create(
            place=place, holder=holder,
            period=hours.local_range(day or self.day, start, end), **kw,
        )

    def at(self, hour, minute=0, day=None):
        d = day or self.day
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=hours.TZ)


class HideNameTests(PrivacyBase):
    def test_snapshot_set_on_booking_desks_only(self):
        privacy.set_hide_name(self.hidden, True)
        [desk] = booking.book(
            actor=self.hidden, holder=self.hidden, places=[self.d1], day=self.day,
            start_hour=9, end_hour=10,
        )
        [room] = booking.book(
            actor=self.hidden, holder=self.hidden, places=[self.m1], day=self.day,
            start_hour=9, end_hour=10,
        )
        self.assertTrue(desk.holder_hidden)
        self.assertFalse(room.holder_hidden)
        # Booked for the hidden person by an assistant: hidden as well.
        [for_them] = booking.book(
            actor=self.assistant, holder=self.hidden, places=[self.d2], day=self.day,
            start_hour=10, end_hour=11,
        )
        self.assertTrue(for_them.holder_hidden)

    def test_set_hide_name_applies_to_desks_and_ended_ones(self):
        past_day = timezone.localdate() - timedelta(days=3)
        past = self.reserve(self.d1, self.hidden, day=past_day)
        future = self.reserve(self.d1, self.hidden)
        room = self.reserve(self.m1, self.hidden)
        privacy.set_hide_name(self.hidden, True)
        for r in (past, future, room):
            r.refresh_from_db()
        # Ended desk reservations are hidden, too (anonymized next pass).
        self.assertEqual((past.holder_hidden, future.holder_hidden, room.holder_hidden),
                         (True, True, False))
        self.assertTrue(DeskProfile.objects.get(user=self.hidden).hide_name)
        privacy.anonymize_due(timezone.now())
        past.refresh_from_db()
        self.assertIsNone(past.holder)
        # Un-hiding is future-only.
        ended = self.reserve(self.d2, self.hidden, day=past_day, holder_hidden=True)
        privacy.set_hide_name(self.hidden, False)
        future.refresh_from_db()
        ended.refresh_from_db()
        self.assertFalse(future.holder_hidden)
        self.assertTrue(ended.holder_hidden)

    def test_holder_label_rules(self):
        res = self.reserve(self.d1, self.hidden, holder_hidden=True)
        for viewer in (self.lender, self.assistant, self.other, None):
            self.assertIsNone(privacy.holder_label(res, viewer=viewer))
        self.assertEqual(privacy.holder_label(res, viewer=self.hidden), "Hildegard Zwiebelkuchen")
        visible = self.reserve(self.d2, self.member)
        self.assertEqual(privacy.holder_label(visible, viewer=self.other), "Max")

    def test_meeting_room_holder_always_shown(self):
        privacy.set_hide_name(self.hidden, True)
        [res] = booking.book(
            actor=self.hidden, holder=self.hidden, places=[self.m1], day=self.day,
            start_hour=9, end_hour=11, comment="Kickoff",
        )
        # Even a stale snapshot never hides a meeting room holder.
        Reservation.objects.filter(pk=res.pk).update(holder_hidden=True)
        res.refresh_from_db()
        for viewer in (self.lender, self.assistant, self.other, None):
            self.assertEqual(privacy.holder_label(res, viewer=viewer), "Hildegard Zwiebelkuchen")
        r = self.client_for(self.other).get(
            f"{API}/overview/", {"pool": self.pool.pk, "day": self.day.isoformat()}
        )
        self.assertEqual(r.status_code, 200)
        [timeline] = r.json()["meeting_rooms"]
        [entry] = timeline["reservations"]
        self.assertEqual(entry["holder"], "Hildegard Zwiebelkuchen")
        self.assertEqual(entry["comment"], "Kickoff")
        self.assertEqual(
            place_status(self.m1, at=self.at(10), anonymous=False)["holder"],
            "Hildegard Zwiebelkuchen",
        )

    def test_move_to_desk_recomputes_snapshot(self):
        privacy.set_hide_name(self.hidden, True)
        [res] = booking.book(
            actor=self.hidden, holder=self.hidden, places=[self.m1], day=self.day,
            start_hour=9, end_hour=10,
        )
        self.assertFalse(res.holder_hidden)
        booking.move(res, actor=self.hidden, to_place=self.d1)
        res.refresh_from_db()
        self.assertTrue(res.holder_hidden)

    def test_release_request_new_reservation_snapshot(self):
        privacy.set_hide_name(self.hidden, True)
        res = self.reserve(self.d1, self.member)
        req = requests_svc.request_release(user=self.hidden, reservation=res)
        requests_svc.answer_release(req, user=self.member, accept=True, now=self.at(8))
        new = Reservation.objects.get(holder=self.hidden)
        self.assertTrue(new.holder_hidden)

    def test_profile_api(self):
        client = self.client_for(self.hidden)
        self.assertEqual(client.get(f"{API}/profile/").json(), {"hide_name": False})
        future = self.reserve(self.d1, self.hidden)
        r = client.put(f"{API}/profile/", {"hide_name": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"hide_name": True})
        future.refresh_from_db()
        self.assertTrue(future.holder_hidden)
        r = client.put(f"{API}/profile/", {"hide_name": "yes"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(APIClient().get(f"{API}/profile/").status_code, 403)


class OptOutEndpointTests(PrivacyBase):
    """The hidden desk holder never shows up for admin, assistant or colleague."""

    def build(self, hide: bool):
        privacy.set_hide_name(self.hidden, hide)
        self.hidden_res = booking.book(
            actor=self.hidden, holder=self.hidden, places=[self.d1], day=self.day,
            start_hour=9, end_hour=12, comment="Hildegard focus time",
        )[0]
        self.viewers = {"admin": self.lender, "assistant": self.assistant, "colleague": self.other}
        self.own = {}
        for (name, viewer), place in zip(self.viewers.items(), (self.d2, self.d3, self.d4)):
            self.own[name] = self.reserve(place, viewer)
            # Incoming swap request from the hidden holder.
            requests_svc.request_swap(user=self.hidden, mine=self.hidden_res, theirs=self.own[name])
            # Outgoing swap and release requests to the hidden holder.
            requests_svc.request_swap(user=viewer, mine=self.own[name], theirs=self.hidden_res)
            requests_svc.request_release(user=viewer, reservation=self.hidden_res)
        # The hidden person owns a fixed place, too.
        self.d5.fixed_owner = self.hidden
        self.d5.save()

    def endpoints(self, name):
        """Every endpoint that can return reservation or holder data."""
        q = {"pool": self.pool.pk, "day": self.day.isoformat()}
        own = self.own[name]
        sq = {
            "pool": self.pool.pk, "start": self.day.isoformat(),
            "end": (self.day + timedelta(days=1)).isoformat(),
        }
        return [
            ("overview", "get", f"{API}/overview/", q),
            ("free_now", "get", f"{API}/free-now/", {"pool": self.pool.pk}),
            ("neighbours", "get", f"{API}/reservations/{own.pk}/neighbours/", None),
            ("manage_reservations", "get", f"{API}/manage/reservations/", q),
            ("requests_mine", "get", f"{API}/requests/mine/", None),
            ("reservations_mine", "get", f"{API}/reservations/mine/", None),
            ("stats", "get", f"{API}/manage/stats/", sq),
            ("stats_csv", "get", f"{API}/manage/stats.csv", sq),
        ]

    def assert_clean(self, label, content):
        text = content.decode() if isinstance(content, bytes) else content
        self.assertNotIn(str(HIDDEN_PK), text, f"{label}: hidden user pk in content")
        for token in HIDDEN_TOKENS:
            self.assertNotIn(token, text, f"{label}: {token!r} leaked")
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        self.assertNotIn(HIDDEN_PK, user_ids_in(data), f"{label}: hidden user id leaked")

    def fetch(self, viewer, name):
        client = self.client_for(viewer)
        out = {}
        for label, method, url, params in self.endpoints(name):
            out[label] = getattr(client, method)(url, params or {})
        return out

    def test_opt_out_hidden_in_every_endpoint(self):
        self.build(hide=True)
        for name, viewer in self.viewers.items():
            responses = self.fetch(viewer, name)
            for label, r in responses.items():
                self.assert_clean(f"{name}/{label}", r.content)
            # Non-vacuous: the hidden reservation is really in the payloads.
            self.assertEqual(responses["overview"].status_code, 200)
            ov = responses["overview"].json()
            d1 = next(p for f in ov["floors"] for p in f["places"] if p["id"] == self.d1.pk)
            booked = [h for h in d1["hours"] if h["reservation_id"] == self.hidden_res.pk]
            self.assertEqual(len(booked), 3)
            self.assertTrue(all(h["state"] == "booked" and h["holder"] is None for h in booked))
            d5 = next(p for f in ov["floors"] for p in f["places"] if p["id"] == self.d5.pk)
            self.assertTrue(d5["fixed"])
            self.assertTrue(all(h["holder"] is None for h in d5["hours"]))
            self.assertEqual(responses["neighbours"].status_code, 200)
            self.assertIn(None, responses["neighbours"].json())
            self.assertEqual(responses["requests_mine"].status_code, 200)
            reqs = responses["requests_mine"].json()
            self.assertEqual(len(reqs["incoming"]), 1)
            self.assertEqual(len(reqs["outgoing"]), 2)
            for item in reqs["outgoing"]:
                self.assertEqual(item["other"]["id"], self.hidden_res.pk)
                self.assertIsNone(item["other_holder_name"])
            # Ruling 5: no reservation id of the hidden requester.
            self.assertIsNone(reqs["incoming"][0]["other"]["id"])
            self.assertEqual(responses["free_now"].status_code, 200)
            self.assertEqual(responses["reservations_mine"].status_code, 200)
            self.assertEqual(
                (responses["stats"].status_code, responses["stats_csv"].status_code),
                (200, 200) if name == "admin" else (403, 403),
            )
            if name == "admin":
                # Non-vacuous: the hidden desk reservation (3 h) is counted, nameless.
                self.assertGreaterEqual(responses["stats"].json()["quota"]["desk"]["booked_h"], 3)
        # Department admins see the reservation in the manage list, nameless.
        admin_list = self.fetch(self.lender, "admin")["manage_reservations"]
        self.assertEqual(admin_list.status_code, 200)
        row = next(r for r in admin_list.json() if r["id"] == self.hidden_res.pk)
        self.assertEqual(
            (row["holder_name"], row["holder_id"], row["booked_by_id"], row["comment"]),
            (None, None, None, ""),
        )
        # Display status (viewer None = public).
        status_ = place_status(self.d1, at=self.at(10), anonymous=False)
        self.assertEqual(status_["state"], "booked")
        self.assert_clean("place_status", json.dumps(status_, default=str))
        status_ = place_status(self.d5, at=self.at(10), anonymous=False)
        self.assertEqual(status_["state"], "booked")
        self.assert_clean("place_status fixed", json.dumps(status_, default=str))

    def test_opt_out_write_responses(self):
        """Responses of actions on the hidden holder's reservations."""
        self.build(hide=True)
        assistant = self.client_for(self.assistant)
        # Booking for the hidden person (single and series).
        r = assistant.post(f"{API}/reservations/", {
            "place_ids": [self.d2.pk], "day": self.day.isoformat(),
            "start_hour": 14, "end_hour": 15, "holder_id": HIDDEN_PK,
        }, format="json")
        self.assertEqual(r.status_code, 201)
        self.assert_clean("book for", r.content)
        r = assistant.post(f"{API}/series/", {
            "place_id": self.d3.pk, "weekdays": [self.day.weekday()],
            "start_hour": 16, "end_hour": 17,
            "valid_from": self.day.isoformat(),
            "valid_until": (self.day + timedelta(days=14)).isoformat(),
            "holder_id": HIDDEN_PK,
        }, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["created"])
        self.assert_clean("series for", r.content)
        # Admin moves the hidden holder's reservation.
        r = self.client_for(self.lender).post(
            f"{API}/reservations/{self.hidden_res.pk}/move/", {"place_id": self.d5.pk},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assert_clean("admin move", r.content)
        # Neighbour lookups of the admin on that reservation (admins act on ids).
        r = self.client_for(self.lender).get(
            f"{API}/reservations/{self.hidden_res.pk}/neighbours/"
        )
        self.assertEqual(r.status_code, 200)
        self.assert_clean("admin neighbours", r.content)

    def test_holder_sees_own_data(self):
        self.build(hide=True)
        client = self.client_for(self.hidden)
        [row] = [r for r in client.get(f"{API}/reservations/mine/").json()
                 if r["id"] == self.hidden_res.pk]
        self.assertEqual(row["holder_id"], HIDDEN_PK)
        self.assertEqual(row["comment"], "Hildegard focus time")
        ov = client.get(f"{API}/overview/", {"pool": self.pool.pk, "day": self.day.isoformat()})
        d1 = next(p for f in ov.json()["floors"] for p in f["places"] if p["id"] == self.d1.pk)
        self.assertIn("Hildegard Zwiebelkuchen", {h["holder"] for h in d1["hours"]})

    def test_control_names_visible_without_opt_out(self):
        self.build(hide=False)
        for name, viewer in self.viewers.items():
            responses = self.fetch(viewer, name)
            self.assertIn(b"Hildegard", responses["overview"].content, name)
            self.assertIn(b"Hildegard", responses["neighbours"].content, name)
            self.assertIn(b"Hildegard", responses["requests_mine"].content, name)
        self.assertIn(
            b"Hildegard", self.fetch(self.lender, "admin")["manage_reservations"].content
        )
        self.assertEqual(
            place_status(self.d1, at=self.at(10), anonymous=False)["holder"],
            "Hildegard Zwiebelkuchen",
        )

    def test_series_serializer_hides_holder(self):
        privacy.set_hide_name(self.hidden, True)
        series = Series.objects.create(
            holder=self.hidden, booked_by=self.assistant, place=self.d1, weekdays=[1],
            start_hour=9, end_hour=10, valid_from=self.day, valid_until=self.day,
        )
        data = SeriesSerializer(series, context={"viewer": self.lender}).data
        self.assertEqual((data["holder_id"], data["booked_by_id"]), (None, None))
        data = SeriesSerializer(series, context={"viewer": self.hidden}).data
        self.assertEqual(data["holder_id"], HIDDEN_PK)
        # No context: redacted (fail closed).
        self.assertIsNone(SeriesSerializer(series).data["holder_id"])


class ReleaseReasonTests(PrivacyBase):
    def test_absence_reason_neutral_for_former_assistant(self):
        res = self.reserve(
            self.d1, self.member, booked_by=self.assistant,
            status=Reservation.Status.RELEASED,
            release_reason=Reservation.ReleaseReason.ABSENCE,
        )
        def reason(viewer):
            return ReservationSerializer(res, context={"viewer": viewer}).data["release_reason"]
        self.assertEqual(reason(self.member), "absence")
        self.assertEqual(reason(self.assistant), "absence")
        self.assertEqual(reason(self.lender), "absence")
        # The assistant leaves the assistant group: only "other" now.
        DeskSettings.objects.filter(pool=self.pool).update(assistant_group=None)
        self.assistant = User.objects.get(pk=self.assistant.pk)  # fresh rights cache
        self.assertEqual(reason(self.assistant), "other")
        self.assertEqual(reason(None), "other")
        other = self.reserve(self.d2, self.member, status=Reservation.Status.RELEASED,
                             release_reason=Reservation.ReleaseReason.NO_SHOW)
        self.assertEqual(
            ReservationSerializer(other, context={"viewer": self.other}).data["release_reason"],
            "no_show",
        )


class AnonymizeTests(PrivacyBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()

    def past(self, place, holder, days_ago, **kw):
        return self.reserve(place, holder, day=self.today - timedelta(days=days_ago),
                            comment="note", **kw)

    def test_anonymize_after_retention(self):
        old = self.past(self.d1, self.member, 91, checked_in_at=timezone.now())
        old_room = self.past(self.m1, self.member, 91)
        recent = self.past(self.d2, self.member, 89)
        cancelled = self.past(self.d3, self.member, 95, status=Reservation.Status.CANCELLED)
        series = Series.objects.create(
            holder=self.member, booked_by=self.member, place=self.d4, weekdays=[0],
            start_hour=9, end_hour=10, comment="s",
            valid_from=self.today - timedelta(days=120),
            valid_until=self.today - timedelta(days=91),
        )
        in_series = self.past(self.d4, self.member, 92, series=series)
        absence_old = Absence.objects.create(
            user=self.member, kind="vacation",
            start_date=self.today - timedelta(days=100), end_date=self.today - timedelta(days=91),
        )
        absence_new = Absence.objects.create(
            user=self.member, kind="vacation",
            start_date=self.today - timedelta(days=100), end_date=self.today - timedelta(days=89),
        )
        out = StringIO()
        call_command("desks_daily", stdout=out)
        for r in (old, old_room, recent, cancelled, in_series):
            r.refresh_from_db()
        for r in (old, old_room, cancelled, in_series):
            self.assertEqual((r.holder, r.booked_by, r.comment), (None, None, ""))
        self.assertIsNone(in_series.series)
        # Statistics fields stay.
        self.assertIsNotNone(old.checked_in_at)
        self.assertEqual(cancelled.status, Reservation.Status.CANCELLED)
        self.assertEqual(old.place, self.d1)
        self.assertEqual(recent.holder, self.member)
        self.assertEqual(recent.comment, "note")
        series.refresh_from_db()
        self.assertEqual((series.holder, series.booked_by, series.comment), (None, None, ""))
        self.assertFalse(Absence.objects.filter(pk=absence_old.pk).exists())
        self.assertTrue(Absence.objects.filter(pk=absence_new.pk).exists())
        self.assertIn("anonymized", out.getvalue())
        # Idempotent.
        self.assertEqual(privacy.anonymize_due(timezone.now())["reservations"], 0)

    def test_anonymize_respects_department_retention(self):
        DeskSettings.objects.filter(pool=self.pool).update(retention_days=10)
        res = self.past(self.d1, self.member, 11)
        privacy.anonymize_due(timezone.now())
        res.refresh_from_db()
        self.assertIsNone(res.holder)

    def test_anonymize_hidden_right_after_end(self):
        privacy.set_hide_name(self.hidden, True)
        now = timezone.now()
        local = timezone.localtime(now, hours.TZ)
        ended = Reservation.objects.create(
            place=self.d1, holder=self.hidden, booked_by=self.hidden, holder_hidden=True,
            comment="x",
            period=(now - timedelta(hours=3), now - timedelta(minutes=1)),
        )
        running = Reservation.objects.create(
            place=self.d2, holder=self.hidden, booked_by=self.hidden, holder_hidden=True,
            period=(now - timedelta(hours=1), now + timedelta(hours=1)),
        )
        room = Reservation.objects.create(
            place=self.m1, holder=self.hidden, booked_by=self.hidden,
            period=(now - timedelta(hours=3), now - timedelta(minutes=1)),
        )
        visible = Reservation.objects.create(
            place=self.d3, holder=self.member, booked_by=self.member,
            period=(now - timedelta(hours=3), now - timedelta(minutes=1)),
        )
        counts = privacy.anonymize_due(now)
        self.assertEqual(counts["reservations"], 1)
        for r in (ended, running, room, visible):
            r.refresh_from_db()
        self.assertEqual((ended.holder, ended.booked_by, ended.comment), (None, None, ""))
        # No-show recorded before the holder link goes (statistics).
        self.assertTrue(ended.no_show)
        self.assertEqual(running.holder, self.hidden)
        self.assertEqual(room.holder, self.hidden)
        self.assertEqual(visible.holder, self.member)
        del local

    def test_anonymize_deletes_ended_requests_after_retention(self):
        a = self.past(self.d1, self.member, 91)
        b = self.past(self.d2, self.other, 91)
        swap = SwapRequest.objects.create(from_reservation=a, to_reservation=b, status="expired")
        release = ReleaseRequest.objects.create(reservation=a, requester=self.other,
                                                status="declined")
        c = self.past(self.d3, self.member, 5)
        keep = ReleaseRequest.objects.create(reservation=c, requester=self.other,
                                             status="declined")
        counts = privacy.anonymize_due(timezone.now())
        self.assertEqual(counts["requests"], 2)
        self.assertFalse(SwapRequest.objects.filter(pk=swap.pk).exists())
        self.assertFalse(ReleaseRequest.objects.filter(pk=release.pk).exists())
        self.assertTrue(ReleaseRequest.objects.filter(pk=keep.pk).exists())


class SwapNotificationTests(PrivacyBase):
    def test_swap_request_context_hides_hidden_requester_id(self):
        privacy.set_hide_name(self.hidden, True)
        mine = booking.book(
            actor=self.hidden, holder=self.hidden, places=[self.d1], day=self.day,
            start_hour=9, end_hour=12,
        )[0]
        theirs = self.reserve(self.d2, self.other)
        with self.captureOnCommitCallbacks(execute=True):
            requests_svc.request_swap(user=self.hidden, mine=mine, theirs=theirs)
        [call] = [c for c in self.notify.call_args_list if c.args[1] == "swap_request"]
        self.assertEqual(call.args[0], self.other)
        context = call.args[2]
        self.assertIsNone(context["offered"]["id"])
        self.assertEqual(context["own"]["id"], theirs.pk)
        self.assertNotIn(str(HIDDEN_PK), json.dumps(context, default=str))
        # A visible requester's reservation id is kept.
        mine2 = self.reserve(self.d3, self.member)
        theirs2 = self.reserve(self.d4, self.other, start=10, end=11)
        self.notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            requests_svc.request_swap(user=self.member, mine=mine2, theirs=theirs2)
        self.assertEqual(self.notify.call_args.args[2]["offered"]["id"], mine2.pk)


class AnonymizeExtraTests(AnonymizeTests):
    """Fix round 1: owner use, fresh groups, hidden series."""

    def test_anonymized_fixed_owner_row_never_becomes_no_show(self):
        from desksharing import release
        self.d1.fixed_owner = self.member
        self.d1.save()
        now = timezone.now()
        res = Reservation.objects.create(
            place=self.d1, holder=self.member, booked_by=self.member, holder_hidden=True,
            period=(now - timedelta(hours=3), now - timedelta(minutes=1)),
        )
        self.assertTrue(res.owner_use)
        privacy.anonymize_due(now)
        res.refresh_from_db()
        self.assertIsNone(res.holder)
        self.assertTrue(res.owner_use)
        self.assertFalse(res.no_show)
        release.tick(now)
        res.refresh_from_db()
        self.assertFalse(res.no_show)

    def test_owner_use_follows_move_and_swap(self):
        self.d1.fixed_owner = self.member
        self.d1.save()
        [res] = booking.book(
            actor=self.member, holder=self.member, places=[self.d2], day=self.day,
            start_hour=9, end_hour=10,
        )
        self.assertFalse(res.owner_use)
        booking.move(res, actor=self.member, to_place=self.d1)
        res.refresh_from_db()
        self.assertTrue(res.owner_use)
        # Swap (the low-level exchange; the validation is tested elsewhere).
        a = self.reserve(self.d3, self.member, start=14, end=15)
        b = self.reserve(self.d1, self.other, start=14, end=15)
        requests_svc._swap_places(a, b)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual((a.place, a.owner_use), (self.d1, True))
        self.assertEqual((b.place, b.owner_use), (self.d3, False))

    def test_anonymization_assigns_fresh_groups(self):
        a = self.past(self.d1, self.member, 91)
        b = self.past(self.d2, self.member, 91)
        Reservation.objects.filter(pk=b.pk).update(group=a.group)
        old_group = a.group
        privacy.anonymize_due(timezone.now())
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertNotEqual(a.group, old_group)
        self.assertNotEqual(a.group, b.group)

    def test_hidden_series_anonymized_right_after_end(self):
        privacy.set_hide_name(self.hidden, True)
        def series(place=None, **kw):
            return Series.objects.create(
                holder=self.hidden, booked_by=self.hidden, place=place or self.d1,
                weekdays=[0], start_hour=9, end_hour=10, comment="s",
                valid_from=self.today - timedelta(days=30), **kw,
            )
        ended = series(valid_until=self.today - timedelta(days=1))
        cancelled = series(valid_until=self.today + timedelta(days=30),
                           cancelled_at=timezone.now() - timedelta(minutes=1))
        running = series(valid_until=self.today + timedelta(days=30))
        room = series(place=self.m1, valid_until=self.today - timedelta(days=1))
        counts = privacy.anonymize_due(timezone.now())
        self.assertEqual(counts["series"], 2)
        for s_ in (ended, cancelled, running, room):
            s_.refresh_from_db()
        self.assertEqual((ended.holder, ended.booked_by, ended.comment), (None, None, ""))
        self.assertIsNone(cancelled.holder)
        self.assertEqual(running.holder, self.hidden)
        self.assertEqual(room.holder, self.hidden)
