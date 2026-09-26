# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Account-related API views."""
from django.conf import settings
from django.contrib.auth import logout as django_logout
from basicbar_integrations import ai, translation_service
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ResourcePool

from .models import (
    AccessGroup,
    PoolMembership,
    RetentionSetting,
    Strike,
    StrikeSetting,
    User,
)
from basicbar_auth.oidc import is_oidc_admin, provider_logout_url
from .permissions import IsAdmin, IsLenderOrAdmin
from . import retention
from .serializers import (
    AccessGroupSerializer,
    BorrowerProfileSerializer,
    RetentionSettingSerializer,
    StrikeSerializer,
    StrikeSettingSerializer,
    UserGroupsUpdateSerializer,
    UserManageSerializer,
    UserPoolsUpdateSerializer,
    UserRoleUpdateSerializer,
)
from .strikes import issue_strike


class BookingHistoryPagination(PageNumberPagination):
    """Smaller pages for the per-user booking history."""

    page_size = 10


def user_booking_history(user, request, view):
    """A user's bookings for one group (paginated), shared by the admin user
    management and the lending-desk borrower profile.

    ``?group=`` is one of ``upcoming`` (pending/confirmed), ``handed_out`` or
    ``completed`` (returned/cancelled). Returns a DRF ``Response``.
    """
    from lending.models import Booking
    from lending.serializers import BookingSerializer

    groups = {
        "upcoming": ([Booking.Status.PENDING, Booking.Status.CONFIRMED], "created_at"),
        "handed_out": ([Booking.Status.HANDED_OUT], "created_at"),
        "completed": (
            [Booking.Status.RETURNED, Booking.Status.CANCELLED],
            "-created_at",
        ),
    }
    group = request.query_params.get("group", "upcoming")
    if group not in groups:
        return Response({"detail": "Unknown 'group'."}, status=400)
    statuses, ordering = groups[group]

    queryset = (
        Booking.objects.filter(borrower=user, status__in=statuses)
        .prefetch_related("items__resource__product", "items__resource__resource_pool")
        .order_by(ordering)
    )
    paginator = BookingHistoryPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    serializer = BookingSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


@ensure_csrf_cookie
def whoami(request):
    """Return the current session user (for the SPA to check login state)."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"authenticated": False})
    return JsonResponse(
        {
            "authenticated": True,
            "username": user.get_username(),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "subject": user.subject,
            "is_staff": user.is_staff,
            "is_lender": bool(
                user.is_staff or user.is_superuser or user.pool_memberships.exists()
            ),
            "language": user.language,
            # Content-translation config so the admin editor knows which language
            # is canonical/required (issue #6, configurable per deployment).
            "content_default_language": settings.MODELTRANSLATION_DEFAULT_LANGUAGE,
            "content_languages": list(settings.MODELTRANSLATION_LANGUAGES),
            # Whether the editor may offer machine-translation pre-fill (#6 P4).
            "content_translation_enabled": translation_service.is_enabled(),
            # Whether AI-assisted features may be offered (optional LiteLLM).
            "ai_enabled": ai.is_enabled(),
        }
    )


class SetLanguageView(APIView):
    """POST /api/whoami/language/ {language} — remember the user's UI/email language."""

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "Not authenticated."}, status=403)
        language = (request.data.get("language") or "").strip()
        if language not in dict(settings.LANGUAGES):
            return Response({"detail": "Unsupported language."}, status=400)
        request.user.language = language
        request.user.save(update_fields=["language"])
        return Response({"language": language})


class ManageUserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-only user management: view accounts and adjust their roles.

    - ``GET``                list/retrieve users (``?search=``, ``?role=``).
    - ``PATCH .../<id>/``    set ``is_admin`` / ``is_active`` flags.
    - ``PUT   .../<id>/pools/``  replace the set of pools the user manages
      (their lender memberships).

    Per concept §2, only admins may promote accounts; the catalog/booking
    management endpoints derive the lender role from these pool memberships.
    """

    permission_classes = [IsAdmin]
    serializer_class = UserManageSerializer

    def get_queryset(self):
        queryset = User.objects.prefetch_related(
            "pool_memberships__resource_pool", "access_groups", "strikes__issued_by"
        ).order_by("username")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        role = self.request.query_params.get("role")
        if role == "admin":
            queryset = queryset.filter(Q(is_staff=True) | Q(is_superuser=True))
        elif role == "lender":
            queryset = queryset.filter(pool_memberships__isnull=False).distinct()
        elif role == "borrower":
            queryset = queryset.filter(
                is_staff=False, is_superuser=False, pool_memberships__isnull=True
            )
        elif role == "inactive":
            queryset = queryset.filter(is_active=False)
        elif role == "blocked":
            queryset = queryset.filter(
                Q(blocked_permanently=True)
                | Q(blocked_until__gt=timezone.now())
            )
        return queryset

    def partial_update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = UserRoleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Guard against an admin locking themselves out.
        if user.pk == request.user.pk:
            if data.get("is_admin") is False:
                return Response(
                    {"detail": "You cannot remove your own admin rights."},
                    status=400,
                )
            if data.get("is_active") is False:
                return Response(
                    {"detail": "You cannot deactivate your own account."},
                    status=400,
                )

        # Admin rights that come from the IdP group are authoritative — a
        # locally-promoted admin must not be able to revoke them here (the group
        # would re-grant them on the next login anyway).
        if data.get("is_admin") is False and is_oidc_admin(user):
            return Response(
                {"detail": "This admin's role is managed by the identity provider "
                           "and cannot be changed here."},
                status=400,
            )

        if "is_admin" in data:
            user.is_staff = data["is_admin"]
            user.is_superuser = data["is_admin"]
        if "is_active" in data:
            user.is_active = data["is_active"]
        user.save()
        return Response(self._serialized(user))

    @action(detail=True, methods=["put"], url_path="pools")
    def pools(self, request, pk=None):
        """Sync the user's lender (manager) memberships to exactly ``pool_ids``."""
        user = self.get_object()
        serializer = UserPoolsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wanted = set(serializer.validated_data["pool_ids"])

        valid_ids = set(
            ResourcePool.objects.filter(pk__in=wanted).values_list("id", flat=True)
        )
        missing = wanted - valid_ids
        if missing:
            return Response(
                {"detail": f"Unknown pool id(s): {sorted(missing)}."}, status=400
            )

        existing = {
            m.resource_pool_id: m
            for m in user.pool_memberships.filter(
                role=PoolMembership.Role.MANAGER
            )
        }
        for pool_id, membership in existing.items():
            if pool_id not in valid_ids:
                membership.delete()
        for pool_id in valid_ids:
            if pool_id not in existing:
                PoolMembership.objects.get_or_create(
                    user=user,
                    resource_pool_id=pool_id,
                    role=PoolMembership.Role.MANAGER,
                )
        return Response(self._serialized(user))

    @action(detail=True, methods=["put"], url_path="groups")
    def groups(self, request, pk=None):
        """Sync the user's manual access-group memberships to ``group_ids``."""
        user = self.get_object()
        serializer = UserGroupsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wanted = set(serializer.validated_data["group_ids"])

        valid_ids = set(
            AccessGroup.objects.filter(pk__in=wanted).values_list("id", flat=True)
        )
        missing = wanted - valid_ids
        if missing:
            return Response(
                {"detail": f"Unknown group id(s): {sorted(missing)}."}, status=400
            )
        user.access_groups.set(valid_ids)
        return Response(self._serialized(user))

    @action(detail=True, methods=["get"], url_path="bookings")
    def bookings(self, request, pk=None):
        """A user's booking history for one group (paginated)."""
        return user_booking_history(self.get_object(), request, self)

    @action(detail=True, methods=["post"], url_path="unblock")
    def unblock(self, request, pk=None):
        """Lift a user's suspension (admin). Does not remove their strikes."""
        user = self.get_object()
        user.blocked_until = None
        user.blocked_permanently = False
        user.save(update_fields=["blocked_until", "blocked_permanently"])
        return Response(self._serialized(user))

    def _serialized(self, user):
        user = (
            User.objects.prefetch_related(
                "pool_memberships__resource_pool", "access_groups",
                "strikes__issued_by",
            ).get(pk=user.pk)
        )
        return UserManageSerializer(user, context=self.get_serializer_context()).data


class ManageBorrowerViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only borrower profile for the lending desk (lenders + admins).

    Lets a lender look up who they're lending to (identity, suspension status,
    strikes) and review the borrower's booking history. Distinct from the
    admin-only ``ManageUserViewSet``, which also edits roles, pools and strikes.
    """

    permission_classes = [IsLenderOrAdmin]
    serializer_class = BorrowerProfileSerializer

    def get_queryset(self):
        return User.objects.prefetch_related("strikes__issued_by")

    @action(detail=True, methods=["get"], url_path="bookings")
    def bookings(self, request, pk=None):
        """The borrower's booking history for one group (paginated)."""
        return user_booking_history(self.get_object(), request, self)


class ManageStrikeViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Issue strikes (lenders/admins) and delete them (admins only, §7.3).

    Lenders issue a strike in the context of a booking they manage; admins may
    also strike a user directly. Strikes are pool-wide.
    """

    queryset = Strike.objects.all()
    serializer_class = StrikeSerializer
    permission_classes = [IsLenderOrAdmin]

    def _is_admin(self):
        user = self.request.user
        return bool(user.is_staff or user.is_superuser)

    def create(self, request, *args, **kwargs):
        from lending.models import Booking, BookingItem

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response({"detail": "A reason is required."}, status=400)

        booking_id = request.data.get("booking")
        user_id = request.data.get("user")
        if booking_id:
            booking = get_object_or_404(Booking, pk=booking_id)
            if booking.status == Booking.Status.CART:
                return Response(
                    {"detail": "This booking hasn't been submitted yet."},
                    status=400,
                )
            if not self._is_admin():
                managed = set(
                    request.user.pool_memberships.values_list(
                        "resource_pool_id", flat=True
                    )
                )
                # A reservation belongs to a single pool (#26) — check that
                # pool directly rather than whether any of its items happens
                # to sit in a managed pool (M4).
                if booking.resource_pool_id not in managed:
                    return Response(
                        {"detail": "You don't manage this booking's pool."},
                        status=403,
                    )
            target = booking.borrower
        elif user_id:
            target = get_object_or_404(User, pk=user_id)
            # A lender may strike a borrower directly (e.g. from the borrower
            # profile) only if that borrower has a booking in a pool the lender
            # manages — the same "manages this borrower's pool" rule as above.
            if not self._is_admin():
                managed = set(
                    request.user.pool_memberships.values_list(
                        "resource_pool_id", flat=True
                    )
                )
                target_pools = set(
                    BookingItem.objects.filter(booking__borrower=target).values_list(
                        "resource__resource_pool_id", flat=True
                    )
                )
                if not (managed & target_pools):
                    return Response(
                        {"detail": "You can only strike borrowers from your pools."},
                        status=403,
                    )
        else:
            return Response({"detail": "Provide 'booking' or 'user'."}, status=400)

        strike = issue_strike(
            target, reason, request.user, booking=booking if booking_id else None
        )
        return Response(StrikeSerializer(strike).data, status=201)

    def destroy(self, request, *args, **kwargs):
        if not self._is_admin():
            return Response(
                {"detail": "Only admins may delete strikes."}, status=403
            )
        return super().destroy(request, *args, **kwargs)


class RetentionSettingView(APIView):
    """GET/PUT the data-retention policy (admins). The GET also reports how many
    accounts would be anonymized right now, so the impact is visible."""

    permission_classes = [IsAdmin]

    def _payload(self, setting):
        data = RetentionSettingSerializer(setting).data
        data["affected_now"] = retention.inactive_candidates(
            setting.retention_days
        ).count()
        return data

    def get(self, request):
        return Response(self._payload(RetentionSetting.load()))

    def put(self, request):
        setting = RetentionSetting.load()
        serializer = RetentionSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self._payload(setting))


class StrikeSettingView(APIView):
    """GET/PUT the system strike policy (admins, concept §7.3)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(StrikeSettingSerializer(StrikeSetting.load()).data)

    def put(self, request):
        setting = StrikeSetting.load()
        serializer = StrikeSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ManageAccessGroupViewSet(viewsets.ModelViewSet):
    """Admin CRUD for access groups (concept §3.4 pool eligibility rules)."""

    queryset = AccessGroup.objects.prefetch_related("pools", "members").all()
    serializer_class = AccessGroupSerializer
    permission_classes = [IsAdmin]


def logout_view(request):
    """Log out of Django and (if logged in via OIDC) the identity provider.

    GET-friendly so the SPA can trigger it with a plain redirect.
    """
    was_authenticated = request.user.is_authenticated
    end_session_url = None
    if was_authenticated and settings.OIDC_OP_LOGOUT_ENDPOINT:
        end_session_url = provider_logout_url(request)
    django_logout(request)
    return redirect(end_session_url or settings.LOGOUT_REDIRECT_URL)
