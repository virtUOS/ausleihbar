# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""URL routes for the lending API."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet,
    BorrowerSearchView,
    BulkAvailabilityView,
    CartItemsView,
    CartItemView,
    CartSetView,
    CartSettingView,
    CartSubmitView,
    CartView,
    HolidayImportView,
    WalkinContextView,
    WalkinCreateView,
    WalkinProductCalendarView,
    WalkinProductHourlyCalendarView,
    WalkinProductHourlyView,
    WalkinProductsView,
    WalkinResourcesView,
    HolidaySettingView,
    LendingOverviewView,
    ResourceBorrowersView,
    ManageBlockViewSet,
    ManageBookingViewSet,
    ManageResourceViewSet,
    ProductAvailabilityCalendarView,
    ProductAvailabilityView,
    ProductHourlyAvailabilityView,
    ProductPoolAvailabilityView,
    ProductHourlyCalendarView,
    CapacityStatsView,
    DefectStatsView,
    ProductStatsView,
    ProductTimeseriesView,
    SetAvailabilityCalendarView,
    SetAvailabilityView,
    SetHourlyAvailabilityView,
    SetHourlyCalendarView,
)

router = DefaultRouter()
router.register("bookings", BookingViewSet, basename="booking")
router.register("manage/bookings", ManageBookingViewSet, basename="manage-booking")
router.register("manage/resources", ManageResourceViewSet, basename="manage-resource")
router.register("manage/blocks", ManageBlockViewSet, basename="manage-block")

urlpatterns = [
    path("availability/", BulkAvailabilityView.as_view(), name="bulk-availability"),
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/", CartItemsView.as_view(), name="cart-items"),
    path("cart/items/<int:item_id>/", CartItemView.as_view(), name="cart-item"),
    path("cart/sets/", CartSetView.as_view(), name="cart-set"),
    path("cart/submit/", CartSubmitView.as_view(), name="cart-submit"),
    path(
        "manage/walkin/context/",
        WalkinContextView.as_view(),
        name="walkin-context",
    ),
    path(
        "manage/walkin/products/",
        WalkinProductsView.as_view(),
        name="walkin-products",
    ),
    path(
        "manage/walkin/availability/calendar/",
        WalkinProductCalendarView.as_view(),
        name="walkin-availability-calendar",
    ),
    path(
        "manage/walkin/availability/hours/calendar/",
        WalkinProductHourlyCalendarView.as_view(),
        name="walkin-availability-hours-calendar",
    ),
    path(
        "manage/walkin/availability/hours/",
        WalkinProductHourlyView.as_view(),
        name="walkin-availability-hours",
    ),
    path(
        "manage/walkin/resources/",
        WalkinResourcesView.as_view(),
        name="walkin-resources",
    ),
    path("manage/walkin/", WalkinCreateView.as_view(), name="walkin-create"),
    path(
        "manage/borrower-search/",
        BorrowerSearchView.as_view(),
        name="borrower-search",
    ),
    path(
        "sets/<int:set_id>/availability/calendar/",
        SetAvailabilityCalendarView.as_view(),
        name="set-availability-calendar",
    ),
    path(
        "sets/<int:set_id>/availability/hours/calendar/",
        SetHourlyCalendarView.as_view(),
        name="set-availability-hours-calendar",
    ),
    path(
        "sets/<int:set_id>/availability/hours/",
        SetHourlyAvailabilityView.as_view(),
        name="set-availability-hours",
    ),
    path(
        "sets/<int:set_id>/availability/",
        SetAvailabilityView.as_view(),
        name="set-availability",
    ),
    path(
        "manage/holidays/import/",
        HolidayImportView.as_view(),
        name="holiday-import",
    ),
    path(
        "manage/holiday-setting/",
        HolidaySettingView.as_view(),
        name="holiday-setting",
    ),
    path(
        "manage/cart-setting/",
        CartSettingView.as_view(),
        name="cart-setting",
    ),
    path(
        "manage/borrowers/",
        LendingOverviewView.as_view(),
        name="lending-overview",
    ),
    path(
        "manage/borrowers/resources/<int:resource_id>/",
        ResourceBorrowersView.as_view(),
        name="resource-borrowers",
    ),
    path(
        "manage/stats/products/",
        ProductStatsView.as_view(),
        name="product-stats",
    ),
    path(
        "manage/stats/defects/",
        DefectStatsView.as_view(),
        name="defect-stats",
    ),
    path(
        "manage/stats/capacity/",
        CapacityStatsView.as_view(),
        name="capacity-stats",
    ),
    path(
        "manage/stats/products/<int:product_id>/timeseries/",
        ProductTimeseriesView.as_view(),
        name="product-timeseries",
    ),
    path(
        "products/<int:product_id>/availability/calendar/",
        ProductAvailabilityCalendarView.as_view(),
        name="product-availability-calendar",
    ),
    path(
        "products/<int:product_id>/availability/hours/calendar/",
        ProductHourlyCalendarView.as_view(),
        name="product-availability-hours-calendar",
    ),
    path(
        "products/<int:product_id>/availability/hours/",
        ProductHourlyAvailabilityView.as_view(),
        name="product-availability-hours",
    ),
    path(
        "products/<int:product_id>/availability/pools/",
        ProductPoolAvailabilityView.as_view(),
        name="product-availability-pools",
    ),
    path(
        "products/<int:product_id>/availability/",
        ProductAvailabilityView.as_view(),
        name="product-availability",
    ),
] + router.urls
