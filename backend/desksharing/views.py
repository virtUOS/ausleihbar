# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q, Value
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
    absences, actions, booking, checkin, hours, notify, overview, privacy, requests as requests_svc, rights, stats as stats_svc,
    series as series_svc,
)
from . import qr as qr_svc
from .models import (
    Absence, DeskSettings, Feature, Floor, Place, ReleaseRequest, Reservation, Room, Series,
    SwapRequest, new_qr_token,
)
from .serializers import (
    AbsenceSerializer,
    ManageAbsenceSerializer,
    SeriesRequestSerializer,
    SeriesSerializer,
    series_result_data,
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

    def perform_destroy(self, instance):
        places = list(Place.objects.filter(**{self.places_lookup: instance}))
        if Reservation.objects.filter(place__in=places).exists():
            booking.retire_places(places)
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        else:
            instance.delete()


class FeatureViewSet(AdminScopedViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer


class FloorViewSet(SoftDeleteContainerMixin, AdminScopedViewSet):
    queryset = Floor.objects.defer("template_data")
    serializer_class = FloorSerializer
    active_lookups = ("is_active",)
    places_lookup = "room__floor"

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


class RoomViewSet(SoftDeleteContainerMixin, AdminScopedViewSet):
    queryset = Room.objects.select_related("floor")
    serializer_class = RoomSerializer
    pool_lookup = "floor__pool_id"
    active_lookups = ("is_active", "floor__is_active")
    places_lookup = "room"


class PlaceViewSet(AdminScopedViewSet):
    queryset = Place.objects.select_related("room__floor", "fixed_owner").prefetch_related(
        "features", "access_groups"
    )
    serializer_class = PlaceSerializer
    pool_lookup = "room__floor__pool_id"
    active_lookups = ("is_active", "room__is_active", "room__floor__is_active")

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
        return Response(
            {
                "reservations": ReservationSerializer(rows, many=True, context={"viewer": request.user}).data,
                "warnings": absences.warnings_for(holder, rows),
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
            .select_related("place__room__floor")
            .order_by("period", "place_id")
        )
        return Response(ReservationSerializer(rows, many=True, context={"viewer": request.user}).data)

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

    @action(detail=True, methods=["get"])
    def neighbours(self, request, pk=None):
        """Who else sits in the same room at that time (opt-out respected)."""
        reservation = self.get_object()
        return Response(overview.room_neighbours(reservation, viewer=request.user))

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
            | Q(place__room__floor__pool_id__in=rights.admin_pool_ids(user))
        ).select_related("place__room__floor__pool", "holder")

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
        try:
            result = series_svc.create_series(
                actor=request.user, holder=holder, place=place,
                weekdays=data["weekdays"], start_hour=data["start_hour"],
                end_hour=data["end_hour"], valid_from=data["valid_from"],
                valid_until=data["valid_until"], comment=data.get("comment", ""),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        except booking.BookingError as exc:
            return booking_error_response(exc)
        data = series_result_data(result, viewer=request.user)
        data["warnings"] = absences.warnings_for(holder, result.created)
        return Response(data, status=201)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        rows = (
            Series.objects.filter(holder=request.user, cancelled_at__isnull=True)
            .select_related("place__room__floor")
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
        try:
            result = series_svc.extend_series(series, actor=request.user)
        except booking.BookingError as exc:
            return booking_error_response(exc)
        return Response(series_result_data(result, viewer=request.user))

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
        absence.delete()
        return Response(status=204)


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
        absence.delete()
        return Response(status=204)


def _int_field(data, name) -> int:
    value = data.get(name) if isinstance(data, dict) else None
    if not isinstance(value, int) or isinstance(value, bool):
        raise serializers.ValidationError({name: "An id is required."})
    return value


def _accept_flag(data) -> bool:
    value = data.get("accept") if isinstance(data, dict) else None
    if not isinstance(value, bool):
        raise serializers.ValidationError({"accept": "true or false is required."})
    return value


def _reservations_qs():
    return Reservation.objects.select_related("place__room__floor__pool", "holder")


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
    """Ask a holder to hand over the rest of a reservation."""

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
        months = pool.max_booking_months or 0
        return Response(
            {
                "open": list(open_hours) if open_hours else None,
                "closed": sorted(hours.closed_hours(pool, day)) if open_hours else [],
                # First bookable hour (the current one) when ``day`` is today.
                "min_hour": local_now.hour if day == local_now.date() else None,
                # Last bookable day (booking horizon); null = unlimited.
                "max_day": (
                    booking.add_months(local_now.date(), months).isoformat() if months else None
                ),
                # Weekdays (0 = Monday) without business hours.
                "closed_weekdays": [
                    d for d in range(7) if not business.get(str(d))
                ],
            }
        )


class PoolFeaturesView(APIView):
    """Equipment features of a department for the booking filter (members)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pool = _member_pool(request)
        rows = Feature.objects.filter(pool=pool).order_by("name", "pk")
        return Response([{"id": f.pk, "name": f.name} for f in rows])


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


PEOPLE_MIN_CHARS = 3
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
                {"q": f"Enter at least {PEOPLE_MIN_CHARS} characters."}
            )
        users = (
            get_user_model()
            .objects.filter(is_active=True)
            .annotate(full_name=Concat("first_name", Value(" "), "last_name"))
            .filter(
                Q(full_name__icontains=q)
                | Q(first_name="", last_name="", username__icontains=q)
            )
            .order_by("last_name", "first_name", "pk")[:100]
        )
        found = []
        for user in users:
            if pool_id in rights.member_pool_ids(user):
                found.append({"id": user.pk, "name": user.get_full_name() or user.get_username()})
                if len(found) == PEOPLE_LIMIT:
                    break
        return Response(found)


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
        ).distinct()
        pool_groups = set(
            AccessGroup.objects.filter(pools__id=pool_id).values_list("pk", flat=True)
        )
        return Response(
            [
                {"id": g.pk, "name": g.name, "in_pool": g.pk in pool_groups}
                for g in rows.order_by("name")
            ]
        )
