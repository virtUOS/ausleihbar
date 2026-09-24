# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Read API for resource availability (ADR-0006)."""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.eligibility import eligible_pool_ids
from accounts.permissions import IsAdmin, IsLenderOrAdmin
from catalog.models import Product, ProductSet, Resource, ResourcePool

from .confirmations import dispatch_confirmation_mails
from .models import Block, Booking, BookingItem, CartSetting, HolidaySetting
from .notifications import (
    send_cancellation_notice,
    send_overdue_reminder,
    send_reservation_email,
)
from .serializers import (
    BlockCreateSerializer,
    BlockSerializer,
    BookingSerializer,
    CartSettingSerializer,
    HolidaySettingSerializer,
    ManageBookingSerializer,
)
from .services import (
    add_set_to_cart,
    add_to_cart,
    apply_block_to_bookings,
    create_walkin_booking,
    walkin_resource_options,
    availability,
    availability_by_pool,
    set_availability,
    availability_on_date,
    availability_per_day,
    availability_per_hour,
    closed_days_for_pools,
    get_active_cart,
    holiday_horizon_months,
    hourly_utilization_per_day,
    defect_stats,
    import_holidays,
    lending_tree,
    mark_resource_defective,
    overdue_items,
    product_stats,
    product_timeseries,
    refresh_holidays,
    release_expired_holds,
    set_availability_per_day,
    set_availability_per_hour,
    set_hourly_utilization_per_day,
    submit_cart,
)


def _parse_bound(value, *, is_end):
    """Parse an ISO datetime or date into an aware datetime.

    A date-only value maps to midnight; for the end bound one day is added so
    a day range like start=2026-06-01&end=2026-06-01 covers the whole day.
    """
    if not value:
        return None
    # Date-only value (no time component) -> treat as a full day.
    if "T" not in value and ":" not in value:
        d = parse_date(value)
        if d is None:
            return None
        dt = datetime.combine(d, time.min)
        if is_end:
            dt += timedelta(days=1)
    else:
        dt = parse_datetime(value)
        if dt is None:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _visible_pool_ids(request, product):
    """Eligible pool ids for the request user, or 404 if the product is hidden.

    A product is visible when it has at least one resource in a pool the user
    may access (concept §3.4). Returns the eligible pool-id set to pass to the
    availability services so counts only reflect usable pools.
    """
    pool_ids = eligible_pool_ids(request.user)
    if not product.resources.filter(resource_pool_id__in=pool_ids).exists():
        raise Http404("No such product.")
    return pool_ids


def _scoped_pool_ids(request, product):
    """Eligible pool ids, optionally narrowed to a chosen `pool` query/body param
    (#10). 404 if the product is hidden; the chosen pool must be eligible and hold
    a resource for this product, else ignored (falls back to all eligible)."""
    pool_ids = _visible_pool_ids(request, product)  # may raise 404
    raw = request.query_params.get("pool")
    if raw is None:
        raw = (request.data or {}).get("pool")  # POST add-to-cart body
    if raw:
        try:
            chosen = int(raw)
        except (TypeError, ValueError):
            chosen = None
        if chosen in pool_ids and product.resources.filter(resource_pool_id=chosen).exists():
            return {chosen}
    return pool_ids


def _blocked_response(user):
    """A 403 Response if the user is suspended (concept §7.3), else None."""
    if not user.is_blocked():
        return None
    if user.blocked_permanently:
        message = "Your account is blocked from borrowing."
    else:
        message = (
            f"Your account is blocked from borrowing until "
            f"{user.blocked_until:%Y-%m-%d}."
        )
    return Response({"detail": message}, status=403)


class ProductAvailabilityView(APIView):
    """GET /api/products/<id>/availability/?start=<iso>&end=<iso>"""

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        pool_ids = _scoped_pool_ids(request, product)
        start = _parse_bound(request.query_params.get("start"), is_end=False)
        end = _parse_bound(request.query_params.get("end"), is_end=True)
        if start is None or end is None:
            return Response(
                {"detail": "Provide valid 'start' and 'end' (ISO date or datetime)."},
                status=400,
            )
        if end <= start:
            return Response({"detail": "'end' must be after 'start'."}, status=400)

        data = availability(product, start, end, pool_ids)
        data.update({"start": start.isoformat(), "end": end.isoformat()})
        return Response(data)


class ProductPoolAvailabilityView(APIView):
    """GET /api/products/<id>/availability/pools/?start=<iso>&end=<iso>

    Per-pool availability breakdown for the exact selection, across every pool
    the user may access (used to choose the pick-up pool after a date is picked,
    #10). Ignores any `pool` param — it always returns the full eligible set.
    """

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        pool_ids = _visible_pool_ids(request, product)  # 404 if hidden
        start = _parse_bound(request.query_params.get("start"), is_end=False)
        end = _parse_bound(request.query_params.get("end"), is_end=True)
        if start is None or end is None:
            return Response(
                {"detail": "Provide valid 'start' and 'end' (ISO date or datetime)."},
                status=400,
            )
        if end <= start:
            return Response({"detail": "'end' must be after 'start'."}, status=400)

        rows = availability_by_pool(product, start, end, pool_ids)
        meta = {
            p.id: p
            for p in ResourcePool.objects.filter(id__in=[r["pool_id"] for r in rows])
        }
        pools = [
            {
                "pool_id": r["pool_id"],
                "name": meta[r["pool_id"]].name,
                "accent_color": meta[r["pool_id"]].accent_color,
                "position": meta[r["pool_id"]].position,
                "total": r["total"],
                "available": r["available"],
            }
            for r in rows
        ]
        return Response({"pools": pools})


class ProductAvailabilityCalendarView(APIView):
    """GET /api/products/<id>/availability/calendar/?from=<date>&to=<date>

    Returns the available count per day, for colouring a month calendar.
    """

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        pool_ids = _scoped_pool_ids(request, product)
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)
        return Response(
            {"days": availability_per_day(product, from_date, to_date, pool_ids)}
        )


