# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""URL routes for the catalog API."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    ExportDataView,
    FavoriteDetailView,
    FavoritesView,
    FooterPagesView,
    ImportDataView,
    ManageCategoryViewSet,
    ManageDefectTicketViewSet,
    ManageInventoryViewSet,
    ManagePageViewSet,
    ManageProductSetViewSet,
    ManageProductTypeViewSet,
    ManageProductViewSet,
    ManageResourcePoolViewSet,
    ManageSectionViewSet,
    PageDetailView,
    ProductViewSet,
    ResourceByQrView,
    SearchView,
    TranslateView,
    BrandingView,
    NotificationSettingView,
    SectionViewSet,
    ShopPoolDetailView,
    ShopPoolsView,
    WelcomeLogoView,
    SetViewSet,
    ShopSettingView,
    WelcomeSettingView,
    WelcomeView,
)
from .trash import TrashItemView, TrashRestoreView, TrashView

router = DefaultRouter()
router.register("sections", SectionViewSet, basename="section")
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("sets", SetViewSet, basename="set")
router.register("manage/pools", ManageResourcePoolViewSet, basename="manage-pool")
router.register(
    "manage/defect-tickets",
    ManageDefectTicketViewSet,
    basename="manage-defect-ticket",
)
router.register(
    "manage/product-types", ManageProductTypeViewSet, basename="manage-product-type"
)
router.register("manage/products", ManageProductViewSet, basename="manage-product")
router.register(
    "manage/categories", ManageCategoryViewSet, basename="manage-category"
)
router.register("manage/sections", ManageSectionViewSet, basename="manage-section")
router.register(
    "manage/product-sets", ManageProductSetViewSet, basename="manage-product-set"
)
router.register(
    "manage/inventory", ManageInventoryViewSet, basename="manage-inventory"
)
router.register("manage/pages", ManagePageViewSet, basename="manage-page")

urlpatterns = [
    path("resources/by-qr/<str:qr_id>/", ResourceByQrView.as_view(), name="resource-by-qr"),
    path("search/", SearchView.as_view(), name="search"),
    path("favorites/", FavoritesView.as_view(), name="favorites"),
    path(
        "favorites/<int:product_id>/",
        FavoriteDetailView.as_view(),
        name="favorite-detail",
    ),
    path("manage/translate/", TranslateView.as_view(), name="manage-translate"),
    path("manage/export/", ExportDataView.as_view(), name="manage-export"),
    path("manage/import/", ImportDataView.as_view(), name="manage-import"),
    path("pools/", ShopPoolsView.as_view(), name="shop-pools"),
    path("pools/<int:pk>/", ShopPoolDetailView.as_view(), name="shop-pool-detail"),
    path("branding/", BrandingView.as_view(), name="branding"),
    path("pages/", FooterPagesView.as_view(), name="footer-pages"),
    path("pages/<slug:slug>/", PageDetailView.as_view(), name="page-detail"),
    path("welcome/", WelcomeView.as_view(), name="welcome"),
    path("manage/welcome-setting/", WelcomeSettingView.as_view(), name="welcome-setting"),
    path("manage/shop-setting/", ShopSettingView.as_view(), name="shop-setting"),
    path(
        "manage/notification-setting/",
        NotificationSettingView.as_view(),
        name="notification-setting",
    ),
    path(
        "manage/welcome-setting/logo/",
        WelcomeLogoView.as_view(),
        name="welcome-logo",
    ),
    path("manage/trash/", TrashView.as_view(), name="trash"),
    path(
        "manage/trash/<str:type>/<int:pk>/restore/",
        TrashRestoreView.as_view(),
        name="trash-restore",
    ),
    path(
        "manage/trash/<str:type>/<int:pk>/",
        TrashItemView.as_view(),
        name="trash-item",
    ),
] + router.urls
