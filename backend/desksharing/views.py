# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef, ProtectedError, Q, Value
from django.db.models.functions import Concat
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import roles
from accounts.models import AccessGroup
from catalog import rich_images
from catalog.models import ResourcePool

from . import (
    absences, actions, booking, checkin, cycles, favorites, hours, notify, overview, privacy,
    requests as requests_svc, rights, series as series_svc, stats as stats_svc,
)
from . import qr as qr_svc
from .models import (
    Absence, Building, DeskSettings, Feature, Floor, FloorTemplate, Place, ReleaseRequest, Reservation,
    Room, Series, SwapRequest, new_qr_token,
)
from .serializers import (
    AbsenceSerializer,
    BuildingSerializer,
    ManageAbsenceSerializer,
    SeriesRequestSerializer,
    SeriesSerializer,
    series_result_data,
    BookDaysSerializer,
    BookRequestSerializer,
    DeskSettingsSerializer,
    FeatureSerializer,
    FloorPlanSerializer,
    FloorSerializer,
    FreePlaceSerializer,
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


class IsDeskAdminOrAppAdmin(IsDeskAdmin):
    """Department admin, or app admin even before any department is enabled
    (the campus building list can be prepared up front)."""

    def has_permission(self, request, view):
        return roles.is_app_admin(request.user) or super().has_permission(request, view)


class AdminScopedViewSet(viewsets.ModelViewSet):
    """Rows of the requesting user's admin pools only (others are 404)."""

    permission_classes = [IsDeskAdmin]
    pool_lookup = "pool_id"

    # Lookups that must be active for a row to be listed (soft delete).
    active_lookups: tuple[str, ...] = ()

    def get_queryset(self):
        pools = rights.admin_pool_ids(self.request.user)
        qs = self.queryset.filter(**{f"{self.pool_lookup}__in": pools})
        if self.action == "list" and self.request.query_params.get("include_inactive") != "1":
            qs = qs.filter(**{lookup: True for lookup in self.active_lookups})
        return qs


class SoftDeleteContainerMixin:
    """Rooms and floors: hard delete without reservation history, otherwise
    deactivate the container and retire its places."""

    places_lookup = ""

    def perform_update(self, serializer):
        # Deactivating through the API retires the places like a soft delete
        # (future reservations cancelled, holders told); reactivating only
        # flips the flag (retired places stay retired until edited).
        was_active = serializer.instance.is_active
        with transaction.atomic():
            instance = serializer.save()
            if was_active and not instance.is_active:
                booking.retire_places(list(Place.objects.filter(**{self.places_lookup: instance})))

    def perform_destroy(self, instance):
        places = list(Place.objects.filter(**{self.places_lookup: instance}))
        if Reservation.objects.filter(place__in=places).exists():
            booking.retire_places(places)
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        else:
            instance.delete()


class BuildingViewSet(viewsets.ModelViewSet):
    """The campus-wide building list. Department admins read it and may add
    a missing building; changing or deleting one is for app admins. A
    building still holding floors is not deleted (409)."""

    permission_classes = [IsDeskAdminOrAppAdmin]
    serializer_class = BuildingSerializer
    queryset = Building.objects.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["may_edit"] = roles.is_app_admin(self.request.user)
        return ctx

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS and not roles.is_app_admin(request.user):
            raise PermissionDenied("Only app admins may change buildings.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            # PROTECT also covers a floor assigned between check and delete.
            instance.delete()
        except ProtectedError:
            return Response(
                {"detail": "This building still has floors."}, status=status.HTTP_409_CONFLICT
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class FeatureViewSet(viewsets.ModelViewSet):
    """Campus-wide equipment (rights are reworked with the admin workspace)."""

    permission_classes = [IsDeskAdmin]
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer


class FloorViewSet(SoftDeleteContainerMixin, AdminScopedViewSet):
    # ``has_template`` without touching the blob table's data column.
    queryset = Floor.objects.annotate(
        template_exists=Exists(FloorTemplate.objects.filter(floor=OuterRef("pk")))
    )
    serializer_class = FloorSerializer
    active_lookups = ("is_active",)
    places_lookup = "room__floor"

    def get_queryset(self):
        # Floors are campus-wide: a department admin sees the floors holding
        # rooms or places of their departments, app admins all of them.
        qs = self.queryset
        if not roles.is_app_admin(self.request.user):
            pools = rights.admin_pool_ids(self.request.user)
            qs = qs.filter(
                Exists(Room.objects.filter(floor=OuterRef("pk"), pool_id__in=pools))
                | Exists(Place.objects.filter(room__floor=OuterRef("pk"), pool_id__in=pools))
            )
        if self.action == "list" and self.request.query_params.get("include_inactive") != "1":
            qs = qs.filter(is_active=True)
        return qs

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
            template = FloorTemplate.objects.filter(floor=floor).first()
            if template is None:
                raise Http404
            resp = HttpResponse(bytes(template.data), content_type=template.content_type)
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
        FloorTemplate.objects.update_or_create(
            floor=floor,
            defaults={
                "data": data,
                "content_type": IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream"),
            },
        )
        floor.template_exists = True
        floor.save(update_fields=["updated_at"])
        return Response(self.get_serializer(floor).data, status=201)


class RoomViewSet(SoftDeleteContainerMixin, AdminScopedViewSet):
    queryset = Room.objects.select_related("floor")
    serializer_class = RoomSerializer
    pool_lookup = "pool_id"
    active_lookups = ("is_active", "floor__is_active")
    places_lookup = "room"


class PlaceViewSet(AdminScopedViewSet):
    queryset = Place.objects.select_related("room__floor__building", "fixed_owner").prefetch_related(
        "features", "access_groups"
    )
    serializer_class = PlaceSerializer
    pool_lookup = "pool_id"
    active_lookups = ("is_active", "room__is_active", "room__floor__is_active")

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        with transaction.atomic():
            instance = serializer.save()
            if was_active and not instance.is_active:
                booking.retire_places([instance])

    def perform_destroy(self, instance):
        # Soft delete keeps the history of places that were ever reserved;
        # reservations not yet over are cancelled and their holders told.
        if instance.has_reservations():
            booking.retire_places([instance])
        else:
            instance.delete()

    @action(detail=True, methods=["post"], url_path="regenerate-qr")
    def regenerate_qr(self, request, pk=None):
        place = self.get_object()
        place.qr_token = new_qr_token()
        place.save(update_fields=["qr_token", "updated_at"])
        return Response(self.get_serializer(place).data)

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        """The place's QR sticker as a PNG (printable label)."""
        place = self.get_object()
        resp = HttpResponse(qr_svc.place_qr_png(place), content_type="image/png")
        resp["Cache-Control"] = "private, no-store"
        return resp


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
            **exc.extra,
        },
        status=code,
    )


def _places_qs():
    return Place.objects.select_related("pool", "room__floor__building")


class ReservationViewSet(viewsets.GenericViewSet):
    """Booking, own reservations, cancel and move."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        user = self.request.user
        return Reservation.objects.filter(
            Q(holder=user)
            | Q(booked_by=user)
            | Q(place__pool_id__in=rights.admin_pool_ids(user))
        ).select_related("place__pool", "place__room__floor__building", "holder")

    def create(self, request):
        ser = BookRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        places = list(_places_qs().filter(pk__in=data["place_ids"]))
        if len(places) != len(set(data["place_ids"])):
            raise serializers.ValidationError({"place_ids": "Unknown place."})
        holder = self._holder(request, data)
        if isinstance(holder, Response):
            return holder
        kwargs = dict(
            actor=request.user, holder=holder, places=places, day=data["day"],
            start_hour=data["start_hour"], end_hour=data["end_hour"],
            comment=data.get("comment", ""),
        )
        limit_warnings: list[str] = []
        try:
            last_day = data.get("last_day")
            if last_day and last_day != data["day"]:
                rows = booking.book_range(last_day=last_day, warnings=limit_warnings, **kwargs)
            else:
                rows = booking.book(warnings=limit_warnings, **kwargs)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(
            {
                "reservations": ReservationSerializer(rows, many=True, context={"viewer": request.user}).data,
                "warnings": absences.warnings_for(holder, rows) + limit_warnings,
            },
            status=201,
        )

    def _holder(self, request, data):
        """The person booked for (an error response when not allowed)."""
        holder_id = data.get("holder_id")
        if not holder_id or holder_id == request.user.pk:
            return request.user
        if not rights.assistant_pool_ids(request.user):
            return booking_error_response(
                booking.BookingError("not_allowed", detail="You may not book for others.")
            )
        return get_object_or_404(get_user_model(), pk=holder_id, is_active=True)

    @action(detail=False, methods=["post"])
    def days(self, request):
        """Book several days x places in one call."""
        ser = BookDaysSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        places = list(_places_qs().filter(pk__in=data["place_ids"]))
        if len(places) != len(set(data["place_ids"])):
            raise serializers.ValidationError({"place_ids": "Unknown place."})
        holder = self._holder(request, data)
        if isinstance(holder, Response):
            return holder
        limit_warnings: list[str] = []
        try:
            rows, requests = booking.book_days(
                actor=request.user, holder=holder, places=places, days=data["days"],
                start_hour=data["start_hour"], end_hour=data["end_hour"],
                comment=data.get("comment", ""), on_taken=data["on_taken"],
                show_name=data["show_name"], warnings=limit_warnings,
            )
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(
            {
                "reservations": ReservationSerializer(rows, many=True, context={"viewer": request.user}).data,
                "requests": [requests_svc.serialize_release(r, request.user, perspective="requester") for r in requests],
                "warnings": absences.warnings_for(holder, rows) + limit_warnings,
            },
            status=201,
        )

    @action(detail=False, methods=["get"])
    def mine(self, request):
        rows = (
            Reservation.objects.filter(
                holder=request.user,
                status=Reservation.Status.ACTIVE,
                period__endswith__gt=timezone.now(),
            )
            .select_related("place__room__floor__building")
            .order_by("period", "place_id")
        )
        rows = list(rows)
        context = {
            "viewer": request.user,
            "neighbours": overview.room_neighbours_bulk(rows, viewer=request.user),
        }
        return Response(ReservationSerializer(rows, many=True, context=context).data)

    def destroy(self, request, pk=None):
        reservation = self.get_object()
        if not isinstance(request.data, dict):
            raise serializers.ValidationError({"detail": "The body must be an object."})
        reason = request.data.get("reason", "") or request.query_params.get("reason", "")
        try:
            booking.cancel(reservation, actor=request.user, reason=str(reason)[:500])
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        reservation = self.get_object()
        try:
            checkin.check_in(reservation, user=request.user)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        reservation.refresh_from_db()
        return Response(ReservationSerializer(reservation, context={"viewer": request.user}).data)

    @action(detail=True, methods=["post"])
    def later(self, request, pk=None):
        reservation = self.get_object()
        until = serializers.DateTimeField().to_internal_value(
            request.data.get("until") if isinstance(request.data, dict) else None
        )
        try:
            checkin.come_later(reservation, user=request.user, until=until)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(ReservationSerializer(reservation, context={"viewer": request.user}).data)

    @action(detail=True, methods=["get"], url_path="move-targets")
    def move_targets(self, request, pk=None):
        """Free places of the same kind for the same hours that the holder
        may book (also for a hidden holder, whose id never leaves the API)."""
        reservation = self.get_object()
        try:
            booking._check_changeable(reservation, request.user)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        places = booking.move_targets(reservation, actor=request.user)
        return Response(FreePlaceSerializer(places, many=True).data)

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
        return Response(ReservationSerializer(reservation, context={"viewer": request.user}).data)


def scan_response(result: checkin.ScanResult, *, viewer) -> Response:
    return Response(
        {
            "action": result.action,
            "reservation": ReservationSerializer(result.reservation, context={"viewer": viewer}).data
            if result.reservation
            else None,
            "next_free_until": result.next_free_until,
            "reason": result.reason,
        }
    )


class ScanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get("token") if isinstance(request.data, dict) else None
        if not isinstance(token, str) or not token:
            raise serializers.ValidationError({"token": "A token is required."})
        return scan_response(checkin.scan(token, user=request.user), viewer=request.user)


class PlaceCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        place = get_object_or_404(_places_qs(), pk=pk)
        return scan_response(checkin.check_in_place(place, user=request.user), viewer=request.user)


class SeriesViewSet(viewsets.GenericViewSet):
    """Weekly series: create, own list, extend, resolve a conflict, delete."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SeriesSerializer

    def get_queryset(self):
        user = self.request.user
        return Series.objects.filter(
            Q(holder=user)
            | Q(booked_by=user)
            | Q(place__pool_id__in=rights.admin_pool_ids(user))
        ).select_related("place__pool", "place__room__floor__building", "holder")

    def create(self, request):
        ser = SeriesRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        place = get_object_or_404(_places_qs(), pk=data["place_id"])
        holder = request.user
        holder_id = data.get("holder_id")
        if holder_id and holder_id != request.user.pk:
            if not rights.assistant_pool_ids(request.user):
                return booking_error_response(
                    booking.BookingError("not_allowed", detail="You may not book for others.")
                )
            holder = get_object_or_404(get_user_model(), pk=holder_id, is_active=True)
        limit_warnings: list[str] = []
        try:
            result = series_svc.create_series(
                actor=request.user, holder=holder, place=place,
                weekdays=data["weekdays"], start_hour=data["start_hour"],
                end_hour=data["end_hour"], valid_from=data["valid_from"],
                valid_until=data["valid_until"], comment=data.get("comment", ""),
                on_taken=data["on_taken"], show_name=data["show_name"],
                warnings=limit_warnings,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        except booking.BookingError as exc:
            return booking_error_response(exc)
        data = series_result_data(result, viewer=request.user)
        data["warnings"] = absences.warnings_for(holder, result.created) + limit_warnings
        return Response(data, status=201)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        rows = (
            Series.objects.filter(holder=request.user, cancelled_at__isnull=True)
            .select_related("place__room__floor__building")
            .order_by("valid_from", "pk")
        )
        return Response(SeriesSerializer(rows, many=True, context={"viewer": request.user}).data)

    def destroy(self, request, pk=None):
        series = self.get_object()
        if not isinstance(request.data, dict):
            raise serializers.ValidationError({"detail": "The body must be an object."})
        reason = request.data.get("reason", "") or request.query_params.get("reason", "")
        try:
            series_svc.delete_series(series, actor=request.user, reason=str(reason)[:500])
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        series = self.get_object()
        limit_warnings: list[str] = []
        try:
            result = series_svc.extend_series(series, actor=request.user, warnings=limit_warnings)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        data = series_result_data(result, viewer=request.user)
        data["warnings"] = limit_warnings
        return Response(data)

    @action(detail=True, methods=["get"])
    def conflicts(self, request, pk=None):
        """Dates of the series still without an occurrence, with alternatives."""
        series = self.get_object()
        return Response(
            [
                {
                    "day": c.day.isoformat(),
                    "code": c.code,
                    "alternatives": [place_brief(p) for p in c.alternatives],
                }
                for c in series_svc.open_conflicts(series)
            ]
        )

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        series = self.get_object()
        try:
            day = serializers.DateField().to_internal_value(request.data.get("day"))
        except serializers.ValidationError:
            raise serializers.ValidationError({"day": "A date is required."})
        place_id = request.data.get("place_id")
        if not isinstance(place_id, int) or isinstance(place_id, bool):
            raise serializers.ValidationError({"place_id": "A place id is required."})
        place = get_object_or_404(_places_qs(), pk=place_id)
        try:
            series_svc._manager_check(series, request.user)
            reservation = series_svc.resolve_conflict(series, day, place, actor=request.user)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(ReservationSerializer(reservation, context={"viewer": request.user}).data, status=201)


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
                place__pool_id=pool_id,
                period__overlap=(start, end),
            )
            .select_related("place__room__floor__building", "holder")
            .order_by("period", "place_id")
        )
        return Response(ManageReservationSerializer(rows, many=True, context={"viewer": request.user}).data)