class ProductHourlyAvailabilityView(APIView):
    """GET /api/products/<id>/availability/hours/?date=<date>

    Per-hour availability within opening hours, for the hourly booking grid.
    """

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        pool_ids = _scoped_pool_ids(request, product)
        date = parse_date(request.query_params.get("date") or "")
        if date is None:
            return Response({"detail": "Provide a valid 'date'."}, status=400)
        return Response(
            {
                "date": date.isoformat(),
                "slots": availability_per_hour(product, date, pool_ids),
                "min_hours": product.min_duration,
                "max_hours": product.max_duration,
            }
        )


class ProductHourlyCalendarView(APIView):
    """GET /api/products/<id>/availability/hours/calendar/?from=&to=

    Per-day capacity utilization (booked %) for an hourly product's month grid.
    """

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        pool_ids = _scoped_pool_ids(request, product)
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)
        return Response(
            {"days": hourly_utilization_per_day(product, from_date, to_date, pool_ids)}
        )


def _bookable_set_or_404(request, set_id):
    """Fetch a set whose pool the requester may access, else 404."""
    product_set = get_object_or_404(ProductSet, pk=set_id)
    pool_id = product_set.resource_pool_id
    if pool_id is None or pool_id not in eligible_pool_ids(request.user):
        raise Http404("This set isn't bookable.")
    return product_set


class SetAvailabilityView(APIView):
    """GET /api/sets/<set_id>/availability/?start=&end=

    Availability of a whole set — limited by the scarcest product.
    """

    def get(self, request, set_id):
        product_set = _bookable_set_or_404(request, set_id)
        start = _parse_bound(request.query_params.get("start"), is_end=False)
        end = _parse_bound(request.query_params.get("end"), is_end=True)
        if start is None or end is None or end <= start:
            return Response({"detail": "Invalid date range."}, status=400)
        return Response(set_availability(product_set, start, end))


class SetAvailabilityCalendarView(APIView):
    """GET /api/sets/<set_id>/availability/calendar/?from=&to= (daily sets)."""

    def get(self, request, set_id):
        product_set = _bookable_set_or_404(request, set_id)
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)
        return Response({"days": set_availability_per_day(product_set, from_date, to_date)})


class SetHourlyAvailabilityView(APIView):
    """GET /api/sets/<set_id>/availability/hours/?date= (hourly/mixed sets)."""

    def get(self, request, set_id):
        product_set = _bookable_set_or_404(request, set_id)
        date = parse_date(request.query_params.get("date") or "")
        if date is None:
            return Response({"detail": "Provide a valid 'date'."}, status=400)
        from catalog.sets import set_durations

        min_h, max_h = set_durations(list(product_set.products.all()))
        return Response(
            {
                "date": date.isoformat(),
                "slots": set_availability_per_hour(product_set, date),
                "min_hours": min_h,
                "max_hours": max_h,
            }
        )


class SetHourlyCalendarView(APIView):
    """GET /api/sets/<set_id>/availability/hours/calendar/?from=&to="""

    def get(self, request, set_id):
        product_set = _bookable_set_or_404(request, set_id)
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)
        return Response(
            {"days": set_hourly_utilization_per_day(product_set, from_date, to_date)}
        )


class BulkAvailabilityView(APIView):
    """GET /api/availability/?date=<date>&products=1,2,3

    Per-product availability for one date — for the shop list indicators.
    """

    def get(self, request):
        date = parse_date(request.query_params.get("date") or "")
        if date is None:
            return Response({"detail": "Provide a valid 'date'."}, status=400)
        products_param = request.query_params.get("products")
        if products_param:
            try:
                product_ids = [int(x) for x in products_param.split(",") if x]
            except ValueError:
                return Response({"detail": "Invalid 'products'."}, status=400)
        else:
            product_ids = list(Product.objects.values_list("id", flat=True))

        data = availability_on_date(product_ids, date, eligible_pool_ids(request.user))
        return Response(
            {"date": date.isoformat(), "availability": {str(k): v for k, v in data.items()}}
        )


class HolidayImportView(APIView):
    """POST /api/manage/holidays/import/  {country, subdiv, year, pool?}

    Lenders/admins import public holidays as blocks for the given year.
    """

    permission_classes = [IsLenderOrAdmin]

    def post(self, request):
        country = (request.data.get("country") or "DE").strip()
        subdiv = (request.data.get("subdiv") or "").strip()
        try:
            year = int(request.data.get("year"))
        except (TypeError, ValueError):
            return Response({"detail": "Provide a valid 'year'."}, status=400)

        pool = None
        pool_id = request.data.get("pool")
        if pool_id:
            pool = get_object_or_404(ResourcePool, pk=pool_id)

        try:
            created = import_holidays(country, subdiv, year, pool)
        except (NotImplementedError, KeyError, ValueError) as exc:
            return Response(
                {"detail": f"Unsupported country/subdivision ({exc})."}, status=400
            )
        return Response({"created": created, "count": len(created)})


