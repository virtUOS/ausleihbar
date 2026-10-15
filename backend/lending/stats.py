"""Lending statistics overview (#96).

Counts are based on actual handouts: a booking item is a *loan* once it has a
``handed_out_at``. Neither ``is_active`` (false once returned) nor the booking
status is used — a handout is a real loan even if the reservation is later
cancelled (e.g. a multi-period reservation whose remaining appointments are
dropped). Borrowers are counted by id, so anonymized accounts (kept in place)
still count; no names are ever returned.
"""

from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import Upper
from django.utils import timezone

from catalog.models import Product, ResourcePool

from .models import BookingItem

_POOL = "resource__resource_pool_id"
_DAILY = Q(resource__product__lending_type=Product.LendingType.DAYS)
_HOURLY = Q(resource__product__lending_type=Product.LendingType.HOURS)
_RETURNED = Q(returned_at__isnull=False)
# Late = returned after the booked (exclusive) end; for day items that is the
# next midnight, so a return on the last booked day is on time.
_LATE = Q(returned_at__gt=Upper("period"))

_DELAY = ExpressionWrapper(F("returned_at") - Upper("period"), output_field=DurationField())
_DURATION = ExpressionWrapper(
    F("returned_at") - F("handed_out_at"), output_field=DurationField()
)

_PERIOD_AGGREGATES = {
    "loans": Count("id"),
    "users_in_period": Count("booking__borrower_id", distinct=True),
    "returned": Count("id", filter=_RETURNED),
    "late_returns": Count("id", filter=_LATE),
    "avg_delay_days": Avg(_DELAY, filter=_LATE & _DAILY),
    "avg_delay_hours": Avg(_DELAY, filter=_LATE & _HOURLY),
    "avg_duration_days": Avg(_DURATION, filter=_RETURNED & _DAILY),
    "avg_duration_hours": Avg(_DURATION, filter=_RETURNED & _HOURLY),
}

_DAY = timedelta(days=1).total_seconds()
_HOUR = timedelta(hours=1).total_seconds()


def _in(value, unit):
    return None if value is None else round(value.total_seconds() / unit, 1)


def _figures(period_row, scope_row):
    """Shape one row (totals or a pool) from its period and scope aggregates."""
    period_row = period_row or {}
    scope_row = scope_row or {}
    returned = period_row.get("returned") or 0
    late = period_row.get("late_returns") or 0
    return {
        "loans": period_row.get("loans") or 0,
        "users_in_period": period_row.get("users_in_period") or 0,
        "users_total": scope_row.get("users_total") or 0,
        "late_returns": late,
        "returned": returned,
        "late_share": round(late / returned, 3) if returned else None,
        "avg_delay_days": _in(period_row.get("avg_delay_days"), _DAY),
        "avg_delay_hours": _in(period_row.get("avg_delay_hours"), _HOUR),
        "overdue_now": scope_row.get("overdue_now") or 0,
        "avg_duration_days": _in(period_row.get("avg_duration_days"), _DAY),
        "avg_duration_hours": _in(period_row.get("avg_duration_hours"), _HOUR),
    }


def stats_overview(pool_ids, start, end, now=None):
    """Overview figures for the loans handed out in [start, end) in ``pool_ids``.

    Returns ``{"totals": {...}, "pools": [{"id", "name", "accent_color", ...}]}``.
    ``users_total`` and ``overdue_now`` are not limited to the period (all
    handouts in scope / the current state). Four aggregate queries in total
    (totals + grouped per pool, each for the period and the whole scope).
    """
    now = now or timezone.now()
    scope = BookingItem.objects.filter(
        resource__resource_pool_id__in=pool_ids, handed_out_at__isnull=False
    ).order_by()
    in_period = scope.filter(handed_out_at__gte=start, handed_out_at__lt=end)
    scope_aggregates = {
        "users_total": Count("booking__borrower_id", distinct=True),
        "overdue_now": Count(
            "id", filter=Q(returned_at__isnull=True, period__endswith__lt=now)
        ),
    }

    totals = _figures(
        in_period.aggregate(**_PERIOD_AGGREGATES), scope.aggregate(**scope_aggregates)
    )
    period_by_pool = {
        row[_POOL]: row
        for row in in_period.values(_POOL).annotate(**_PERIOD_AGGREGATES)
    }
    scope_by_pool = {
        row[_POOL]: row for row in scope.values(_POOL).annotate(**scope_aggregates)
    }
    pools = [
        {
            "id": pool.id,
            "name": pool.name,
            "accent_color": pool.accent_color,
            **_figures(period_by_pool.get(pool.id), scope_by_pool.get(pool.id)),
        }
        for pool in ResourcePool.objects.filter(id__in=pool_ids).order_by("name")
    ]
    return {"totals": totals, "pools": pools}