def _absence_today():
    return timezone.localtime(timezone.now(), hours.TZ).date()


class AbsencesView(APIView):
    """Own absences: list (current and future), create, delete."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = Absence.objects.filter(
            user=request.user, end_date__gte=_absence_today()
        ).select_related("user")
        return Response(AbsenceSerializer(rows, many=True).data)

    def post(self, request):
        ser = AbsenceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            absence = absences.add_absence(
                actor=request.user, user=request.user, **ser.validated_data
            )
        except booking.BookingError as exc:
            return booking_error_response(exc)
        data = AbsenceSerializer(absence).data
        data["released_count"] = absence.released_count
        return Response(data, status=201)

    def delete(self, request, pk):
        absence = get_object_or_404(
            Absence, pk=pk, user=request.user, end_date__gte=_absence_today()
        )
        return Response({"kept_bookings": absences.delete_absence(absence)})


class IsDeskAssistant(permissions.BasePermission):
    """Assistant or administrator of at least one desksharing department."""

    message = "Only department admins and assistants may access this."

    def has_permission(self, request, view):
        return bool(rights.assistant_pool_ids(request.user))


class ManageAbsencesView(APIView):
    """Absences of members of the requester's departments (assistants)."""

    permission_classes = [IsDeskAssistant]

    def _visible(self, request, absence) -> bool:
        return bool(
            rights.assistant_pool_ids(request.user) & rights.member_pool_ids(absence.user)
        )

    def get(self, request):
        rows = Absence.objects.select_related("user")
        if request.query_params.get("include_past") != "1":
            rows = rows.filter(end_date__gte=_absence_today())
        pool = request.query_params.get("pool")
        if pool:
            # One department: its members' absences (assistants of it only).
            try:
                pool_id = int(pool)
            except ValueError:
                raise serializers.ValidationError({"pool": "A department id is required."})
            if pool_id not in rights.assistant_pool_ids(request.user):
                raise Http404
            rows = rows.filter(user_id__in=rights.member_user_ids(pool_id))
            visible = list(rows)
        else:
            visible = [a for a in rows if self._visible(request, a)]
        return Response(ManageAbsenceSerializer(visible, many=True).data)

    def post(self, request):
        ser = ManageAbsenceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            absence = absences.add_absence(actor=request.user, **ser.validated_data)
        except booking.BookingError as exc:
            if exc.code == "not_allowed":
                return Response({"detail": exc.detail}, status=403)
            return booking_error_response(exc)
        return Response(ManageAbsenceSerializer(absence).data, status=201)

    def delete(self, request, pk):
        absence = get_object_or_404(Absence.objects.select_related("user"), pk=pk)
        if not self._visible(request, absence):
            raise Http404
        return Response({"kept_bookings": absences.delete_absence(absence)})


