# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup
from desksharing.models import FavoritePlace, Floor, Place, Room
from desksharing.tests.test_booking import API, setup_department
from desksharing.tests.test_rights import make_pool

User = get_user_model()


class FavoriteTests(TestCase):
    def setUp(self):
        setup_department(self)
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def ids(self, client=None):
        r = (client or self.client).get(f"{API}/favorites/")
        self.assertEqual(r.status_code, 200)
        return r.data["place_ids"]

    def test_mark_list_unmark(self):
        self.assertEqual(self.ids(), [])
        for place in (self.d2, self.m1, self.d2):  # idempotent
            r = self.client.put(f"{API}/favorites/{place.pk}/")
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.ids(), [self.d2.pk, self.m1.pk])
        self.assertEqual(FavoritePlace.objects.filter(user=self.member).count(), 2)
        self.assertEqual(self.client.delete(f"{API}/favorites/{self.d2.pk}/").status_code, 200)
        self.assertEqual(self.client.delete(f"{API}/favorites/{self.d2.pk}/").status_code, 200)
        self.assertEqual(self.ids(), [self.m1.pk])

    def test_personal(self):
        self.client.put(f"{API}/favorites/{self.d1.pk}/")
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(self.ids(other), [])

    def test_only_bookable_places(self):
        foreign_pool = make_pool("PoolB", AccessGroup.objects.create(name="Dept B"))
        foreign_room = Room.objects.create(
            floor=Floor.objects.create(pool=foreign_pool, name="F"), name="R"
        )
        foreign = Place.objects.create(room=foreign_room, name="X")
        self.assertEqual(self.client.put(f"{API}/favorites/{foreign.pk}/").status_code, 404)
        self.assertEqual(self.client.put(f"{API}/favorites/999999/").status_code, 404)
        restricted = Place.objects.create(room=self.room, name="Boss")
        restricted.access_groups.add(AccessGroup.objects.create(name="Board"))
        self.assertEqual(self.client.put(f"{API}/favorites/{restricted.pk}/").status_code, 404)
        self.assertFalse(FavoritePlace.objects.exists())

    def test_lost_rights_and_deactivation_drop_silently(self):
        for place in (self.d1, self.d2, self.d3):
            self.client.put(f"{API}/favorites/{place.pk}/")
        self.d1.access_groups.add(AccessGroup.objects.create(name="Board"))
        Place.objects.filter(pk=self.d2.pk).update(is_active=False)
        self.assertEqual(self.ids(), [self.d3.pk])
        self.assertEqual(
            list(FavoritePlace.objects.values_list("place_id", flat=True)), [self.d3.pk]
        )
        # Leaving the department drops the rest.
        self.group.members.remove(self.member)
        fresh = APIClient()
        fresh.force_authenticate(User.objects.get(pk=self.member.pk))
        self.assertEqual(self.ids(fresh), [])
        self.assertFalse(FavoritePlace.objects.exists())

    def test_anonymous_refused(self):
        self.assertEqual(APIClient().get(f"{API}/favorites/").status_code, 403)
