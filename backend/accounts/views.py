# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Account-related API views."""
from basicbar_auth.views import whoami_payload
from django.conf import settings
from basicbar_integrations.capabilities import capabilities_payload
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ResourcePool

from .models import (
    AccessGroup,
    RetentionSetting,
    Strike,
    StrikeSetting,
    User,
)
from basicbar_auth.oidc import is_oidc_admin
from .permissions import IsAdmin, IsLenderOrAdmin
from . import retention, roles
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
        .select_related("resource_pool")
        .prefetch_related(
            "items__resource__product__images",
            "items__resource__resource_pool",
            "strikes",
        )
        .order_by(ordering)
    )
    paginator = BookingHistoryPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    serializer = BookingSerializer(page, many=True, context={"request": request})
    return paginator.get_paginated_response(serializer.data)


def _lending_scope_pool_ids(user):
    from lending.scope import admin_membership_pool_ids

    ids = admin_membership_pool_ids(user)
    return sorted(ids) if ids is not None else None


def whoami(request):
    """Return the current session user (for the SPA to check login state).

    The shared part (identity, ``language``, CSRF token) comes from
    basicbar-auth; ``set_language`` and ``logout_view`` are the package's,
    wired by ``basicbar_auth.urls``."""
    payload = whoami_payload(request)
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(payload)
    return JsonResponse(
        {
            **payload,
            # NB: ``is_staff`` here means "app admin" for the SPA, not the
            # Django flag — it reports the role (incl. admin via an access
            # group, #80). ``is_admin`` is the same value under its real name.
            "is_staff": roles.is_app_admin(user),
            "is_admin": roles.is_app_admin(user),
            # Admin via the Django flags themselves (only such admins may
            # change another user's ``is_admin`` toggle).
            "admin_via_flag": bool(user.is_staff or user.is_superuser),
            "is_lender": roles.is_lender(user),
            # Shared feature flags (basicbar-integrations): ai_enabled,
            # content_default_language, content_translation_enabled (#6).
            **capabilities_payload(),
            "content_languages": list(settings.MODELTRANSLATION_LANGUAGES),
            # Admins assigned as lenders: their (active) pools, the default
            # lending-area scope ("My pools" switch). null = no switch.
            "lending_scope_pool_ids": _lending_scope_pool_ids(user),
        }
    )


class ManageUserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-only user management: view accounts and adjust their roles.

    - ``GET``                list/retrieve users (``?search=``, ``?role=``,
      ``?active=1`` for active accounts only).
    - ``PATCH .../<id>/``    set ``is_admin`` / ``is_active`` flags.
    - ``PUT   .../<id>/pools/``  replace the set of pools whose system lender
      group ("Verleiher ‹Pool›") the user is a manual member of.

    Per concept §2, only admins may promote accounts; the catalog/booking
    management endpoints derive the roles from access groups (``accounts.roles``).
    """

    permission_classes = [IsAdmin]
    serializer_class = UserManageSerializer

    def get_queryset(self):
        queryset = User.objects.prefetch_related(
            "access_groups", "strikes__issued_by"
        ).order_by("username")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        if self.request.query_params.get("active") == "1":
            queryset = queryset.filter(is_active=True)
        role = self.request.query_params.get("role")
        if role == "admin":
            queryset = queryset.filter(roles.admin_user_q())
        elif role == "lender":
            queryset = queryset.filter(id__in=roles.lender_user_ids())
        elif role == "borrower":
            queryset = queryset.exclude(roles.admin_user_q()).exclude(
                id__in=roles.lender_user_ids()
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

        # ``is_admin`` sets is_staff + is_superuser, i.e. Django-admin
        # superuser access: only staff/superusers may change it. Group-only
        # admins grant admin rights via the "Administratoren" group instead.
        if "is_admin" in data and not (
            request.user.is_staff or request.user.is_superuser
        ):
            return Response(
                {"detail": "Only staff/superuser admins may change the admin flag; "
                           "grant admin rights via an admin group instead."},
                status=403,
            )

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
        """Sync the user's manual membership in the pools' system lender groups
        to exactly ``pool_ids`` (lender rights via other groups are untouched)."""
        user = self.get_object()
        serializer = UserPoolsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wanted = set(serializer.validated_data["pool_ids"])

        valid_ids = set(
            # incl. trashed pools: the form may send one the user still lends
            ResourcePool.all_objects.filter(pk__in=wanted).values_list("id", flat=True)
        )
        missing = wanted - valid_ids
        if missing:
            return Response(
                {"detail": f"Unknown pool id(s): {sorted(missing)}."}, status=400
            )

        with transaction.atomic():
            for pool in ResourcePool.all_objects.filter(
                Q(pk__in=valid_ids) | Q(lender_group__members=user)
            ).distinct():
                group = roles.ensure_pool_lender_group(pool)
                if pool.pk in valid_ids:
                    group.members.add(user)
                else:
                    group.members.remove(user)
        return Response(self._serialized(user))

    @action(detail=True, methods=["put"], url_path="groups")
    def groups(self, request, pk=None):
        """Sync the user's manual access-group memberships to ``group_ids``
        (pools' system lender groups excluded, see ``pools``)."""
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
        # Pools' system lender groups are edited via ``pools`` (and the pool's
        # lenders endpoint), not here: keep the user's current ones whatever
        # was sent, so saving pools and groups together can't undo each other.
        lender_groups = set(
            user.access_groups.filter(system_pool__isnull=False).values_list(
                "id", flat=True
            )
        )
        regular = set(
            AccessGroup.objects.filter(
                pk__in=valid_ids, system_pool__isnull=True
            ).values_list("id", flat=True)
        )
        new_ids = regular | lender_groups
        with transaction.atomic():
            # Guard against an admin removing their own admin group (as PATCH
            # does for the is_admin toggle); the row lock serialises
            # concurrent lockout checks of the same requester.
            _lock_user(request.user)
            if (
                user.pk == request.user.pk
                and roles.is_app_admin(user)
                and not roles.would_be_admin(user, new_ids)
            ):
                return Response(
                    {"detail": "You cannot remove your own admin rights."}, status=400
                )
            user.access_groups.set(new_ids)
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
                "access_groups", "strikes__issued_by",
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
        return roles.is_app_admin(self.request.user)

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
                managed = roles.managed_pool_ids(request.user)
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
                managed = roles.managed_pool_ids(request.user)
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


def _lock_user(user):
    """Row-lock ``user`` for the surrounding transaction so two concurrent
    requests can't both pass a "keeps own admin rights" check."""
    User.objects.select_for_update().filter(pk=user.pk).first()


class OwnAdminRightsLockout(APIException):
    status_code = 400
    default_detail = "You cannot remove your own admin rights."
    default_code = "own_admin_rights"


class ManageAccessGroupViewSet(viewsets.ModelViewSet):
    """Admin CRUD for access groups (concept §3.4 pool eligibility rules) and
    the rights they grant (#80).

    - System groups can't be deleted; their locked fields are guarded by the
      serializer.
    - An admin can't remove their own admin rights by editing a group's
      ``members`` / ``is_admin`` or deleting an admin group.
    - ``GET .../<id>/members/`` lists the effective members with their source.
    """

    # ``member_count`` = manual members (see AccessGroupSerializer).
    # ``preview_members`` feeds ``member_preview``: only the name columns of
    # the manual members (one query for all groups; small in practice — big
    # audiences come via claim rules, which aren't prefetched).
    queryset = AccessGroup.objects.prefetch_related(
        "pools",
        "lender_pools",
        Prefetch(
            "members",
            queryset=User.objects.only("id", "username", "first_name", "last_name"),
            to_attr="preview_members",
        ),
    ).annotate(member_count=Count("members", distinct=True)).order_by("name")
    serializer_class = AccessGroupSerializer
    permission_classes = [IsAdmin]

    def _other_manual_group_ids(self, group):
        return set(
            self.request.user.access_groups.exclude(pk=group.pk).values_list(
                "id", flat=True
            )
        )

    def _reload(self, serializer):
        """Re-read the saved group so the response carries the annotated,
        current ``member_count``."""
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    def perform_create(self, serializer):
        serializer.save()
        self._reload(serializer)

    @transaction.atomic
    def perform_update(self, serializer):
        user, group = self.request.user, serializer.instance
        data = serializer.validated_data
        _lock_user(user)
        if roles.is_app_admin(user):
            if "members" in data:
                in_group = any(m.pk == user.pk for m in data["members"])
            else:
                in_group = group.members.filter(pk=user.pk).exists()
            keeps_admin = in_group and data.get("is_admin", group.is_admin)
            if not keeps_admin and not roles.would_be_admin(
                user, self._other_manual_group_ids(group)
            ):
                raise OwnAdminRightsLockout()
        serializer.save()
        self._reload(serializer)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        if group.is_system:
            return Response(
                {"detail": "System groups can't be deleted."}, status=400
            )
        _lock_user(request.user)
        if (
            group.is_admin
            and roles.is_app_admin(request.user)
            and not roles.would_be_admin(
                request.user, self._other_manual_group_ids(group)
            )
        ):
            raise OwnAdminRightsLockout()
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        """Effective members (manual, claim-matched and — for
        "Administratoren" — is_staff/is_superuser users), ordered by name."""
        return Response(
            [
                {
                    "id": user.pk,
                    "username": user.username,
                    "name": user.get_full_name(),
                    "email": user.email,
                    "is_active": user.is_active,
                    "source": source,
                }
                for user, source in roles.effective_members(self.get_object())
            ]
        )