def _int_field(data, name) -> int:
    value = data.get(name) if isinstance(data, dict) else None
    if not isinstance(value, int) or isinstance(value, bool):
        raise serializers.ValidationError({name: "An id is required."})
    return value


def _uuid_field(data, name) -> uuid.UUID:
    value = data.get(name) if isinstance(data, dict) else None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise serializers.ValidationError({name: "An id is required."}) from None


def _accept_flag(data) -> bool:
    value = data.get("accept") if isinstance(data, dict) else None
    if not isinstance(value, bool):
        raise serializers.ValidationError({"accept": "true or false is required."})
    return value


def _reservations_qs():
    return Reservation.objects.select_related("place__pool", "place__room__floor__building", "holder")


class SwapRequestViewSet(viewsets.GenericViewSet):
    """Ask another holder to exchange places; answered by that holder."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return SwapRequest.objects.filter(
            Q(from_reservation__holder=user) | Q(to_reservation__holder=user)
        )

    def create(self, request):
        mine = get_object_or_404(_reservations_qs(), pk=_int_field(request.data, "mine_id"))
        theirs = get_object_or_404(_reservations_qs(), pk=_int_field(request.data, "theirs_id"))
        try:
            req = requests_svc.request_swap(user=request.user, mine=mine, theirs=theirs)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(requests_svc.serialize_swap(req, request.user), status=201)

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        req = self.get_object()
        accept = _accept_flag(request.data)
        try:
            req = requests_svc.answer_swap(req, user=request.user, accept=accept)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response({"id": req.pk, "status": req.status})


class ReleaseRequestViewSet(viewsets.GenericViewSet):
    """Ask a holder to hand over a reservation; answer (one or a batch) and
    withdraw requests."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return ReleaseRequest.objects.filter(Q(requester=user) | Q(reservation__holder=user))

    def create(self, request):
        reservation = get_object_or_404(
            _reservations_qs(), pk=_int_field(request.data, "reservation_id")
        )
        show_name = request.data.get("show_name", False)
        if not isinstance(show_name, bool):
            raise serializers.ValidationError({"show_name": "true or false is required."})
        try:
            req = requests_svc.request_release(
                user=request.user, reservation=reservation, show_name=show_name
            )
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(requests_svc.serialize_release(req, request.user), status=201)

    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        req = self.get_object()
        accept = _accept_flag(request.data)
        try:
            req = requests_svc.answer_release(req, user=request.user, accept=accept)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response({"id": req.pk, "status": req.status})

    @action(detail=False, methods=["post"], url_path="answer-batch")
    def answer_batch(self, request):
        batch = _uuid_field(request.data, "batch")
        accept = _accept_flag(request.data)
        return Response(requests_svc.answer_release_batch(batch, user=request.user, accept=accept))

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        req = get_object_or_404(ReleaseRequest.objects.filter(requester=request.user), pk=pk)
        try:
            req = requests_svc.withdraw_release(req, user=request.user)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response({"id": req.pk, "status": req.status})

    @action(detail=False, methods=["post"], url_path="withdraw-batch")
    def withdraw_batch(self, request):
        batch = _uuid_field(request.data, "batch")
        return Response({"withdrawn": requests_svc.withdraw_batch(batch, user=request.user)})


