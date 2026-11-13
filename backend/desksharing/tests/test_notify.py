# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import re
from datetime import date, datetime, timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from desksharing import (
    absences, actions, booking, hours, notify, privacy, reminders, requests as requests_svc,
    series as series_svc,
)
from desksharing.models import DeskProfile, NotificationPreference, Reservation, Series
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_hours import next_weekday

PREFS = f"{API}/notification-preferences/"
ACTIONS = f"{API}/actions/"


class NotifyTestBase(TestCase):
    def setUp(self):
        setup_department(self)
        for user in (self.member, self.other, self.lender):
            user.email = f"{user.username}@example.org"
            user.language = "en"
            user.save()
        self.day = next_weekday(1)

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def reserve(self, place, holder, start=9, end=12, day=None, **kw):
        return Reservation.objects.create(
            place=place, holder=holder, booked_by=kw.pop("booked_by", holder),
            period=hours.local_range(day or self.day, start, end), **kw,
        )

    def mails_to(self, user):
        return [m for m in mail.outbox if user.email in m.to]


class ChannelTests(NotifyTestBase):
    def test_default_channel_mail(self):
        notify.notify(self.member, notify.DAILY_SUMMARY, {"reservations": [self.reserve(self.d1, self.member)]})
        self.assertEqual(len(self.mails_to(self.member)), 1)
        self.assertEqual(notify.channel_for(self.member, notify.GRACE_NUDGE), "mail")

    def test_off_sends_nothing(self):
        notify.set_preferences(self.member, {notify.DAILY_SUMMARY: "off"})
        notify.notify(self.member, notify.DAILY_SUMMARY, {"reservations": [self.reserve(self.d1, self.member)]})
        self.assertEqual(mail.outbox, [])

    def test_push_rejected_until_enabled(self):
        client = self.api(self.member)
        for channel in ("push", "both", "nonsense"):
            r = client.put(PREFS, {notify.GRACE_NUDGE: channel}, format="json")
            self.assertEqual(r.status_code, 400, channel)
        self.assertEqual(client.put(PREFS, {"unknown": "mail"}, format="json").status_code, 400)
        self.assertFalse(NotificationPreference.objects.exists())

    def test_preferences_api_partial_update(self):
        client = self.api(self.member)
        data = client.get(PREFS).json()
        self.assertEqual(set(data), set(notify.EVENTS))
        self.assertEqual(set(data.values()), {"mail"})
        r = client.put(PREFS, {notify.DAILY_SUMMARY: "off"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[notify.DAILY_SUMMARY], "off")
        self.assertEqual(r.json()[notify.GRACE_NUDGE], "mail")
        client.put(PREFS, {notify.DAILY_SUMMARY: "mail"}, format="json")
        self.assertEqual(client.get(PREFS).json()[notify.DAILY_SUMMARY], "mail")
        self.assertEqual(APIClient().get(PREFS).status_code in (401, 403), True)

    def test_push_channel_hook(self):
        sender = mock.Mock()
        notify.register_channel("push", sender)
        self.addCleanup(notify._senders.clear)
        NotificationPreference.objects.create(user=self.member, event=notify.GRACE_NUDGE, channel="both")
        res = self.reserve(self.d1, self.member)
        notify.notify(self.member, notify.GRACE_NUDGE, {"reservation": res})
        sender.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_event_rejected(self):
        with self.assertRaises(ValueError):
            notify.notify(self.member, "bogus", {})


class DailySummaryTests(NotifyTestBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localtime(timezone.now(), hours.TZ).date()
        self.at = lambda hour: datetime(
            self.today.year, self.today.month, self.today.day, hour, 5, tzinfo=hours.TZ
        )

    def test_daily_summary_only_with_reservations(self):
        self.reserve(self.d1, self.member, 14, 16, day=self.today)
        self.assertEqual(reminders.send_daily_summaries(self.at(7)), 1)
        self.assertEqual(len(self.mails_to(self.member)), 1)
        self.assertEqual(self.mails_to(self.other), [])
        self.assertIn("D1", self.mails_to(self.member)[0].body)

    def test_summary_not_before_hour_and_not_twice(self):
        self.reserve(self.d1, self.member, 14, 16, day=self.today)
        with self.settings(DESKS_SUMMARY_HOUR=8):
            self.assertEqual(reminders.send_daily_summaries(self.at(7)), 0)
            self.assertEqual(reminders.send_daily_summaries(self.at(9)), 1)
            self.assertEqual(reminders.send_daily_summaries(self.at(10)), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(DeskProfile.objects.get(user=self.member).last_summary_date, self.today)

    def test_summary_skips_cancelled_and_over(self):
        self.reserve(self.d1, self.member, 9, 10, day=self.today)  # over at 12:05
        self.reserve(self.d2, self.other, 14, 15, day=self.today, status=Reservation.Status.CANCELLED)
        self.assertEqual(reminders.send_daily_summaries(self.at(12)), 0)

    def test_command_runs(self):
        self.reserve(self.d1, self.member, 14, 16, day=self.today)
        with mock.patch("desksharing.reminders.timezone.now", return_value=self.at(9)):
            call_command("desks_daily", stdout=mock.MagicMock())
        self.assertEqual(len(self.mails_to(self.member)), 1)


class ActionLinkTests(NotifyTestBase):
    def nudge_token(self, res, action="release"):
        notify.notify(res.holder, notify.GRACE_NUDGE, {"reservation": res})
        [msg] = self.mails_to(res.holder)
        match = re.search(rf"/desks/a/([^\s?]+)\?action={action}", msg.body)
        self.assertIsNotNone(match, msg.body)
        return match.group(1)

    def test_signed_action_link_releases(self):
        res = self.reserve(self.d1, self.member, day=timezone.localdate() + timedelta(days=1))
        token = self.nudge_token(res)
        self.assertIn("http://localhost:5173/desks/a/", self.mails_to(self.member)[0].body)
        r = self.api(self.other).post(ACTIONS, {"token": token, "action": "release"}, format="json")
        self.assertEqual(r.status_code, 403)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)
        r = self.api(self.member).post(ACTIONS, {"token": token, "action": "release"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.CANCELLED)
        self.assertEqual(res.release_reason, Reservation.ReleaseReason.HOLDER)
        again = self.api(self.member).post(ACTIONS, {"token": token, "action": "release"}, format="json")
        self.assertEqual(again.status_code, 409)

    def test_later_action(self):
        day = timezone.localdate() + timedelta(days=1)
        res = self.reserve(self.d1, self.member, day=day)
        token = self.nudge_token(res, "later")
        until = hours.local_dt(day, 10).isoformat()
        with mock.patch("django.utils.timezone.now", return_value=hours.local_dt(day, 9)):
            r = self.api(self.member).post(
                ACTIONS, {"token": token, "action": "later", "until": until}, format="json"
            )
            self.assertEqual(r.status_code, 200, r.content)
            missing = self.api(self.member).post(ACTIONS, {"token": token, "action": "later"}, format="json")
            self.assertEqual(missing.status_code, 400)
        res.refresh_from_db()
        self.assertEqual(res.late_until, hours.local_dt(day, 10))

    def test_signed_link_expires_after_end(self):
        res = self.reserve(self.d1, self.member)
        token = notify.make_action_token(res, self.member)
        after = hours.local_dt(self.day, 12) + timedelta(minutes=1)
        with self.assertRaises(actions.ActionError) as cm:
            actions.perform(token, "release", user=self.member, now=after)
        self.assertEqual(cm.exception.status, 410)
        # Also through the API (a past reservation).
        past = self.reserve(self.d2, self.member, day=timezone.localdate() - timedelta(days=2))
        r = self.api(self.member).post(
            ACTIONS, {"token": notify.make_action_token(past, self.member), "action": "release"},
            format="json",
        )
        self.assertEqual(r.status_code, 410)

    def test_tampered_token_rejected(self):
        res = self.reserve(self.d1, self.member)
        token = notify.make_action_token(res, self.member)
        r = self.api(self.member).post(ACTIONS, {"token": token + "x", "action": "release"}, format="json")
        self.assertEqual(r.status_code, 400)


class ActionContextTests(NotifyTestBase):
    def get(self, user, token):
        return self.api(user).get(f"{ACTIONS}context/", {"token": token})

    def test_context_returns_reservation_without_state_change(self):
        res = self.reserve(self.d1, self.member, day=timezone.localdate() + timedelta(days=1))
        token = notify.make_action_token(res, self.member)
        r = self.get(self.member, token)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.data["expired"])
        self.assertEqual(r.data["reservation"]["id"], res.pk)
        self.assertEqual(r.data["reservation"]["place"], self.d1.name)
        self.assertFalse(r.data["reservation"]["checked_in"])
        res.refresh_from_db()
        self.assertEqual(res.status, Reservation.Status.ACTIVE)

    def test_context_errors(self):
        res = self.reserve(self.d1, self.member)
        token = notify.make_action_token(res, self.member)
        self.assertEqual(self.get(self.other, token).status_code, 403)
        self.assertEqual(self.get(self.member, token + "x").status_code, 400)
        self.assertEqual(self.get(self.member, "").status_code, 400)
        self.assertEqual(APIClient().get(f"{ACTIONS}context/", {"token": token}).status_code in (401, 403), True)

    def test_context_flags_expired(self):
        past = self.reserve(self.d2, self.member, day=timezone.localdate() - timedelta(days=2))
        r = self.get(self.member, notify.make_action_token(past, self.member))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["expired"])


class SeriesReminderTests(NotifyTestBase):
    def make_series(self, valid_until):
        return Series.objects.create(
            holder=self.member, booked_by=self.member, place=self.d1, weekdays=[1],
            start_hour=9, end_hour=11, valid_from=valid_until - timedelta(days=60),
            valid_until=valid_until,
        )

    def noon(self, day):
        return hours.local_dt(day, 12)

    def test_series_reminders_28_and_7_days(self):
        today = date(2027, 3, 1)
        series = self.make_series(today + timedelta(days=28))
        self.assertEqual(reminders.send_series_reminders(self.noon(today - timedelta(days=1))), 0)
        self.assertEqual(reminders.send_series_reminders(self.noon(today)), 1)
        self.assertEqual(reminders.send_series_reminders(self.noon(today)), 0)
        self.assertEqual(reminders.send_series_reminders(self.noon(today + timedelta(days=10))), 0)
        self.assertEqual(reminders.send_series_reminders(self.noon(today + timedelta(days=21))), 1)
        self.assertEqual(reminders.send_series_reminders(self.noon(today + timedelta(days=22))), 0)
        self.assertEqual(len(self.mails_to(self.member)), 2)
        series.refresh_from_db()
        self.assertTrue(series.reminder_28_sent and series.reminder_7_sent)

    def test_late_first_run_sends_one(self):
        today = date(2027, 3, 1)
        self.make_series(today + timedelta(days=5))
        self.assertEqual(reminders.send_series_reminders(self.noon(today)), 1)
        self.assertEqual(reminders.send_series_reminders(self.noon(today + timedelta(days=1))), 0)

    def test_extension_resets_markers(self):
        today = timezone.localdate()
        series = self.make_series(today + timedelta(days=20))
        reminders.send_series_reminders()
        series.refresh_from_db()
        self.assertTrue(series.reminder_28_sent)
        series_svc.extend_series(series, actor=self.member)
        series.refresh_from_db()
        self.assertFalse(series.reminder_28_sent or series.reminder_7_sent)

    def test_cancelled_series_not_reminded(self):
        today = date(2027, 3, 1)
        series = self.make_series(today + timedelta(days=7))
        Series.objects.filter(pk=series.pk).update(cancelled_at=timezone.now())
        self.assertEqual(reminders.send_series_reminders(self.noon(today)), 0)


class BookedForYouTests(NotifyTestBase):
    def test_range_booking_one_mail(self):
        mon = next_weekday(0)
        booking.book_range(
            actor=self.lender, holder=self.member, places=[self.m1], day=mon,
            last_day=mon + timedelta(days=3), start_hour=9, end_hour=12,
        )
        self.assertEqual(len(self.mails_to(self.member)), 1)
        self.assertEqual(self.mails_to(self.member)[0].body.count("M1"), 4)

    def test_series_for_someone_else_one_mail(self):
        first = next_weekday(1)
        result = series_svc.create_series(
            actor=self.lender, holder=self.member, place=self.d1, weekdays=[first.weekday()],
            start_hour=9, end_hour=11, valid_from=first, valid_until=first + timedelta(days=28),
        )
        self.assertGreater(len(result.created), 2)
        self.assertEqual(len(self.mails_to(self.member)), 1)
        self.assertEqual(self.mails_to(self.member)[0].body.count("D1"), len(result.created))

    def test_own_booking_no_mail(self):
        booking.book(
            actor=self.member, holder=self.member, places=[self.d1], day=self.day,
            start_hour=9, end_hour=11,
        )
        self.assertEqual(mail.outbox, [])


class PrivacyMailTests(NotifyTestBase):
    def test_mail_never_names_hidden_requester(self):
        privacy.set_hide_name(self.other, True)
        self.other.first_name = "Ola"
        self.other.save()
        mine = self.reserve(self.d1, self.other)  # hidden holder
        theirs = self.reserve(self.d2, self.member)
        with self.captureOnCommitCallbacks(execute=True):
            requests_svc.request_swap(user=self.other, mine=mine, theirs=theirs)
        with self.captureOnCommitCallbacks(execute=True):
            requests_svc.request_release(user=self.other, reservation=theirs, show_name=False)
        self.assertEqual(len(self.mails_to(self.member)), 2)
        for msg in self.mails_to(self.member):
            self.assertNotIn("Ola", msg.body)
            self.assertNotIn("other", msg.body.replace("another", ""))
            self.assertNotIn(self.other.email, msg.body)

    def test_release_request_names_requester_only_when_shown(self):
        theirs = self.reserve(self.d2, self.member)
        with self.captureOnCommitCallbacks(execute=True):
            requests_svc.request_release(user=self.other, reservation=theirs, show_name=True)
        self.assertIn("Ola", self.mails_to(self.member)[0].body)

    def test_booker_named_unless_opted_out(self):
        res = self.reserve(self.d1, self.member, booked_by=self.lender)
        notify.notify(self.member, notify.BOOKED_FOR_YOU, {"reservations": [res]})
        self.assertIn("Lea", mail.outbox[-1].body)
        privacy.set_hide_name(self.lender, True)
        notify.notify(self.member, notify.BOOKED_FOR_YOU, {"reservations": [res]})
        self.assertNotIn("Lea", mail.outbox[-1].body)


class RenderAllEventsTests(NotifyTestBase):
    def test_every_event_renders_in_both_languages(self):
        res = self.reserve(self.d1, self.member)
        series = Series.objects.create(
            holder=self.member, booked_by=self.member, place=self.d1, weekdays=[1],
            start_hour=9, end_hour=11, valid_from=self.day, valid_until=self.day + timedelta(days=7),
        )
        brief = requests_svc._brief(res)
        contexts = {
            notify.DAILY_SUMMARY: {"reservations": [res]},
            notify.GRACE_NUDGE: {"reservation": res},
            notify.RELEASED_NO_SHOW: {"reservation": res, "alternatives": [self.d2]},
            notify.RELEASED_OTHER: {"reservation": res, "reason": "absence"},
            notify.BOOKED_FOR_YOU: {"reservations": [res]},
            notify.ADMIN_CHANGED: {"reservation": res, "action": "move", "from_place": self.d2},
            notify.SWAP_REQUEST: {"request_id": 1, "offered": brief, "own": brief},
            notify.SWAP_ANSWER: {"request_id": 1, "accepted": True, "reservation": brief, "previous": brief},
            notify.RELEASE_REQUEST: {"request_id": 1, "reservation": brief},
            notify.RELEASE_ANSWER: {"request_id": 1, "accepted": False, "reservation": brief},
            notify.SERIES_EXTENSION_DUE: {"series": series, "days": 7},
        }
        self.assertEqual(set(contexts), set(notify.EVENTS))
        for lang in ("en", "de"):
            self.member.language = lang
            self.member.save()
            mail.outbox.clear()
            for event, ctx in contexts.items():
                notify.notify(self.member, event, ctx)
            self.assertEqual(len(mail.outbox), len(notify.EVENTS), lang)
        de = mail.outbox[0]
        self.assertNotIn("Ressource", de.body)
        self.assertNotIn("Gerät", de.body)
        self.assertIn("Arbeitsplatz", " ".join(m.body for m in mail.outbox))


class BulkMailTests(NotifyTestBase):
    def test_admin_deletes_series_one_mail(self):
        first = next_weekday(1)
        result = series_svc.create_series(
            actor=self.member, holder=self.member, place=self.d1, weekdays=[first.weekday()],
            start_hour=9, end_hour=11, valid_from=first, valid_until=first + timedelta(days=35),
        )
        self.assertEqual(len(result.created), 6)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            series_svc.delete_series(result.series, actor=self.lender, reason="Umbau")
        mails = self.mails_to(self.member)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails[0].body.count("D1"), 6)
        self.assertIn("Umbau", mails[0].body)

    def test_block_releases_grouped_per_holder(self):
        from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

        from lending.models import Block

        self.reserve(self.d1, self.member, 8, 9)
        self.reserve(self.d2, self.member, 10, 11)
        self.reserve(self.d1, self.member, 13, 14)
        self.reserve(self.d3, self.other, 9, 10)
        mail.outbox.clear()
        start = hours.local_dt(self.day, 0)
        with self.captureOnCommitCallbacks(execute=True):
            Block.objects.create(
                period=DateTimeTZRange(start, start + timedelta(days=1)), reason="Feiertag"
            )
        self.assertEqual(len(self.mails_to(self.member)), 1)
        self.assertEqual(len(self.mails_to(self.other)), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.mails_to(self.member)[0].body.count("D1") + self.mails_to(self.member)[0].body.count("D2"), 3)

    def test_absence_by_assistant_one_mail(self):
        for hour in (8, 10):
            self.reserve(self.d1, self.member, hour, hour + 1)
        mail.outbox.clear()
        with mock.patch("desksharing.rights.assistant_pool_ids", return_value={self.pool.pk}):
            with self.captureOnCommitCallbacks(execute=True):
                absences.add_absence(
                    actor=self.lender, user=self.member, start_date=self.day,
                    end_date=self.day, kind="vacation",
                )
        self.assertEqual(len(self.mails_to(self.member)), 1)


class FooterTests(NotifyTestBase):
    def test_desk_mails_link_to_desks_not_bookings(self):
        res = self.reserve(self.d1, self.member)
        notify.notify(self.member, notify.DAILY_SUMMARY, {"reservations": [res]})
        body = mail.outbox[0].body
        self.assertNotIn("/bookings", body)
        self.assertIn("/desks/mine", body)

    def test_lending_footer_unchanged(self):
        from lending.notifications import user_mail_body

        self.assertIn("/bookings", user_mail_body(self.member, "x"))

    def test_summary_claim_is_atomic(self):
        today = timezone.localtime(timezone.now(), hours.TZ).date()
        self.reserve(self.d1, self.member, 14, 16, day=today)
        at = hours.local_dt(today, 9)
        self.assertEqual(reminders.send_daily_summaries(at), 1)
        self.assertEqual(reminders.send_daily_summaries(at), 0)
