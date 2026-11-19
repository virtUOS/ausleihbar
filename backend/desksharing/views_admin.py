# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Batch creation of rooms/places, name suggestions, department assignment
and the campus-wide admin setting."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import roles
from catalog.models import ResourcePool

from . import assignment, naming, rights
from .models import DeskAdminSetting, Floor, Place, Room
from .serializers import PlaceSerializer, RoomSerializer
from .views import IsDeskAdminOrAppAdmin, save_unique


def _id_list(value, field, *, required=False) -> list[int]:
    if value in (None, ""):
        value = []
    if not isinstance(value, list) or any(
        isinstance(v, bool) or not isinstance(v, int) for v in value
    ):
        raise serializers.ValidationError({field: ["Expected a list of ids."]})
    if required and not value:
        raise serializers.ValidationError({field: ["This field is required."]})
    return list(dict.fromkeys(value))


def _name_taken(exc: serializers.ValidationError, message: str) -> bool:
    detail = exc.detail
    return isinstance(detail, dict) and [str(m) for m in detail.get("name", [])] == [message]


class RoomBatchView(APIView):
    """Create ``prefix`` + number rooms on a floor; names that already exist
    are skipped. App admins only."""

    permission_classes = [IsDeskAdminOrAppAdmin]

    def post(self, request):
        if not roles.is_app_admin(request.user):
            raise PermissionDenied("Only app admins may create or delete rooms.")
        data = request.data if isinstance(request.data, dict) else {}
        floor = Floor.objects.filter(pk=data.get("floor")).first() if isinstance(
            data.get("floor"), int
        ) else None
        if floor is None:
            raise serializers.ValidationError({"floor": ["Unknown floor."]})
        pool = None
        if data.get("pool") is not None:
            pool = ResourcePool.objects.filter(pk=data["pool"]).first() if isinstance(
                data["pool"], int
            ) else None
            if pool is None:
                raise serializers.ValidationError({"pool": ["Unknown department."]})
        prefix = data.get("prefix", "")
        if not isinstance(prefix, str):
            raise serializers.ValidationError({"prefix": ["Not a valid string."]})
        try:
            names = naming.room_range(prefix, str(data.get("start", "")), str(data.get("end", "")))
        except ValueError as exc:
            raise serializers.ValidationError({"start": [str(exc)]})
        dry_run = data.get("dry_run") is True
        created, skipped = [], []
        with transaction.atomic():
            for name in names:
                ser = RoomSerializer(
                    data={"floor": floor.pk, "name": name, "pool": pool.pk if pool else None}
                )
                try:
                    ser.is_valid(raise_exception=True)
                except serializers.ValidationError as exc:
                    if not _name_taken(exc, ser.name_taken_message):
                        raise
                    skipped.append(name)
                    continue
                if not dry_run:
                    save_unique(ser)
                created.append(name)
        return Response({"created": created, "skipped": skipped})


class PlaceBatchView(APIView):
    """Create ``count`` places per room, named after the room's pattern."""

    permission_classes = [IsDeskAdminOrAppAdmin]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        room_ids = _id_list(data.get("room_ids"), "room_ids", required=True)
        count = data.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 50:
            raise serializers.ValidationError({"count": ["Enter a number between 1 and 50."]})
        kind = data.get("kind", Place.Kind.DESK)
        if kind not in Place.Kind.values:
            raise serializers.ValidationError({"kind": ["Invalid kind."]})
        rooms = {r.pk: r for r in Room.objects.select_related("floor").filter(pk__in=room_ids)}
        if set(room_ids) - set(rooms):
            raise serializers.ValidationError({"room_ids": ["Unknown room."]})
        ordered = [rooms[pk] for pk in room_ids]
        if any(not rights.can_admin_room(request.user, room) for room in ordered):
            raise PermissionDenied("You do not administer this department.")
        pattern = DeskAdminSetting.load().place_name_pattern
        dry_run = data.get("dry_run") is True
        created, skipped, planned = [], [], []
        with transaction.atomic():
            for room in ordered:
                for name in naming.next_place_names(room, count, pattern, extra_taken=planned):
                    ser = PlaceSerializer(data={"room": room.pk, "name": name, "kind": kind})
                    try:
                        ser.is_valid(raise_exception=True)
                    except serializers.ValidationError as exc:
                        if not _name_taken(exc, ser.name_taken_message):
                            raise
                        skipped.append(name)
                        continue
                    planned.append(name)
                    if not dry_run:
                        save_unique(ser)
                    created.append(name)
        return Response({"created": created, "skipped": skipped})