class BookingViewSet(viewsets.ModelViewSet):
    """The current user's submitted reservations (the cart is separate)."""

    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete"]

    def get_queryset(self):
        return (
            Booking.objects.filter(borrower=self.request.user)
            .exclude(status=Booking.Status.CART)
            .prefetch_related(
                "items__resource__product", "items__resource__resource_pool"
            )
        )

    @action(detail=False, methods=["get"], url_path="by-code")
    def by_code(self, request):
        """The current user's booking with this code — for the pickup deeplink."""
        code = (request.query_params.get("code") or "").strip()
        booking = self.get_queryset().filter(code__iexact=code).first()
        if booking is None:
            return Response({"detail": "No such booking."}, status=404)
        return Response(BookingSerializer(booking, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="current-count")
    def current_count(self, request):
        """How many of the user's bookings are still active — awaiting pickup or
        currently out. Drives the start-page summary (#11) without paging the
        whole (paginated) list, which would undercount for heavy users."""
        count = self.get_queryset().filter(
            status__in=[
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.HANDED_OUT,
            ]
        ).count()
        return Response({"count": count})

    def destroy(self, request, *args, **kwargs):
        booking = self.get_object()
        booking.cancel()
        # Let the lending team know a borrower freed these slots (concept §6.5).
        send_cancellation_notice(booking)
        return Response(status=204)


class CartView(APIView):
    """The current user's cart (a held, not-yet-submitted reservation)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_active_cart(request.user)
        data = BookingSerializer(cart, context={"request": request}).data if cart else None
        return Response({"cart": data})

    def delete(self, request):
        """Discard the whole cart, releasing its held slots."""
        cart = get_active_cart(request.user)
        if cart:
            cart.cancel()
        return Response(status=204)


class CartItemsView(APIView):
    """Add a product/period to the cart."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        blocked = _blocked_response(request.user)
        if blocked:
            return blocked
        product = get_object_or_404(Product, pk=request.data.get("product"))
        pool_ids = _scoped_pool_ids(request, product)
        start = _parse_bound(request.data.get("start"), is_end=False)
        end = _parse_bound(request.data.get("end"), is_end=True)
        if start is None or end is None or end <= start:
            return Response({"detail": "Invalid date range."}, status=400)
        try:
            with transaction.atomic():
                cart = add_to_cart(request.user, product, start, end, pool_ids)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        except IntegrityError:
            return Response(
                {"detail": "The selected period was just taken. Please try again."},
                status=409,
            )
        return Response(
            BookingSerializer(cart, context={"request": request}).data, status=201
        )


class CartSetView(APIView):
    """Add every product of a set to the cart from one pool (concept §4.5)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        blocked = _blocked_response(request.user)
        if blocked:
            return blocked
        product_set = get_object_or_404(ProductSet, pk=request.data.get("set"))
        pool_id = product_set.resource_pool_id
        if pool_id is None or pool_id not in eligible_pool_ids(request.user):
            return Response(
                {"detail": "This set isn't bookable."}, status=400
            )
        start = _parse_bound(request.data.get("start"), is_end=False)
        end = _parse_bound(request.data.get("end"), is_end=True)
        if start is None or end is None or end <= start:
            return Response({"detail": "Invalid date range."}, status=400)
        try:
            with transaction.atomic():
                cart = add_set_to_cart(request.user, product_set, start, end)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        except IntegrityError:
            return Response(
                {"detail": "The selected period was just taken. Please try again."},
                status=409,
            )
        return Response(
            BookingSerializer(cart, context={"request": request}).data, status=201
        )


class CartItemView(APIView):
    """Add one more of, or remove, a single cart item."""

    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        """Add one more unit of an existing line — same product and period, a
        fresh free resource. Powers the cart's quantity stepper, reusing the
        item's exact stored period (no client-side date math)."""
        blocked = _blocked_response(request.user)
        if blocked:
            return blocked
        cart = get_active_cart(request.user)
        if cart is None:
            return Response({"detail": "No active cart."}, status=404)
        item = (
            cart.items.filter(pk=item_id)
            .select_related("resource__product")
            .first()
        )
        if item is None:
            return Response({"detail": "Item not in cart."}, status=404)
        product = item.resource.product
        # Keep the "+1" in the same pool as the rest of this line (#10) — an
        # extra unit from a different pool would split one line's pickup
        # across pools. Intersected with eligibility as a safety net: if the
        # line's own pool somehow isn't visible to this user anymore, this
        # yields an empty set (→ "none available") rather than reaching into
        # a different pool.
        pool_ids = {item.resource.resource_pool_id} & _visible_pool_ids(request, product)
        start, end = item.period.lower, item.period.upper
        try:
            with transaction.atomic():
                cart = add_to_cart(request.user, product, start, end, pool_ids)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        except IntegrityError:
            return Response(
                {"detail": "The selected period was just taken. Please try again."},
                status=409,
            )
        return Response(
            BookingSerializer(cart, context={"request": request}).data, status=201
        )

    def delete(self, request, item_id):
        cart = get_active_cart(request.user)
        if cart is None:
            return Response({"detail": "No active cart."}, status=404)
        item = cart.items.filter(pk=item_id).first()
        if item is None:
            return Response({"detail": "Item not in cart."}, status=404)
        item.delete()
        cart.refresh_from_db()
        return Response(BookingSerializer(cart, context={"request": request}).data)


class CartSubmitView(APIView):
    """Submit the cart as a reservation (awaiting lender confirmation)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        blocked = _blocked_response(request.user)
        if blocked:
            return blocked
        cart = get_active_cart(request.user)
        if cart is None or not cart.items.filter(is_active=True).exists():
            return Response({"detail": "Your cart is empty."}, status=400)
        note = (request.data.get("note") or "").strip()
        note_required = cart.items.filter(
            is_active=True, resource__resource_pool__require_booking_note=True
        ).exists()
        if note_required and not note:
            return Response(
                {
                    "detail": "A message to the lending team is required for this order.",
                    "note_required": True,
                },
                status=400,
            )
        bookings = submit_cart(cart, note)
        send_reservation_email(bookings)
        return Response(
            {
                "bookings": BookingSerializer(
                    bookings, many=True, context={"request": request}
                ).data
            },
            status=201,
        )


User = get_user_model()


def _managed_pool_ids(user):
    """Pool ids the user may lend from: their managed pools, or all (admin)."""
    if user.is_staff or user.is_superuser:
        qs = ResourcePool.objects.filter(is_active=True)
    else:
        qs = ResourcePool.objects.filter(memberships__user=user)
    return set(qs.values_list("id", flat=True))


class WalkinContextView(APIView):
    """GET /api/manage/walkin/context/ — pools the lender may lend from."""

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        pools = (
            ResourcePool.objects.filter(id__in=_managed_pool_ids(request.user))
            .order_by("name")
            .values("id", "name", "room")
        )
        return Response({"pools": list(pools)})


class WalkinProductsView(APIView):
    """GET /api/manage/walkin/products/?pool=<id> — products stocked in a pool."""

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        try:
            pool_id = int(request.query_params.get("pool"))
        except (TypeError, ValueError):
            return Response({"detail": "Provide a 'pool' id."}, status=400)
        if pool_id not in _managed_pool_ids(request.user):
            return Response({"detail": "You don't manage this pool."}, status=403)
        products = (
            Product.objects.filter(
                resources__resource_pool_id=pool_id,
                resources__status=Resource.Status.AVAILABLE,
            )
            .distinct()
            .order_by("title")
            .values("id", "title", "lending_type")
        )
        return Response({"products": list(products)})


def _walkin_target(request):
    """Resolve (product, pool_id) for a walk-in calendar from query params.

    Returns ``(product, pool_id, None)`` or ``(None, None, error_response)``.
    """
    try:
        pool_id = int(request.query_params.get("pool"))
    except (TypeError, ValueError):
        return None, None, Response({"detail": "Provide a 'pool' id."}, status=400)
    if pool_id not in _managed_pool_ids(request.user):
        return None, None, Response(
            {"detail": "You don't manage this pool."}, status=403
        )
    product = get_object_or_404(Product, pk=request.query_params.get("product"))
    return product, pool_id, None


class WalkinProductCalendarView(APIView):
    """GET /api/manage/walkin/availability/calendar/?product=&pool=&from=&to=

    Per-day availability for a daily product, bypassing lead time / horizon.
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        product, pool_id, error = _walkin_target(request)
        if error:
            return error
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)
        return Response(
            {
                "days": availability_per_day(
                    product, from_date, to_date, {pool_id}, ignore_planning=True
                )
            }
        )