class MyRequestsView(APIView):
    """Open incoming and outgoing swap and release requests."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(requests_svc.requests_for(request.user))


def _member_pool(request) -> ResourcePool:
    """The ``pool`` query parameter; 404 unless the user is a member."""
    try:
        pool_id = int(request.query_params.get("pool", ""))
    except ValueError:
        raise serializers.ValidationError({"pool": "A department id is required."})
    if pool_id not in rights.member_pool_ids(request.user):
        raise Http404
    return get_object_or_404(ResourcePool, pk=pool_id)


class OverviewView(APIView):
    """A department's day: plan, place states per hour, meeting rooms
    (members of the department only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pool = _member_pool(request)
        raw_day = request.query_params.get("day")
        if raw_day:
            try:
                day = serializers.DateField().to_internal_value(raw_day)
            except serializers.ValidationError:
                raise serializers.ValidationError({"day": "A date is required."})
        else:
            day = _absence_today()
        # Past days (who sat where) only for department admins.
        if day < _absence_today() and pool.pk not in rights.admin_pool_ids(request.user):
            raise serializers.ValidationError({"day": "Past days are not available."})
        return Response(overview.department_day(pool, day, viewer=request.user))


def _stats_params(request):
    """(pool, start, end) of a statistics request; admin pools only."""
    ser = StatsQuerySerializer(data=request.query_params)
    ser.is_valid(raise_exception=True)
    pool_id, start, end = ser.validated_data["pool"], ser.validated_data["start"], ser.validated_data["end"]
    # The single authoritative check, on the validated value.
    if pool_id not in rights.admin_pool_ids(request.user):
        raise PermissionDenied("Only department admins may access this.")
    return get_object_or_404(ResourcePool, pk=pool_id), start, end


class StatsQuerySerializer(serializers.Serializer):
    pool = serializers.IntegerField()
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs["end"] < attrs["start"]:
            raise serializers.ValidationError({"end": "The end must not precede the start."})
        if (attrs["end"] - attrs["start"]).days > stats_svc.MAX_DAYS:
            raise serializers.ValidationError({"end": "Range too large (max 5 years)."})
        return attrs


class StatsView(APIView):
    """Anonymous usage figures of a department (department admins only)."""

    permission_classes = [IsDeskAdmin]

    def get(self, request):
        pool, start, end = _stats_params(request)
        return Response(stats_svc.department_stats(pool, start, end))


class StatsCsvView(APIView):
    permission_classes = [IsDeskAdmin]

    def get(self, request):
        pool, start, end = _stats_params(request)
        response = HttpResponse(
            stats_svc.stats_csv(pool, start, end), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="desksharing-stats-{start}-{end}.csv"'
        return response


class HoursView(APIView):
    """Business hours of a department on a day (members only): the open
    interval (``null`` = closed) and the grid hours closed by blocks."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pool = _member_pool(request)
        try:
            day = serializers.DateField().to_internal_value(request.query_params.get("day", ""))
        except serializers.ValidationError:
            raise serializers.ValidationError({"day": "A date is required."})
        open_hours = hours.business_hours(pool, day)
        local_now = timezone.localtime(timezone.now(), hours.TZ)
        settings_ = DeskSettings.objects.filter(pool=pool).first()
        business = (settings_.business_hours if settings_ else None) or {}
        return Response(
            {
                "open": list(open_hours) if open_hours else None,
                "closed": sorted(hours.closed_hours(pool, day)) if open_hours else [],
                # First bookable hour (the current one) when ``day`` is today.
                "min_hour": local_now.hour if day == local_now.date() else None,
                # Last bookable day (the department's advance horizon).
                "max_day": cycles.booking_window(pool).advance_until.isoformat(),
                # Weekdays (0 = Monday) without business hours.
                "closed_weekdays": [
                    d for d in range(7) if not business.get(str(d))
                ],
            }
        )


class ClosedDaysView(APIView):
    """Days closed by lending blocks (public holidays, closures) in
    ``from..to`` so calendars can grey them out. With ``pool`` (members
    only): system and department blocks against its business hours; without:
    system-wide blocks only (absences span all departments)."""

    permission_classes = [permissions.IsAuthenticated]
    MAX_DAYS = 400

    def get(self, request):
        pool = _member_pool(request) if request.query_params.get("pool") else None
        field = serializers.DateField()
        try:
            first = field.to_internal_value(request.query_params.get("from", ""))
            last = field.to_internal_value(request.query_params.get("to", ""))
        except serializers.ValidationError:
            raise serializers.ValidationError({"from": "A date range is required."})
        if last < first or (last - first).days > self.MAX_DAYS:
            raise serializers.ValidationError({"to": "Range too large (max 400 days)."})
        return Response(
            {"days": [d.isoformat() for d in hours.blocked_days(pool, first, last)]}
        )


def _holder_param(request, pool_id: int):
    """The person a booking page is computed for: the requester, or — for
    assistants of the pool — the ``holder`` query parameter (a member of the
    pool; 404 otherwise)."""
    raw = request.query_params.get("holder")
    if raw in (None, ""):
        return request.user
    try:
        holder_id = int(raw)
    except ValueError:
        raise serializers.ValidationError({"holder": "A person id is required."})
    if holder_id == request.user.pk:
        return request.user
    if pool_id not in rights.assistant_pool_ids(request.user):
        raise PermissionDenied("You may not book for others.")
    holder = get_object_or_404(get_user_model(), pk=holder_id, is_active=True)
    if pool_id not in rights.member_pool_ids(holder):
        raise Http404
    return holder


def _date_param(request, name: str):
    try:
        return serializers.DateField().to_internal_value(request.query_params.get(name, ""))
    except serializers.ValidationError:
        raise serializers.ValidationError({name: "A date is required."})


class WindowView(APIView):
    """The booking window of a department and how much of the advance quota
    the person has used (members; ``holder`` for assistants)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pool = _member_pool(request)
        holder = _holder_param(request, pool.pk)
        window = cycles.booking_window(pool)
        used = len(cycles.advance_usage(pool, holder, window))
        return Response({
            "today": window.today.isoformat(),
            "open_until": window.open_until.isoformat(),
            "transition_from": window.transition_from.isoformat(),
            "next_open_until": window.next_cycle_end.isoformat(),
            "advance_until": window.advance_until.isoformat(),
            "advance_days": window.advance_days,
            "advance_places": window.advance_places,
            "advance_days_used": used,
            "advance_days_left": max(0, window.advance_days - used),
        })


class PlaceDaysView(APIView):
    """Per day of ``from..to``: whether the department is closed and which
    grid hours of one place are taken by others or fixed for someone else.
    Never names holders or reservations; the ``holder``'s own reservations
    are left out only when the holder asks."""

    permission_classes = [permissions.IsAuthenticated]
    MAX_DAYS = 400

    def get(self, request, pk):
        place = get_object_or_404(
            Place.objects.select_related("pool"), pk=pk, is_active=True,
            room__is_active=True, room__floor__is_active=True,
        )
        pool = place.pool
        if pool.pk not in rights.member_pool_ids(request.user):
            raise Http404
        holder = _holder_param(request, pool.pk)
        first, last = _date_param(request, "from"), _date_param(request, "to")
        if last < first or (last - first).days > self.MAX_DAYS:
            raise serializers.ValidationError({"to": "Range too large (max 400 days)."})
        cfg = DeskSettings.for_pool(pool)
        blocked = set(hours.blocked_days(pool, first, last))
        taken: dict = {}
        rows = Reservation.objects.filter(
            place=place, status=Reservation.Status.ACTIVE,
            period__overlap=(hours.local_dt(first, 0), hours.local_dt(last, 24)),
        )
        if holder.pk == request.user.pk:
            rows = rows.exclude(holder=holder)
        rows = rows.values_list("period", flat=True)
        for period in rows:
            day = max(first, period.lower.astimezone(hours.TZ).date())
            while day <= last and hours.local_dt(day, 0) < period.upper:
                for hour in range(hours.FIRST_HOUR, hours.LAST_HOUR):
                    if period.lower < hours.local_dt(day, hour + 1) and period.upper > hours.local_dt(day, hour):
                        taken.setdefault(day, set()).add(hour)
                day += timedelta(days=1)
        # On someone else's behalf the holder's own fixed place counts as
        # assigned, too (an assistant must not learn which one it is).
        fixed_for_others = bool(
            place.fixed_owner_id
            and (place.fixed_owner_id != holder.pk or holder.pk != request.user.pk)
        )
        absent = set()
        if fixed_for_others:
            absent = absences.absent_days_by_user(
                [place.fixed_owner_id], first, last
            ).get(place.fixed_owner_id, set())
        out = []
        day = first
        while day <= last:
            span = hours.business_hours(pool, day, cfg)
            hours_taken = set(taken.get(day, set()))
            if span and fixed_for_others and day not in absent:
                hours_taken |= set(range(span[0], span[1]))
            out.append({
                "day": day.isoformat(),
                "closed": span is None or day in blocked,
                "taken": sorted(hours_taken),
            })
            day += timedelta(days=1)
        return Response(out)


class AvailabilityView(APIView):
    """Per bookable place of a kind: the days of a list on which it is taken
    (can be requested) or unavailable for the same hours (members)."""

    permission_classes = [permissions.IsAuthenticated]
    MAX_DAYS = 366

    def get(self, request):
        pool = _member_pool(request)
        holder = _holder_param(request, pool.pk)
        kind = request.query_params.get("kind", "")
        if kind not in Place.Kind.values:
            raise serializers.ValidationError({"kind": "A valid place kind is required."})
        try:
            start_hour = int(request.query_params.get("start_hour", ""))
            end_hour = int(request.query_params.get("end_hour", ""))
            features = [int(v) for v in request.query_params.get("features", "").split(",") if v.strip()]
        except ValueError:
            raise serializers.ValidationError({"detail": "Hours and features must be numbers."})
        if not (hours.FIRST_HOUR <= start_hour < end_hour <= hours.LAST_HOUR):
            raise serializers.ValidationError({"start_hour": "Hours must lie within 06-20."})
        field = serializers.DateField()
        try:
            days = [field.to_internal_value(v) for v in request.query_params.get("days", "").split(",") if v.strip()]
        except serializers.ValidationError:
            raise serializers.ValidationError({"days": "Comma-separated dates are required."})
        days = sorted(set(days))
        if not days or len(days) > self.MAX_DAYS:
            raise serializers.ValidationError({"days": "Between 1 and 366 days are required."})
        if pool.pk not in rights.member_pool_ids(holder):
            return Response([])
        return Response(booking.availability(
            pool, kind, days, start_hour, end_hour, holder=holder, features=features,
            viewer=request.user,
        ))


class PoolFeaturesView(APIView):
    """Equipment features of a department for the booking filter (members)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _member_pool(request)
        # Equipment is one campus-wide catalogue.
        rows = Feature.objects.order_by("name", "pk")
        return Response([{"id": f.pk, "name": f.name} for f in rows])


class PoolFloorsView(APIView):
    """Active floors of a department with their building, for the location
    picker on the member pages (no plans), plus the floor of the viewer's
    latest booking as the default."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pool = _member_pool(request)
        rows = overview.pool_floors(pool).select_related("building")
        return Response({
            "floors": [{"id": f.pk, "name": f.name, **overview.floor_location(f)} for f in rows],
            "last_floor_id": overview.last_floor_id(pool, request.user),
        })


class RoomPopularityView(APIView):
    """Rooms of a department ordered by popularity (members; order only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pool = _member_pool(request)
        return Response({"order": overview.room_popularity(pool)})


class FreeNowQuerySerializer(serializers.Serializer):
    pool = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=Place.Kind.choices, required=False)
    features = serializers.CharField(required=False, allow_blank=True)

    def validate_features(self, value):
        try:
            return [int(v) for v in value.split(",") if v.strip()]
        except ValueError:
            raise serializers.ValidationError("Comma-separated feature ids.")


class FreeNowView(APIView):
    """Places free from now on (empty for non-members)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        ser = FreeNowQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data["pool"] not in rights.member_pool_ids(request.user):
            return Response([])
        pool = get_object_or_404(ResourcePool, pk=data["pool"])
        return Response(
            overview.free_now(
                pool, viewer=request.user, kind=data.get("kind"),
                features=data.get("features") or [],
            )
        )


class FavoritesView(APIView):
    """Own favourite places: ``GET`` lists ids, ``PUT``/``DELETE`` on
    ``<place_id>/`` marks or unmarks one (idempotent)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        places = favorites.favorite_places(request.user)
        return Response({
            "place_ids": [p.pk for p in places],
            # For the shop's favourites page (header heart).
            "places": [
                {
                    **place_brief(p), "kind": p.kind, "building": p.room.floor.building_code,
                    "pool": p.pool_id, "pool_name": p.pool.name,
                }
                for p in places
            ],
        })

    def put(self, request, place_id):
        place = get_object_or_404(
            Place.objects.select_related("room__floor__building"), pk=place_id
        )
        if not favorites.add_favorite(request.user, place):
            # Same answer as for an unknown id: no hint about other departments.
            raise Http404
        return Response({"place_id": place.pk, "favorite": True})

    def delete(self, request, place_id):
        favorites.remove_favorite(request.user, place_id)
        return Response({"place_id": place_id, "favorite": False})


class ProfileView(APIView):
    """Own desksharing preferences (``hide_name`` opt-out)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"hide_name": privacy.get_hide_name(request.user)})

    def put(self, request):
        value = request.data.get("hide_name") if isinstance(request.data, dict) else None
        if not isinstance(value, bool):
            raise serializers.ValidationError({"hide_name": "true or false is required."})
        privacy.set_hide_name(request.user, value)
        return Response({"hide_name": value})