class PlaceNameSuggestionsView(APIView):
    permission_classes = [IsDeskAdminOrAppAdmin]

    def get(self, request):
        params = request.query_params
        room = Room.objects.select_related("floor").filter(
            pk=params["room"] if params.get("room", "").isdigit() else None
        ).first()
        if room is None:
            raise serializers.ValidationError({"room": ["Unknown room."]})
        if not rights.can_admin_room(request.user, room):
            raise PermissionDenied("You do not administer this department.")
        raw = params.get("count", "1")
        if not (raw.isdigit() and 1 <= int(raw) <= 50):
            raise serializers.ValidationError({"count": ["Enter a number between 1 and 50."]})
        pattern = DeskAdminSetting.load().place_name_pattern
        return Response({"names": naming.next_place_names(room, int(raw), pattern)})


class AssignView(APIView):
    """Assign rooms/places to a department; with ``access_group_ids`` /
    ``admin_group_ids`` the groups are added to the department and desksharing
    is switched on first. All or nothing, app admins only."""

    permission_classes = [IsDeskAdminOrAppAdmin]

    def post(self, request):
        user = request.user
        if not roles.is_app_admin(user):
            raise PermissionDenied("Only app admins may assign departments.")
        data = request.data if isinstance(request.data, dict) else {}
        room_ids = _id_list(data.get("room_ids"), "room_ids")
        place_ids = _id_list(data.get("place_ids"), "place_ids")
        access_ids = _id_list(data.get("access_group_ids"), "access_group_ids")
        admin_ids = _id_list(data.get("admin_group_ids"), "admin_group_ids")
        follow_room = data.get("follow_room") is True
        if not room_ids and not place_ids:
            raise serializers.ValidationError({"room_ids": ["Choose rooms or places."]})
        rooms = list(Room.objects.filter(pk__in=room_ids))
        if len(rooms) != len(room_ids):
            raise serializers.ValidationError({"room_ids": ["Unknown room."]})
        places = list(Place.objects.filter(pk__in=place_ids))
        if len(places) != len(place_ids):
            raise serializers.ValidationError({"place_ids": ["Unknown place."]})
        pool = None
        if "pool" not in data:
            raise serializers.ValidationError({"pool": ["This field is required."]})
        if data["pool"] is not None:
            pool = ResourcePool.objects.filter(pk=data["pool"]).first() if isinstance(
                data["pool"], int
            ) and not isinstance(data["pool"], bool) else None
            if pool is None:
                raise serializers.ValidationError({"pool": ["Unknown department."]})
        if pool is None and (access_ids or admin_ids):
            raise serializers.ValidationError({"pool": ["Choose a department for the groups."]})
        try:
            with transaction.atomic():
                if pool is not None:
                    assignment.add_department_groups(
                        pool, access_group_ids=access_ids, admin_group_ids=admin_ids, actor=user
                    )
                    if not follow_room:
                        assignment.ensure_desksharing_enabled(pool)
                changed = 0
                if rooms:
                    changed += assignment.assign_rooms(rooms, pool, actor=user)
                if places:
                    changed += assignment.assign_places(
                        places, pool, actor=user, follow_room=follow_room
                    )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "error_dict") else exc.messages
            )
        return Response({"places_changed": changed}, status=status.HTTP_200_OK)


class AdminSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeskAdminSetting
        fields = ["place_name_pattern"]


class AdminSettingView(APIView):
    """Campus-wide setting: any department admin reads, app admins change."""

    permission_classes = [IsDeskAdminOrAppAdmin]

    def get(self, request):
        return Response(AdminSettingSerializer(DeskAdminSetting.load()).data)

    def put(self, request):
        if not roles.is_app_admin(request.user):
            raise PermissionDenied("Only app admins may change this.")
        ser = AdminSettingSerializer(DeskAdminSetting.load(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