class WalkinResourcesView(APIView):
    """GET /api/manage/walkin/resources/?product=&pool=&start=&end=

    The lendable units of a product in a pool, each flagged for a time conflict
    so the lender can choose which unit was handed out (concept §6.4).
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        product, pool_id, error = _walkin_target(request)
        if error:
            return error
        start = _parse_bound(request.query_params.get("start"), is_end=False)
        end = _parse_bound(request.query_params.get("end"), is_end=True)
        if start is None or end is None or end <= start:
            return Response({"detail": "Invalid date range."}, status=400)
        return Response(
            {"resources": walkin_resource_options(product, pool_id, start, end)}
        )


class WalkinProductHourlyView(APIView):
    """GET /api/manage/walkin/availability/hours/?product=&pool=&date="""

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        product, pool_id, error = _walkin_target(request)
        if error:
            return error
        date = parse_date(request.query_params.get("date") or "")
        if date is None:
            return Response({"detail": "Provide a valid 'date'."}, status=400)
        return Response(
            {
                "date": date.isoformat(),
                "slots": availability_per_hour(
                    product, date, {pool_id}, ignore_planning=True
                ),
                "min_hours": product.min_duration,
                "max_hours": product.max_duration,
            }
        )


class WalkinProductHourlyCalendarView(APIView):
    """GET /api/manage/walkin/availability/hours/calendar/?product=&pool=&from=&to="""

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        product, pool_id, error = _walkin_target(request)
        if error:
            return error
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)
        return Response(
            {
                "days": hourly_utilization_per_day(
                    product, from_date, to_date, {pool_id}, ignore_planning=True
                )
            }
        )


class BorrowerSearchView(APIView):
    """GET /api/manage/borrower-search/?q=<term> — pick a borrower for a walk-in."""

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        term = (request.query_params.get("q") or "").strip()
        qs = User.objects.all()
        if term:
            qs = qs.filter(
                Q(username__icontains=term)
                | Q(email__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
            )
        qs = qs.order_by("username")[:20]
        return Response(
            [
                {
                    "id": u.id,
                    "username": u.username,
                    "full_name": u.get_full_name(),
                    "email": u.email,
                    "is_blocked": u.is_blocked(),
                }
                for u in qs
            ]
        )


class WalkinCreateView(APIView):
    """POST /api/manage/walkin/ — lender creates a walk-in lending (concept §6.4).

    Body: ``{borrower, pool, hand_out, items: [{product, start, end}, ...]}``.
    Bypasses lead time / horizon; the borrower must not be suspended.
    """

    permission_classes = [IsLenderOrAdmin]

    def post(self, request):
        try:
            pool_id = int(request.data.get("pool"))
        except (TypeError, ValueError):
            return Response({"detail": "Provide a 'pool' id."}, status=400)
        if pool_id not in _managed_pool_ids(request.user):
            return Response({"detail": "You don't manage this pool."}, status=403)

        borrower = get_object_or_404(User, pk=request.data.get("borrower"))
        if borrower.is_blocked():
            return Response(
                {"detail": "This borrower's account is currently suspended."},
                status=400,
            )

        raw_items = request.data.get("items") or []
        if not isinstance(raw_items, list) or not raw_items:
            return Response({"detail": "Add at least one item."}, status=400)
        items = []
        for entry in raw_items:
            product = get_object_or_404(Product, pk=entry.get("product"))
            start = _parse_bound(entry.get("start"), is_end=False)
            end = _parse_bound(entry.get("end"), is_end=True)
            if start is None or end is None or end <= start:
                return Response({"detail": "Invalid date range."}, status=400)
            resource = None
            if entry.get("resource"):
                resource = get_object_or_404(Resource, pk=entry.get("resource"))
            items.append((product, start, end, resource))

        hand_out = bool(request.data.get("hand_out"))
        note = (request.data.get("note") or "").strip()
        try:
            with transaction.atomic():
                booking = create_walkin_booking(
                    borrower, pool_id, items, hand_out, note=note
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        except IntegrityError:
            return Response(
                {"detail": "A selected period was just taken. Please try again."},
                status=409,
            )
        dispatch_confirmation_mails(booking)
        return Response(ManageBookingSerializer(booking).data, status=201)


class ManageBookingViewSet(viewsets.ReadOnlyModelViewSet):
    """Lender/admin view of bookings with status transitions (concept §6)."""

    serializer_class = ManageBookingSerializer
    permission_classes = [IsLenderOrAdmin]

    def get_queryset(self):
        user = self.request.user
        queryset = (
            Booking.objects.select_related("borrower")
            .exclude(status=Booking.Status.CART)  # carts aren't reservations yet
            .prefetch_related(
                "items__resource__product",
                "items__resource__resource_pool",
                "reminders",
            )
            .order_by("-created_at")
        )
        # Admins see everything; lenders only bookings in pools they manage
        # (the reservation's own pool, #26 — not merely a pool one of its
        # items happens to sit in).
        if not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(
                resource_pool__memberships__user=user
            ).distinct()
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(borrower__username__icontains=search)
                | Q(items__resource__product__title__icontains=search)
            ).distinct()
        return queryset

    def _transition(self, expected_status, apply, error):
        booking = self.get_object()
        if booking.status != expected_status:
            return Response({"detail": error}, status=400)
        apply(booking)
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        # Optional one-off note the lender adds to this confirmation email
        # (e.g. a pickup-time suggestion, concept §6.2 / issue #29).
        message = (request.data.get("message") or "").strip()
        response = self._transition(
            Booking.Status.PENDING,
            lambda b: b.confirm(message),
            "Only pending bookings can be confirmed.",
        )
        if response.status_code == 200:
            dispatch_confirmation_mails(self.get_object())
        return response

    @action(detail=True, methods=["post"])
    def handout(self, request, pk=None):
        """Hand out items of one appointment (``item_ids``) or the whole booking."""
        booking = self.get_object()
        if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT):
            return Response(
                {"detail": "Only confirmed reservations can be handed out."},
                status=400,
            )
        item_ids = request.data.get("item_ids")
        booking.hand_out_items(item_ids)
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=False, methods=["get"], url_path="by-code")
    def by_code(self, request):
        """Look up a (scoped) booking by its code — for the QR pickup scan."""
        code = (request.query_params.get("code") or "").strip()
        if not code:
            return Response({"detail": "Provide a booking 'code'."}, status=400)
        booking = self.get_queryset().filter(code__iexact=code).first()
        if booking is None:
            return Response(
                {"detail": "No booking with that code in your pools."}, status=404
            )
        return Response(ManageBookingSerializer(booking).data)

    @action(detail=False, methods=["get"], url_path="resolve-resource")
    def resolve_resource(self, request):
        """Resolve a scanned device QR (its ``qr_code_id``) to a resource.

        Scoped to the lender's managed pools, so a lender can only act on
        devices they're responsible for.
        """
        qr = (request.query_params.get("qr") or "").strip()
        if not qr:
            return Response({"detail": "Provide a device 'qr' id."}, status=400)
        resource = (
            Resource.objects.filter(
                qr_code_id=qr,
                resource_pool_id__in=_managed_pool_ids(request.user),
            )
            .select_related("product", "resource_pool")
            .first()
        )
        if resource is None:
            return Response(
                {"detail": "Unknown device, or not in your pools."}, status=404
            )
        return Response(
            {
                "id": resource.id,
                "qr_code_id": resource.qr_code_id,
                "inventory_number": resource.inventory_number,
                "status": resource.status,
                "product": resource.product_id,
                "product_title": resource.product.title,
                "pool_id": resource.resource_pool_id,
                "pool_name": resource.resource_pool.name,
            }
        )

    @action(detail=False, methods=["get"])
    def scan(self, request):
        """Resolve any scan (a pickup code or a device QR) to the next action.

        Returns ``kind``/``mode`` so the QR desk can route:
        - a booking code → ``mode="handout"`` with the booking;
        - a device that is currently out → ``mode="return"`` with its booking;
        - a device reserved for a due pickup → ``mode="handout"`` with it;
        - any other device → ``mode="idle"`` (show storage + defect controls).
        Scoped to the lender's managed pools.
        """
        raw = (request.query_params.get("value") or "").strip()
        if not raw:
            return Response({"detail": "Provide a scanned 'value'."}, status=400)
        # Accept a bare id or a resource URL like ".../r/<qr>".
        value = raw.rstrip("/").split("/")[-1]

        booking = self.get_queryset().filter(code__iexact=value).first()
        if booking is not None:
            return Response(
                {
                    "kind": "booking",
                    "mode": "handout",
                    "resource": None,
                    "booking": ManageBookingSerializer(booking).data,
                }
            )

        scope = _managed_pool_ids(request.user)
        resource = (
            Resource.objects.filter(qr_code_id__iexact=value, resource_pool_id__in=scope)
            .select_related("product", "resource_pool")
            .first()
        )
        if resource is None:
            return Response(
                {"detail": "Unknown code or device, or not in your pools."}, status=404
            )
        payload = {
            "id": resource.id,
            "inventory_number": resource.inventory_number,
            "product_title": resource.product.title,
            "pool_name": resource.resource_pool.name,
            "status": resource.status,
            "storage_location": resource.storage_location,
            "defect_note": resource.defect_note,
        }

        out_item = (
            BookingItem.objects.filter(
                resource=resource,
                is_active=True,
                handed_out_at__isnull=False,
                returned_at__isnull=True,
            )
            .select_related("booking")
            .order_by("-handed_out_at")
            .first()
        )
        if out_item is not None:
            return Response(
                {
                    "kind": "resource",
                    "mode": "return",
                    "resource": payload,
                    "booking": ManageBookingSerializer(out_item.booking).data,
                }
            )

        # A confirmed reservation whose pickup time has arrived → hand it out.
        now = timezone.now()
        due = next(
            (
                item
                for item in BookingItem.objects.filter(
                    resource=resource,
                    is_active=True,
                    handed_out_at__isnull=True,
                    returned_at__isnull=True,
                    booking__status=Booking.Status.CONFIRMED,
                )
                .select_related("booking")
                .order_by("id")
                if item.period and item.period.lower and item.period.lower <= now
            ),
            None,
        )
        if due is not None:
            return Response(
                {
                    "kind": "resource",
                    "mode": "handout",
                    "resource": payload,
                    "booking": ManageBookingSerializer(due.booking).data,
                }
            )

        return Response(
            {"kind": "resource", "mode": "idle", "resource": payload, "booking": None}
        )

    @action(detail=True, methods=["post"])
    def swap(self, request, pk=None):
        """Swap a booked item to a different unit of the *same* product.

        Used when the scanned device differs from the reserved unit but is the
        same product (concept §6.2).
        """
        booking = self.get_object()
        item = booking.items.filter(pk=request.data.get("item_id")).first()
        if item is None or not item.is_active or item.handed_out_at or item.returned_at:
            return Response({"detail": "No such open item on this booking."}, status=400)
        resource = get_object_or_404(Resource, pk=request.data.get("resource"))
        if resource.product_id != item.resource.product_id:
            return Response(
                {"detail": "The unit must be of the same product to swap."}, status=400
            )
        if resource.resource_pool_id != booking.resource_pool_id:
            return Response(
                {"detail": "The unit must be from this reservation's pool."}, status=400
            )
        if resource.status != Resource.Status.AVAILABLE:
            return Response({"detail": "That unit isn't available."}, status=400)
        try:
            with transaction.atomic():
                item.resource = resource
                item.save(update_fields=["resource"])
        except IntegrityError:
            return Response(
                {"detail": "That unit is booked in this period."}, status=409
            )
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="add-item")
    def add_item(self, request, pk=None):
        """Add an ad-hoc unit (a different product) to an existing booking.

        Used when the scanned device isn't part of the booking (concept §6.2);
        it takes the booking's overall period.
        """
        booking = self.get_object()
        if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT):
            return Response(
                {"detail": "Items can only be added to a confirmed booking."},
                status=400,
            )
        resource = get_object_or_404(Resource, pk=request.data.get("resource"))
        if resource.resource_pool_id != booking.resource_pool_id:
            return Response(
                {"detail": "The unit must be from this reservation's pool."}, status=400
            )
        if resource.status != Resource.Status.AVAILABLE:
            return Response({"detail": "That unit isn't available."}, status=400)
        active = list(booking.items.filter(is_active=True))
        if not active:
            return Response({"detail": "This booking has no active items."}, status=400)
        lower = min(i.period.lower for i in active)
        upper = max(i.period.upper for i in active)
        try:
            with transaction.atomic():
                BookingItem.objects.create(
                    booking=booking,
                    resource=resource,
                    period=DateTimeTZRange(lower, upper),
                )
        except IntegrityError:
            return Response(
                {"detail": "That unit is booked in this period."}, status=409
            )
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_booking(self, request, pk=None):
        """Take back items of one appointment (``item_ids``) or all handed-out items."""
        booking = self.get_object()
        if booking.status not in (Booking.Status.HANDED_OUT, Booking.Status.RETURNED):
            return Response(
                {"detail": "Only handed-out items can be returned."}, status=400
            )
        item_ids = request.data.get("item_ids")
        booking.return_items(item_ids)
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a reservation (lender side) — e.g. an overdue, never-collected one.

        Allowed as long as nothing has actually been handed out; if items are
        out, return them first.
        """
        booking = self.get_object()
        if booking.status in (Booking.Status.CANCELLED, Booking.Status.RETURNED):
            return Response({"detail": "This reservation is already closed."}, status=400)
        if booking.items.filter(
            handed_out_at__isnull=False, returned_at__isnull=True
        ).exists():
            return Response(
                {"detail": "Return the handed-out items before cancelling."},
                status=400,
            )
        booking.cancel()
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def remind(self, request, pk=None):
        """Email the borrower about this reservation's overdue pickups/returns."""
        booking = self.get_object()
        pickups, returns = overdue_items(booking)
        if not pickups and not returns:
            return Response({"detail": "Nothing overdue on this reservation."}, status=400)
        send_overdue_reminder(booking, pickups, returns)
        booking.overdue_reminded_at = timezone.now()
        booking.save(update_fields=["overdue_reminded_at", "updated_at"])
        return Response(ManageBookingSerializer(self.get_object()).data)

    @action(detail=False, methods=["get"], url_path="pending-count")
    def pending_count(self, request):
        """Number of reservations awaiting confirmation in the user's pools.

        Drives the notification badge in the lending desk navigation.
        """
        count = self.get_queryset().filter(status=Booking.Status.PENDING).count()
        return Response({"count": count})

    @action(detail=False, methods=["get"])
    def day(self, request):
        """Daily overview (concept §6.1): pickups, returns, overdue, to confirm.

        ?date=YYYY-MM-DD (defaults to today). Pending reservations are listed
        regardless of date; pickups/returns are bucketed by the booking's
        local start/end date.
        """
        day = parse_date(request.query_params.get("date") or "") or timezone.localdate()
        today = timezone.localdate()
        buckets = {"to_confirm": [], "pickups": [], "returns": [], "overdue": []}
        micro = timedelta(microseconds=1)

        for booking in self.get_queryset():
            if booking.status == Booking.Status.PENDING:
                buckets["to_confirm"].append(booking)
                continue
            if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT):
                continue
            # Per item: an item awaiting pickup is a pickup on its start day; an
            # item that is out is a return on its last booked day. Already
            # returned items are done.
            has_pickup = has_return = has_overdue = False
            for item in booking.items.all():
                if not item.period or item.returned_at:
                    continue
                start_day = (
                    timezone.localtime(item.period.lower).date()
                    if item.period.lower else None
                )
                last_day = (
                    timezone.localtime(item.period.upper - micro).date()
                    if item.period.upper else None
                )
                if item.handed_out_at is None:  # awaiting pickup
                    if start_day == day:
                        has_pickup = True
                    elif start_day and start_day < today:
                        has_overdue = True
                else:  # out, awaiting return
                    if last_day == day:
                        has_return = True
                    elif last_day and last_day < today:
                        has_overdue = True
            if has_pickup:
                buckets["pickups"].append(booking)
            if has_return:
                buckets["returns"].append(booking)
            if has_overdue and not has_pickup and not has_return:
                buckets["overdue"].append(booking)

        data = {
            key: ManageBookingSerializer(value, many=True).data
            for key, value in buckets.items()
        }
        data["date"] = day.isoformat()
        return Response(data)

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """Per-day activity counts (pickups/returns) for marking a calendar.

        Mirrors the day overview so the calendar and the day's lists agree: an
        item still awaiting pickup counts as a pickup on its start day; an item
        that is out counts as a return on its last booked day. Returned items
        are done, and pending (unconfirmed) reservations aren't desk work yet.
        """
        from_date = parse_date(request.query_params.get("from") or "")
        to_date = parse_date(request.query_params.get("to") or "")
        if from_date is None or to_date is None or to_date <= from_date:
            return Response({"detail": "Provide valid 'from' and 'to' dates."}, status=400)
        if (to_date - from_date).days > 62:
            return Response({"detail": "Range too large (max 62 days)."}, status=400)

        counts = {}

        def bump(local_dt, key):
            d = timezone.localtime(local_dt).date()
            if from_date <= d < to_date:
                entry = counts.setdefault(d, {"pickups": 0, "returns": 0})
                entry[key] += 1

        scoped = self.get_queryset().filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.HANDED_OUT]
        )
        for booking in scoped:
            for item in booking.items.all():
                if not item.period or item.returned_at:
                    continue
                if item.handed_out_at is None:
                    # Awaiting pickup → a pickup on its start day.
                    if item.period.lower:
                        bump(item.period.lower, "pickups")
                elif item.period.upper:
                    # Out → a return on its last booked day (inclusive end, not
                    # the exclusive upper bound which is the following midnight).
                    bump(item.period.upper - timedelta(microseconds=1), "returns")

        days = [
            {"date": d.isoformat(), "pickups": c["pickups"], "returns": c["returns"]}
            for d, c in sorted(counts.items())
        ]

        # Grey out days on which every in-scope pool is closed.
        user = request.user
        pools = ResourcePool.objects.filter(is_active=True)
        if not (user.is_staff or user.is_superuser):
            pools = pools.filter(memberships__user=user)
        pool_ids = set(pools.values_list("id", flat=True))
        closed_days = closed_days_for_pools(pool_ids, from_date, to_date)

        return Response({"days": days, "closed_days": closed_days})