class NotificationPreferencesView(APIView):
    """Channel per event (``mail`` or ``off`` until push exists)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(notify.preferences_for(request.user))

    def put(self, request):
        data = request.data
        if not isinstance(data, dict):
            raise serializers.ValidationError({"detail": "The body must be an object."})
        errors = {}
        for event, channel in data.items():
            if event not in notify.EVENTS:
                errors[event] = "Unknown event."
            elif channel not in notify.SELECTABLE_CHANNELS:
                errors[event] = "Choose mail or off."
        if errors:
            raise serializers.ValidationError(errors)
        notify.set_preferences(request.user, data)
        return Response(notify.preferences_for(request.user))


class ActionView(APIView):
    """One-click actions from the grace nudge mail (signed token)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        token, action_name = data.get("token"), data.get("action")
        if not isinstance(token, str) or not isinstance(action_name, str):
            raise serializers.ValidationError({"detail": "token and action are required."})
        until = None
        if data.get("until") is not None:
            until = parse_datetime(str(data["until"]))
            if until is None:
                raise serializers.ValidationError({"until": "Not a date and time."})
            if timezone.is_naive(until):
                until = timezone.make_aware(until, hours.TZ)
        try:
            actions.perform(token, action_name, user=request.user, until=until)
        except actions.ActionError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
        return Response({"action": action_name, "done": True})


