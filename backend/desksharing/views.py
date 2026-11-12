# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import roles
from catalog import rich_images
from catalog.models import ResourcePool

from . import booking, hours, notify, rights
from .models import DeskSettings, Feature, Floor, Place, Reservation, Room, new_qr_token
from .serializers import (
    BookRequestSerializer,
    DeskSettingsSerializer,
    FeatureSerializer,
    FloorPlanSerializer,
    FloorSerializer,
    FreePlaceSerializer,
    FreeQuerySerializer,
    ManageReservationSerializer,
    PlaceSerializer,
    ReservationSerializer,
    RoomSerializer,
    place_brief,
)

IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class IsDeskAdmin(permissions.BasePermission):
    """Administrator of at least one desksharing department."""

    message = "Only department admins may access this."

    def has_permission(self, request, view):
        return bool(rights.admin_pool_ids(request.user))


class AdminScopedViewSet(viewsets.ModelViewSet):
    """Rows of the requesting user's admin pools only (others are 404)."""

    permission_classes = [IsDeskAdmin]
    pool_lookup = "pool_id"

    def get_queryset(self):
        pools = rights.admin_pool_ids(self.request.user)
        return self.queryset.filter(**{f"{self.pool_lookup}__in": pools})

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "Places here have reservations; delete the places first."},
                status=status.HTTP_409_CONFLICT,
            )


