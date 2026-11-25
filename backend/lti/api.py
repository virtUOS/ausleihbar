# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Management API of the LTI course pools.

- ``GET|PUT /api/manage/lti-setting/`` — the admin switch (admins).
- ``/api/manage/lti/platforms/`` — LMS platform registrations, basicbar-lti's
  CRUD viewset with the app-admin permission.
- ``/api/manage/lti/registration-links/`` — one-time Dynamic Registration
  links (create/list/revoke; admins).
- ``GET /api/manage/lti/tool/`` — the tool's own URLs and public key to paste
  into the LMS registration (admins).
- ``GET /api/manage/pools/<id>/courses/``,
  ``PATCH|DELETE /api/manage/pools/<id>/courses/<link_id>/`` — a pool's
  linked courses (the pool's lenders — incl. its owner — and admins).
"""
from typing import ClassVar

from basicbar_lti.models import LtiToolKey
from basicbar_lti.views import LtiRegistrationTokenViewSet as BaseRegistrationTokenViewSet
from basicbar_lti.views import LtiPlatformViewSet as BaseLtiPlatformViewSet
from basicbar_lti.views import LtiToolInfoView as BaseLtiToolInfoView
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import roles
from accounts.permissions import IsAdmin, IsLenderOrAdmin
from catalog.models import ResourcePool

from . import services
from .models import LtiCourseLink, LtiSetting
from .serializers import (
    LtiSettingSerializer,
    PoolCourseSerializer,
    PoolCourseUpdateSerializer,
)


class LtiSettingView(APIView):
    """GET/PUT the LTI switches (``instructors_create_pools``)."""

    permission_classes: ClassVar = [IsAdmin]

    def get(self, request):
        return Response(LtiSettingSerializer(LtiSetting.load()).data)

    def put(self, request):
        serializer = LtiSettingSerializer(
            LtiSetting.load(), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    patch = put


class LtiPlatformViewSet(BaseLtiPlatformViewSet):
    """basicbar-lti platform CRUD, for app admins (not only Django staff)."""

    permission_classes: ClassVar = [IsAdmin]


class LtiRegistrationTokenViewSet(BaseRegistrationTokenViewSet):
    """One-time Dynamic Registration links, for app admins."""

    permission_classes: ClassVar = [IsAdmin]


class LtiToolInfoView(BaseLtiToolInfoView):
    """basicbar-lti's tool info (login/launch/JWKS/register URLs, built from
    the request's origin) plus the tool's public key."""

    permission_classes: ClassVar = [IsAdmin]

    def get(self, request):
        response = super().get(request)
        response.data["public_key"] = LtiToolKey.load().public_key
        return response


def _pool_for(request, pool_id):
    """The pool, if the requester may manage its courses (404 otherwise):
    admins any live pool, lenders (incl. the owner) their managed pools."""
    pools = ResourcePool.objects.all()
    if not roles.is_app_admin(request.user):
        pools = pools.filter(pk__in=roles.managed_pool_ids(request.user))
    return get_object_or_404(pools, pk=pool_id)


def _courses(pool):
    return (
        LtiCourseLink.objects.filter(pool=pool)
        .select_related("platform", "created_by")
        .annotate(member_count=Count("access_group__members", distinct=True))
        .order_by("-created_at", "-pk")
    )


class PoolCoursesView(APIView):
    """The courses linked to a pool (unpaginated, newest first)."""

    permission_classes: ClassVar = [IsLenderOrAdmin]

    def get(self, request, pool_id):
        pool = _pool_for(request, pool_id)
        return Response(PoolCourseSerializer(_courses(pool), many=True).data)


class PoolCourseDetailView(APIView):
    """Switch a course link on/off (PATCH ``{is_active}``) or delete it
    (DELETE; its system access group and memberships go with it)."""

    permission_classes: ClassVar = [IsLenderOrAdmin]

    def patch(self, request, pool_id, link_id):
        pool = _pool_for(request, pool_id)
        link = get_object_or_404(LtiCourseLink, pk=link_id, pool=pool)
        serializer = PoolCourseUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_link_active(link, serializer.validated_data["is_active"])
        return Response(PoolCourseSerializer(_courses(pool).get(pk=link.pk)).data)

    def delete(self, request, pool_id, link_id):
        pool = _pool_for(request, pool_id)
        link = get_object_or_404(LtiCourseLink, pk=link_id, pool=pool)
        link.delete()
        return Response(status=204)