class ActionContextView(APIView):
    """Reservation behind a mail action token (read only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        token = request.query_params.get("token", "")
        try:
            data = actions.context(token, user=request.user)
        except actions.ActionError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
        return Response(data)


PEOPLE_MIN_CHARS = 3  # also in the static "Enter at least 3 characters."
PEOPLE_LIMIT = 20


def _admin_or_assistant_pool(request) -> int:
    """The ``pool`` query parameter, if the requester assists that department."""
    try:
        pool_id = int(request.query_params.get("pool", ""))
    except ValueError:
        raise serializers.ValidationError({"pool": "A department is required."})
    if pool_id not in rights.assistant_pool_ids(request.user):
        raise Http404
    return pool_id


class PeopleSearchView(APIView):
    """Find members of a department by name (assistants and department admins):
    the only place where people are picked by name — fixed owners, "mark
    absent" and "book for". Names only; no e-mail or username is searched or
    returned (except as display fallback for accounts without a name)."""

    permission_classes = [IsDeskAssistant]

    def get(self, request):
        pool_id = _admin_or_assistant_pool(request)
        q = request.query_params.get("q", "").strip()
        if len(q) < PEOPLE_MIN_CHARS:
            raise serializers.ValidationError(
                # Static text (translated as a catalog key); keep in sync.
                {"q": "Enter at least 3 characters."}
            )
        users = (
            get_user_model()
            .objects.filter(is_active=True, pk__in=rights.member_user_ids(pool_id))
            .annotate(full_name=Concat("first_name", Value(" "), "last_name"))
            .filter(
                Q(full_name__icontains=q)
                | Q(first_name="", last_name="", username__icontains=q)
            )
            .order_by("last_name", "first_name", "pk")[:PEOPLE_LIMIT]
        )
        return Response(
            [{"id": u.pk, "name": u.get_full_name() or u.get_username()} for u in users]
        )


class ManageAccessGroupsView(APIView):
    """Access groups a department admin may use as place restrictions: the
    department's own groups plus every ordinary (non-system, non-admin) group."""

    permission_classes = [IsDeskAdmin]

    def get(self, request):
        try:
            pool_id = int(request.query_params.get("pool", ""))
        except ValueError:
            raise serializers.ValidationError({"pool": "A department is required."})
        if pool_id not in rights.admin_pool_ids(request.user):
            raise Http404
        rows = AccessGroup.objects.filter(
            Q(pools__id=pool_id)
            | Q(system_pool__isnull=True, system_admin=False, is_admin=False)
        ).filter(system_pool__isnull=True, system_admin=False, is_admin=False).distinct()
        pool_groups = set(
            AccessGroup.objects.filter(pools__id=pool_id).values_list("pk", flat=True)
        )
        return Response(
            [
                {"id": g.pk, "name": g.name, "in_pool": g.pk in pool_groups}
                for g in rows.order_by("name")
            ]
        )