class FeatureViewSet(AdminScopedViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer


class FloorViewSet(AdminScopedViewSet):
    queryset = Floor.objects.defer("template_data")
    serializer_class = FloorSerializer

    @action(detail=True, methods=["put"], url_path="plan")
    def plan(self, request, pk=None):
        floor = self.get_object()
        ser = FloorPlanSerializer(floor, data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="template",
        parser_classes=[MultiPartParser, FormParser],
    )
    def template(self, request, pk=None):
        floor = self.get_object()
        if request.method == "GET":
            floor = Floor.objects.get(pk=floor.pk)
            if not floor.template_data:
                raise Http404
            resp = HttpResponse(
                bytes(floor.template_data), content_type=floor.template_content_type
            )
            resp["Cache-Control"] = "private, no-store"
            resp["X-Content-Type-Options"] = "nosniff"
            return resp
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file uploaded."}, status=400)
        if upload.size > rich_images.RICH_IMAGE_MAX_BYTES:
            return Response({"detail": "Image is too large (max 5 MB)."}, status=400)
        try:
            data, ext = rich_images.process_rich_image(upload.read())
        except ValueError:
            return Response({"detail": "Uploaded file must be an image."}, status=400)
        floor.template_data = data
        floor.template_content_type = IMAGE_CONTENT_TYPES.get(
            ext, "application/octet-stream"
        )
        floor.save(update_fields=["template_data", "template_content_type", "updated_at"])
        return Response(self.get_serializer(floor).data, status=201)


class RoomViewSet(AdminScopedViewSet):
    queryset = Room.objects.select_related("floor")
    serializer_class = RoomSerializer
    pool_lookup = "floor__pool_id"


class PlaceViewSet(AdminScopedViewSet):
    queryset = Place.objects.select_related("room__floor").prefetch_related(
        "features", "access_groups"
    )
    serializer_class = PlaceSerializer
    pool_lookup = "room__floor__pool_id"

    def perform_destroy(self, instance):
        # Soft delete keeps the history of places that were ever reserved;
        # reservations not yet over are cancelled and their holders told.
        if instance.has_reservations():
            now = timezone.now()
            pending = list(
                instance.reservations.filter(
                    status=Reservation.Status.ACTIVE, period__endswith__gt=now
                ).select_related("holder")
            )
            for res in pending:
                res.status = Reservation.Status.CANCELLED
                res.released_at = now
                res.release_reason = Reservation.ReleaseReason.ADMIN
                res.save(update_fields=["status", "released_at", "release_reason"])
                if res.holder_id:
                    notify.notify(
                        res.holder,
                        notify.ADMIN_CHANGED,
                        {"reservation": res, "action": "cancel", "reason": "place_removed"},
                    )
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        else:
            instance.delete()

    @action(detail=True, methods=["post"], url_path="regenerate-qr")
    def regenerate_qr(self, request, pk=None):
        place = self.get_object()
        place.qr_token = new_qr_token()
        place.save(update_fields=["qr_token", "updated_at"])
        return Response(self.get_serializer(place).data)


class DeskSettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _settings(self, request, pool_id):
        # App admins may switch desksharing on for any active pool; lenders
        # only for the pools they manage.
        if roles.is_app_admin(request.user):
            pool = get_object_or_404(ResourcePool, pk=pool_id, is_active=True)
        elif pool_id in rights.admin_pool_ids(request.user):
            pool = get_object_or_404(ResourcePool, pk=pool_id)
        else:
            raise Http404
        return DeskSettings.for_pool(pool)

    def get(self, request, pool_id):
        obj = self._settings(request, pool_id)
        return Response(DeskSettingsSerializer(obj).data)

    def put(self, request, pool_id):
        obj = self._settings(request, pool_id)
        ser = DeskSettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        # enabled / assistant_group change the memoised desksharing rights.
        roles.invalidate_cache()
        return Response(ser.data)


def booking_error_response(exc: booking.BookingError) -> Response:
    code = status.HTTP_400_BAD_REQUEST if exc.code == "reason_required" else status.HTTP_409_CONFLICT
    return Response(
        {
            "code": exc.code,
            "detail": exc.detail,
            "alternatives": [place_brief(p) for p in exc.alternatives],
        },
        status=code,
    )


def _places_qs():
    return Place.objects.select_related("room__floor__pool")


class ReservationViewSet(viewsets.GenericViewSet):
    """Booking, own reservations, cancel and move."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        user = self.request.user
        return Reservation.objects.filter(
            Q(holder=user)
            | Q(booked_by=user)
            | Q(place__room__floor__pool_id__in=rights.admin_pool_ids(user))
        ).select_related("place__room__floor__pool", "holder")

    def create(self, request):
        ser = BookRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        places = list(_places_qs().filter(pk__in=data["place_ids"]))
        if len(places) != len(set(data["place_ids"])):
            raise serializers.ValidationError({"place_ids": "Unknown place."})
        holder = request.user
        holder_id = data.get("holder_id")
        if holder_id and holder_id != request.user.pk:
            if not rights.assistant_pool_ids(request.user):
                return booking_error_response(
                    booking.BookingError("not_allowed", detail="You may not book for others.")
                )
            holder = get_object_or_404(get_user_model(), pk=holder_id, is_active=True)
        kwargs = dict(
            actor=request.user, holder=holder, places=places, day=data["day"],
            start_hour=data["start_hour"], end_hour=data["end_hour"],
            comment=data.get("comment", ""),
        )
        try:
            last_day = data.get("last_day")
            if last_day and last_day != data["day"]:
                rows = booking.book_range(last_day=last_day, **kwargs)
            else:
                rows = booking.book(**kwargs)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(ReservationSerializer(rows, many=True).data, status=201)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        rows = (
            Reservation.objects.filter(
                holder=request.user,
                status=Reservation.Status.ACTIVE,
                period__endswith__gt=timezone.now(),
            )
            .select_related("place__room__floor")
            .order_by("period", "place_id")
        )
        return Response(ReservationSerializer(rows, many=True).data)

    def destroy(self, request, pk=None):
        reservation = self.get_object()
        reason = request.data.get("reason", "") if hasattr(request, "data") else ""
        reason = reason or request.query_params.get("reason", "")
        try:
            booking.cancel(reservation, actor=request.user, reason=str(reason)[:500])
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        reservation = self.get_object()
        place_id = request.data.get("place_id")
        if not isinstance(place_id, int) or isinstance(place_id, bool):
            raise serializers.ValidationError({"place_id": "A place id is required."})
        to_place = get_object_or_404(_places_qs(), pk=place_id)
        try:
            booking.move(reservation, actor=request.user, to_place=to_place)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(ReservationSerializer(reservation).data)


class FreePlacesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        ser = FreeQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data["pool"] not in rights.member_pool_ids(request.user):
            return Response([])
        pool = get_object_or_404(ResourcePool, pk=data["pool"])
        places = booking.free_places(
            pool, data["kind"], data["day"], data["start_hour"], data["end_hour"],
            for_user=request.user, features=data.get("features") or [],
        )
        return Response(FreePlaceSerializer(places, many=True).data)


class ManageReservationsView(APIView):
    """A department's reservations of one day (department admins)."""

    permission_classes = [IsDeskAdmin]

    def get(self, request):
        try:
            pool_id = int(request.query_params.get("pool", ""))
            day = serializers.DateField().to_internal_value(request.query_params.get("day", ""))
        except (ValueError, serializers.ValidationError):
            return Response({"detail": "pool and day are required."}, status=400)
        if pool_id not in rights.admin_pool_ids(request.user):
            raise Http404
        start = hours.local_dt(day, 0)
        end = hours.local_dt(day + timedelta(days=1), 0)
        rows = (
            Reservation.objects.filter(
                place__room__floor__pool_id=pool_id,
                period__overlap=(start, end),
            )
            .select_related("place__room__floor", "holder")
            .order_by("period", "place_id")
        )
        return Response(ManageReservationSerializer(rows, many=True).data)