class ManageResourceViewSet(viewsets.GenericViewSet):
    """Lender/admin operations on physical resources (concept §6: defects)."""

    permission_classes = [IsLenderOrAdmin]

    def get_queryset(self):
        user = self.request.user
        queryset = Resource.objects.select_related("product", "resource_pool")
        # Admins manage every resource; lenders only those in their pools.
        if not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(
                resource_pool__memberships__user=user
            ).distinct()
        return queryset

    def _set_status(self, pk, new_status, allowed_from, defect_note):
        resource = get_object_or_404(self.get_queryset(), pk=pk)
        if resource.status not in allowed_from:
            return Response(
                {"detail": f"A {resource.get_status_display().lower()} resource "
                           "cannot be changed here."},
                status=400,
            )
        resource.status = new_status
        resource.defect_note = defect_note
        resource.save(update_fields=["status", "defect_note", "updated_at"])
        return Response(
            {
                "id": resource.id,
                "inventory_number": resource.inventory_number,
                "status": resource.status,
                "defect_note": resource.defect_note,
            }
        )

    @action(detail=True, methods=["post"])
    def defective(self, request, pk=None):
        """Flag a working resource as defective and rebook its upcoming bookings.

        An optional ``note`` describes what is wrong. Affected bookings are moved
        to free units of the same product/pool where possible; otherwise the
        borrowers are notified (concept §3.6).
        """
        resource = get_object_or_404(self.get_queryset(), pk=pk)
        if resource.status != Resource.Status.AVAILABLE:
            return Response(
                {"detail": f"A {resource.get_status_display().lower()} resource "
                           "cannot be flagged here."},
                status=400,
            )
        note = (request.data.get("note") or "").strip()[:500]
        summary = mark_resource_defective(resource, note)
        return Response(
            {
                "id": resource.id,
                "inventory_number": resource.inventory_number,
                "status": resource.status,
                "defect_note": resource.defect_note,
                "rebooked": summary["rebooked"],
                "unfulfilled": summary["unfulfilled"],
            }
        )

    @action(detail=True, methods=["post"], url_path="available")
    def make_available(self, request, pk=None):
        """Return a repaired resource to service (clears the defect note)."""
        return self._set_status(
            pk, Resource.Status.AVAILABLE, {Resource.Status.DEFECTIVE}, ""
        )


class ManageBlockViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Manage block days (Sperrtage).

    Admins see and manage all blocks (system-wide + every pool); lenders manage
    only blocks for the pools they run. ``?pool=<id>`` filters to one pool.
    """

    permission_classes = [IsLenderOrAdmin]

    def _is_admin(self):
        user = self.request.user
        return bool(user.is_staff or user.is_superuser)

    def _managed_pool_ids(self):
        return set(
            self.request.user.pool_memberships.values_list(
                "resource_pool_id", flat=True
            )
        )

    def get_serializer_class(self):
        if self.action == "create":
            return BlockCreateSerializer
        return BlockSerializer

    def get_queryset(self):
        queryset = Block.objects.select_related("resource_pool").all()
        if not self._is_admin():
            queryset = queryset.filter(resource_pool_id__in=self._managed_pool_ids())
        pool = self.request.query_params.get("pool")
        if pool:
            queryset = queryset.filter(resource_pool_id=pool)
        return queryset.order_by("period")

    def create(self, request, *args, **kwargs):
        serializer = BlockCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pool = serializer.validated_data.get("resource_pool")
        if not self._is_admin():
            if pool is None or pool.id not in self._managed_pool_ids():
                return Response(
                    {"detail": "You can only block days for pools you manage."},
                    status=403,
                )
        block = serializer.save()
        # Reschedule / cancel the bookings this closure now collides with and
        # notify the borrowers (concept §3.5).
        adjusted = apply_block_to_bookings(block)
        data = BlockSerializer(block).data
        data["adjusted"] = adjusted
        return Response(data, status=201)

    def destroy(self, request, *args, **kwargs):
        # get_queryset already limits lenders to their own pools' blocks.
        block = self.get_object()
        block.delete()
        return Response(status=204)


class HolidaySettingView(APIView):
    """GET/PUT the system holiday region; PUT also (re)loads holidays.

    Admins set only the country and subdivision (the Land); the system loads
    public holidays across the longest pool booking horizon (concept §3.5).
    """

    permission_classes = [IsAdmin]

    def _payload(self, setting, loaded=None):
        data = HolidaySettingSerializer(setting).data
        data["horizon_months"] = holiday_horizon_months()
        if loaded is not None:
            data["loaded"] = loaded
        return data

    def get(self, request):
        return Response(self._payload(HolidaySetting.load()))

    def put(self, request):
        setting = HolidaySetting.load()
        serializer = HolidaySettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        try:
            created = refresh_holidays()
        except (NotImplementedError, KeyError, ValueError) as exc:
            return Response(
                {"detail": f"Unsupported country/subdivision ({exc})."}, status=400
            )
        return Response(self._payload(setting, loaded=len(created)))


class CartSettingView(APIView):
    """GET/PUT the system cart-hold timeout (concept §4.5).

    ``hold_minutes`` is how long a cart keeps its reserved resources before the
    hold expires; every cart action renews it.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(CartSettingSerializer(CartSetting.load()).data)

    def put(self, request):
        setting = CartSetting.load()
        serializer = CartSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


