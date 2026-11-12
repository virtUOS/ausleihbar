# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

import uuid

from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import roles
from catalog import rich_images
from catalog.models import ResourcePool

from . import rights
from .models import DeskSettings, Feature, Floor, Place, Room, new_qr_token
from .serializers import (
    DeskSettingsSerializer,
    FeatureSerializer,
    FloorPlanSerializer,
    FloorSerializer,
    PlaceSerializer,
    RoomSerializer,
)


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


class FeatureViewSet(AdminScopedViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer


class FloorViewSet(AdminScopedViewSet):
    queryset = Floor.objects.all()
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
        methods=["post"],
        url_path="template",
        parser_classes=[MultiPartParser, FormParser],
    )
    def template(self, request, pk=None):
        floor = self.get_object()
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file uploaded."}, status=400)
        if upload.size > rich_images.RICH_IMAGE_MAX_BYTES:
            return Response({"detail": "Image is too large (max 5 MB)."}, status=400)
        try:
            data, ext = rich_images.process_rich_image(upload.read())
        except ValueError:
            return Response({"detail": "Uploaded file must be an image."}, status=400)
        if floor.template_image:
            floor.template_image.delete(save=False)
        floor.template_image.save(f"{uuid.uuid4().hex}{ext}", ContentFile(data), save=True)
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
        # Soft delete keeps the history of places that were ever reserved.
        if instance.has_reservations():
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
    permission_classes = [IsDeskAdmin]

    def _settings(self, request, pool_id):
        if pool_id not in rights.admin_pool_ids(request.user):
            from django.http import Http404

            raise Http404
        pool = get_object_or_404(ResourcePool, pk=pool_id)
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
