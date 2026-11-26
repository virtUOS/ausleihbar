# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Management of door displays: pair, rename, move, revoke, preview."""
import io

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin
from catalog.models import Resource

from . import displays, door_render, door_session, rights
from .door_view import build_door_view
from .models import Display, Room
from .serializers import DisplaySerializer
from .views import IsDeskAdminOrAppAdmin  # room preview only


def _png(image) -> HttpResponse:
    buf = io.BytesIO()
    image.convert("L").save(buf, "PNG")
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    return response


def _visible(user):
    """All paired displays (room or item); management is for app admins."""
    return (
        Display.objects.filter(Q(room__isnull=False) | Q(resource__isnull=False))
        .select_related("room__floor__building", "resource__product", "resource__resource_pool")
    )


def _given(data, key) -> bool:
    return data.get(key) not in (None, "")


def _target_resource(value) -> Resource:
    try:
        pk = int(value)
    except (TypeError, ValueError):
        raise ValidationError({"resource": "An item is required."})
    resource = (
        Resource.objects.select_related("product", "resource_pool").filter(pk=pk).first()
    )
    if resource is None:
        raise ValidationError({"resource": "Unknown item."})
    if resource.status == Resource.Status.RETIRED:
        raise ValidationError({"resource": "This item is retired."})
    if not resource.product.is_self_service:
        raise ValidationError(
            {"resource": "Only on-site items without hand-out can have a display."}
        )
    return resource


def _resolve_target(user, data):
    """The ``(room, resource)`` pair requested; exactly one is set."""
    has_room, has_resource = _given(data, "room"), _given(data, "resource")
    if has_room == has_resource:
        raise ValidationError({"target": "Give exactly one of room or resource."})
    if has_room:
        return _target_room(user, data.get("room")), None
    return None, _target_resource(data.get("resource"))


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
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = _visible(request.user).order_by("name", "pk")
        pool = request.query_params.get("pool")
        if pool:
            try:
                pool = int(pool)
                qs = qs.filter(Q(room__pool_id=pool) | Q(resource__resource_pool_id=pool))
            except ValueError:
                raise ValidationError({"pool": "Invalid pool."})
        return Response(DisplaySerializer(qs, many=True).data)


class DisplayResourceSearchView(APIView):
    """Items a sign can be paired with: on-site, no hand-out, not retired."""

    permission_classes = [IsAdmin]

    def get(self, request):
        qs = (
            Resource.objects.filter(
                product__use_type="onsite", product__requires_handout=False
            )
            .exclude(status=Resource.Status.RETIRED)
            .select_related("product", "resource_pool")
        )
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(product__title__icontains=search) | Q(inventory_number__icontains=search)
            )
        qs = qs.order_by("product__title", "inventory_number")[:50]
        return Response([
            {
                "id": r.pk, "inventory_number": r.inventory_number,
                "product_title": r.product.title, "pool_name": r.resource_pool.name,
            }
            for r in qs
        ])


class DisplayClaimView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        room, resource = _resolve_target(request.user, request.data)
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
            display.resource = resource
            display.name = name or display.name
            display.paired_at = now
            display.pairing_code = ""
            display.pairing_expires_at = None
            display.ui_state = {}
            display.last_etag = ""
            display.save()
        return Response(DisplaySerializer(display).data)


class DisplayDetailView(APIView):
    permission_classes = [IsAdmin]

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
            if "room" in request.data or "resource" in request.data:
                room, resource = _resolve_target(request.user, request.data)
                new = (room.pk if room else None, resource.pk if resource else None)
                if new != (display.room_id, display.resource_id):
                    display.room, display.resource = room, resource
                    display.ui_state = {}
                    display.last_etag = ""
            display.save()
        return Response(DisplaySerializer(display).data)

    def delete(self, request, pk):
        self._get(request, pk).delete()
        return Response(status=204)


class DisplayPreviewView(APIView):
    permission_classes = [IsAdmin]

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