def _stats_pools(request):
    """(selectable pools, scoped pool ids) for the stats requester.

    Admins get all pools (optionally narrowed by ``?pool``); lenders only the
    pools they manage.
    """
    user = request.user
    if user.is_staff or user.is_superuser:
        pools = ResourcePool.objects.all()
    else:
        pools = ResourcePool.objects.filter(memberships__user=user).distinct()
    pool_param = request.query_params.get("pool")
    scoped = pools.filter(id=pool_param) if pool_param else pools
    return pools, list(scoped.values_list("id", flat=True))


def _stats_window(request):
    """(from_date, to_date) for stats, defaulting to the last 90 days."""
    today = timezone.localdate()
    to_date = parse_date(request.query_params.get("to") or "") or today
    from_date = parse_date(request.query_params.get("from") or "") or (
        to_date - timedelta(days=90)
    )
    return from_date, to_date


class ProductStatsView(APIView):
    """GET /api/manage/stats/products/?from=&to=&pool=

    Per-product lending statistics (every in-scope product, including
    never-borrowed ones). Admins see all pools (optionally filtered by
    ``pool``); lenders see only the pools they manage. Defaults to the last 90
    days. Returns the products plus the pools the requester may filter by.
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        pools, pool_ids = _stats_pools(request)
        from_date, to_date = _stats_window(request)
        if to_date < from_date:
            return Response({"detail": "'to' must not be before 'from'."}, status=400)

        start = timezone.make_aware(datetime.combine(from_date, time.min))
        end = timezone.make_aware(datetime.combine(to_date + timedelta(days=1), time.min))

        return Response(
            {
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "products": product_stats(pool_ids, start, end),
                "pools": [{"id": p.id, "name": p.name} for p in pools.order_by("name")],
            }
        )


class CapacityStatsView(APIView):
    """GET /api/manage/stats/capacity/

    Deployment-wide totals against the optional creation caps (resources,
    products, users). ``max`` is null when no cap is configured. Users counted
    exclude anonymized (deleted) accounts, matching the cap logic.
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        return Response(
            {
                "resources": {
                    "count": Resource.objects.count(),
                    "max": settings.MAX_RESOURCES,
                },
                "products": {
                    "count": Product.objects.count(),
                    "max": settings.MAX_PRODUCTS,
                },
                "users": {
                    "count": User.objects.filter(anonymized_at__isnull=True).count(),
                    "max": settings.MAX_USERS,
                },
            }
        )


