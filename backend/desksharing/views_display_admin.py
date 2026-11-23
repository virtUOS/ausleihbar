# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Management of door displays: pair, rename, move, revoke, preview."""
import io

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import roles

from . import displays, door_render, door_session, rights
from .door_view import build_door_view
from .models import Display, Room
from .serializers import DisplaySerializer
from .views import IsDeskAdminOrAppAdmin


def _png(image) -> HttpResponse:
    buf = io.BytesIO()
    image.convert("L").save(buf, "PNG")
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    return response


def _visible(user):
    """Paired displays of the user's departments (all for app admins)."""
    qs = Display.objects.filter(room__isnull=False).select_related("room__floor__building")
    if roles.is_app_admin(user):
        return qs
    return qs.filter(room__pool_id__in=rights.admin_pool_ids(user))


def _target_room(user, value) -> Room:
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise ValidationError({"room": "A room is required."})
    room = Room.objects.select_related("floor__building").filter(pk=pk).first()
    if room is None:
        raise ValidationError({"room": "Unknown room."})
    if not rights.can_admin_room(user, room):
        raise PermissionDenied("You may not administer this room.")
    return room


def _normalise(code) -> str:
    return "".join(str(code or "").upper().replace("-", "").split())


class DisplayListView(APIView):
    permission_classes = [IsDeskAdminOrAppAdmin]

    def get(self, request):
        qs = _visible(request.user).order_by("room__floor__building__code", "name", "pk")
        pool = request.query_params.get("pool")
        if pool:
            try:
                qs = qs.filter(room__pool_id=int(pool))
            except ValueError:
                raise ValidationError({"pool": "Invalid pool."})
        return Response(DisplaySerializer(qs, many=True).data)


class DisplayClaimView(APIView):
    permission_classes = [IsDeskAdminOrAppAdmin]

    def post(self, request):
        room = _target_room(request.user, request.data.get("room"))
        code = _normalise(request.data.get("code"))
        name = str(request.data.get("name") or "").strip()[:100]
        now = timezone.now()
        with transaction.atomic():
            displays._lock()
            display = (
                displays._pending(now).select_for_update().filter(pairing_code=code).first()
                if code else None
            )
            if display is None:
                return Response({"detail": "Unknown or expired code.", "code": "unknown_code"},
                                status=404)
            display.room = room
            display.name = name or display.name
            display.paired_at = now
            display.pairing_code = ""
            display.pairing_expires_at = None
            display.ui_state = {}
            display.last_etag = ""
            display.save()
        return Response(DisplaySerializer(display).data)


class DisplayDetailView(APIView):
    permission_classes = [IsDeskAdminOrAppAdmin]

    def _get(self, request, pk, *, lock=False):
        qs = _visible(request.user)
        if lock:
            qs = qs.select_for_update(of=("self",))
        display = qs.filter(pk=pk).first()
        if display is None:
            raise NotFound()
        return display

    def patch(self, request, pk):
        with transaction.atomic():
            display = self._get(request, pk, lock=True)
            if "name" in request.data:
                display.name = str(request.data.get("name") or "").strip()[:100]
            if "room" in request.data:
                room = _target_room(request.user, request.data.get("room"))
                if room.pk != display.room_id:
                    display.room = room
                    display.ui_state = {}
                    display.last_etag = ""
            display.save()
        return Response(DisplaySerializer(display).data)

    def delete(self, request, pk):
        self._get(request, pk).delete()
        return Response(status=204)


class DisplayPreviewView(APIView):
    permission_classes = [IsDeskAdminOrAppAdmin]

    def get(self, request, pk):
        display = _visible(request.user).filter(pk=pk).first()
        if display is None:
            raise NotFound()
        screen = door_session.current_screen(display, timezone.now())
        return _png(door_render.render(screen, display.panel))


class RoomDoorPreviewView(APIView):
    permission_classes = [IsDeskAdminOrAppAdmin]

    def get(self, request, pk):
        room = get_object_or_404(Room, pk=pk)
        if not rights.can_admin_room(request.user, room):
            raise PermissionDenied()
        panel = request.query_params.get("panel", "5.79")
        if panel not in displays.PANELS:
            raise ValidationError({"panel": "Invalid panel."})
        view = build_door_view(room, panel=panel, now=timezone.now())
        screen = door_session.Screen(
            view=view, mode="normal", selected=None, hours=1, confirm_text=None,
            message=None, session_timeout=0,
        )
        return _png(door_render.render(screen, panel))