class DefectStatsView(APIView):
    """GET /api/manage/stats/defects/?pool=

    Defect statistics for the requester's pools (admins: all, optionally one).
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        _pools, pool_ids = _stats_pools(request)
        return Response(defect_stats(pool_ids))


class ProductTimeseriesView(APIView):
    """GET /api/manage/stats/products/<id>/timeseries/?from=&to=&pool=&bucket=

    How often one product was borrowed per day/week/month over the window.
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request, product_id):
        _pools, pool_ids = _stats_pools(request)
        bucket = request.query_params.get("bucket", "week")
        if bucket not in ("day", "week", "month"):
            return Response({"detail": "bucket must be day, week or month."}, status=400)
        from_date, to_date = _stats_window(request)
        if to_date < from_date:
            return Response({"detail": "'to' must not be before 'from'."}, status=400)

        start = timezone.make_aware(datetime.combine(from_date, time.min))
        end = timezone.make_aware(datetime.combine(to_date + timedelta(days=1), time.min))

        return Response(
            {
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "bucket": bucket,
                "series": product_timeseries(product_id, pool_ids, start, end, bucket),
            }
        )


class BorrowerPagination(PageNumberPagination):
    """Paging for a single resource's borrowing history."""

    page_size = 10


def _booking_row(item):
    booking = item.booking
    period = item.period
    return {
        "code": booking.code or f"#{booking.id}",
        "borrower": booking.borrower.get_username(),
        "borrower_name": booking.borrower.get_full_name(),
        "status": booking.status,
        "start": period.lower.isoformat() if period and period.lower else None,
        "end": period.upper.isoformat() if period and period.upper else None,
    }


class LendingOverviewView(APIView):
    """GET /api/manage/borrowers/?pool=

    The Pool → Product → Resource tree (with per-resource booking counts) for
    the pools the requester manages (admins: all, optionally one via ``pool``).
    A resource's borrowings are fetched separately and paginated.
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request):
        _pools, pool_ids = _stats_pools(request)
        return Response({"pools": lending_tree(pool_ids)})


class ResourceBorrowersView(APIView):
    """GET /api/manage/borrowers/resources/<id>/?page=

    Paginated borrowing history (non-cart, recent first) of one resource, if it
    belongs to a pool the requester manages.
    """

    permission_classes = [IsLenderOrAdmin]

    def get(self, request, resource_id):
        _pools, pool_ids = _stats_pools(request)
        resource = get_object_or_404(Resource, pk=resource_id)
        if resource.resource_pool_id not in set(pool_ids):
            raise Http404("No such resource.")
        queryset = (
            BookingItem.objects.filter(resource=resource)
            .exclude(booking__status=Booking.Status.CART)
            .select_related("booking__borrower")
            .order_by("-booking__created_at", "-id")
        )
        paginator = BorrowerPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([_booking_row(item) for item in page])
