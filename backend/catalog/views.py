# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Read-only catalog API for the borrower-facing shop, plus admin management."""
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.eligibility import eligible_pool_ids, visible_products
from accounts.models import PoolMembership
from accounts.permissions import IsAdmin, IsLenderOrAdmin
from basicbar_integrations import ai, translation_service
from basicbar_integrations.views import TranslateView as BaseTranslateView
from common.limits import check_create_allowed
from .ai_prompts import (
    RESERVED_ATTRIBUTE_KEYS,
    build_attribute_prompt,
    build_product_extraction_prompt,
)
from . import rich_images
from .pdf_extract import PdfTextError, extract_pdf_text
from .serializers import _normalize_attr_value, normalize_attribute


def _is_admin(user):
    """Admins (staff/superusers) are unscoped; lenders are limited to their pools."""
    return bool(user.is_staff or user.is_superuser)


def _managed_pool_ids(user):
    """Ids of the pools a lender manages (via PoolMembership)."""
    return set(user.pool_memberships.values_list("resource_pool_id", flat=True))


from .navigation import CategoryTree, daily_first
from .models import (
    Category,
    Favorite,
    NotificationSetting,
    Page,
    Product,
    ProductImage,
    ProductSet,
    ProductType,
    Resource,
    ResourcePool,
    Section,
    ShopSetting,
    TrashSetting,
    WelcomeSetting,
)
from .serializers import (
    NotificationSettingSerializer,
    PageDetailSerializer,
    PageLinkSerializer,
    PageManageSerializer,
    PoolLenderSerializer,
    PoolLendersUpdateSerializer,
    ProductBriefSerializer,
    ProductImageSerializer,
    ProductDetailSerializer,
    ProductManageSerializer,
    ProductSetManageSerializer,
    ProductTypeSerializer,
    CategoryManageSerializer,
    category_group,
    shop_navigation,
    SetBriefSerializer,
    SetDetailSerializer,
    ResourceDetailManageSerializer,
    ResourceManageSerializer,
    PoolCardSerializer,
    PoolDetailSerializer,
    PoolDefectTicketSerializer,
    ResourcePoolSerializer,
    SectionDetailSerializer,
    SectionListSerializer,
    SectionManageSerializer,
    ShopSettingSerializer,
    TrashSettingSerializer,
    WelcomeSettingSerializer,
)


def _narrow_to_admin_scope(request, queryset, field="id"):
    """Narrow a lending-area list to an admin's own pools ("My pools").

    A view filter only (``lending.scope``): no-op for lenders (already scoped),
    admins without lender assignments and the ``X-Pool-Scope: all`` support
    view. Never use it for authorization checks.
    """
    from lending.scope import admin_scope_pool_ids

    scope = admin_scope_pool_ids(request)
    if scope is None:
        return queryset
    return queryset.filter(**{f"{field}__in": scope})


class SectionViewSet(viewsets.ReadOnlyModelViewSet):
    """Sections ("Sparten") — the top-level grouping shown on the start page.

    Both list and detail navigate by categories (#78); counts and groups come
    from one per-request ``ShopNavigation`` (no per-section queries, #63).
    """

    queryset = Section.objects.all()

    def get_queryset(self):
        if self.action == "retrieve":
            return self.queryset.prefetch_related("categories", "sets__products")
        return self.queryset.prefetch_related("categories")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SectionDetailSerializer
        return SectionListSerializer


class CategoryViewSet(viewsets.GenericViewSet):
    """GET /api/categories/<id>/ — a shop category page (#78).

    The category with ``ancestors`` (root → parent, for breadcrumbs), the
    ``sections`` of its root category, its ordered ``children`` (each with the
    visible product count of its subtree) and the visible products of its
    whole subtree in shop order (own ``product_order`` first, then the
    subcategories in order, deduplicated; daily before hourly). 404 for a
    trashed category or one below a trashed parent. No list route.
    """

    permission_classes = []

    def retrieve(self, request, pk=None):
        context = {"request": request}
        nav = shop_navigation(context)
        try:
            category = nav.tree.nodes[int(pk)]
        except (KeyError, TypeError, ValueError):
            return Response({"detail": "Not found."}, status=404)
        ancestors = nav.tree.ancestors(category.id)
        root = ancestors[0] if ancestors else category
        nav.preload([category.id])
        data = category_group(category, context, nav)
        data["parent"] = category.parent_id
        data["ancestors"] = [{"id": c.id, "name": c.name} for c in ancestors]
        data["sections"] = [
            {"id": s.id, "title": s.title}
            for s in root.sections.order_by("position", "title")
        ]
        data["children"] = [
            category_group(nav.tree.nodes[cid], context, nav, with_products=False)
            for cid in nav.tree.children[category.id]
        ]
        return Response(data)


class SearchView(APIView):
    """GET /api/search/?q= — shop search across products, categories and
    sections.

    Products match by title/description (visibility-filtered, as on the product
    list). Categories (any depth) and sections match by their own name and are
    returned with their content (categories → the visible products of their
    subtree plus their ``path`` of ancestors; sections → their top-level
    categories with products), so searching a grouping's name surfaces it and
    what's inside it. Categories with no visible product are left out (top
    level and inside sections), so names used only in restricted pools don't
    leak.
    """

    permission_classes = []

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response({"sections": [], "categories": [], "products": []})
        context = {"request": request}
        nav = shop_navigation(context)
        sections = list(
            Section.objects.filter(title__icontains=query)
            .prefetch_related("categories", "sets__products")
            .order_by("position", "title")
        )
        matched = sorted(
            (
                cid for cid in Category.objects.filter(
                    name__icontains=query
                ).values_list("id", flat=True)
                if cid in nav.tree and nav.count(cid) > 0
            ),
            key=nav.tree.index,
        )
        products = visible_products(
            Product.objects.select_related("product_type")
            .prefetch_related("images")
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .distinct(),
            request.user,
            pool_ids=context["_eligible_pool_ids"],
        )
        # One product query for every matched section and category (#63).
        roots = [cid for section in sections for cid in nav.section_roots(section)]
        nav.preload(roots + matched)
        section_data = SectionDetailSerializer(sections, many=True, context=context).data
        for section in section_data:
            section["categories"] = [
                g for g in section["categories"] if g["product_count"] > 0
            ]
        categories = []
        for cid in matched:
            group = category_group(nav.tree.nodes[cid], context, nav)
            group["path"] = [
                {"id": c.id, "name": c.name} for c in nav.tree.ancestors(cid)
            ]
            categories.append(group)
        return Response(
            {
                "sections": section_data,
                "categories": categories,
                "products": ProductBriefSerializer(
                    products, many=True, context=context
                ).data,
            }
        )


class TranslateView(BaseTranslateView):
    """POST /api/manage/translate/ — machine-translate a snippet for the editor.

    The canonical basicbar contract (``{text, source, target, format?}`` →
    ``{translated}``), here restricted to lenders/admins because only they
    author content.
    """

    permission_classes = [IsLenderOrAdmin]


class ExportDataView(APIView):
    """GET /api/manage/export/ — download the catalog data set as a ZIP.

    ``?pool=<id>`` exports a single pool (its resources + the products/types/
    images they need); otherwise the whole system. Admin only.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        from . import transfer

        pool_id = request.query_params.get("pool")
        if pool_id:
            pool = get_object_or_404(ResourcePool, pk=pool_id)
            data = transfer.build_archive("pool", pool=pool)
            name = f"ausleihbar-pool-{pool.pool_id}.zip"
        else:
            data = transfer.build_archive("full")
            name = "ausleihbar-export.zip"
        response = HttpResponse(data, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class ImportDataView(APIView):
    """POST /api/manage/import/ — merge an export archive into the database.

    Multipart: ``file`` (the ZIP) and optional ``dry_run``. Returns a summary of
    created/updated counts. Existing rows are matched by natural key and
    updated; missing ones are created. Admin only.
    """

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        from . import transfer

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file uploaded."}, status=400)
        dry_run = str(request.data.get("dry_run", "")).lower() in ("1", "true", "on")
        try:
            summary = transfer.import_archive(upload, dry_run=dry_run)
        except transfer.ImportError_ as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(summary)


class ResourceByQrView(APIView):
    """GET /api/resources/by-qr/<qr_id>/ — resolve a device QR to its product.

    Public: a device QR sticker encodes ``<shop>/r/<qr_id>``; a normal QR reader
    lands on this so the SPA can redirect to the product page (manuals etc.).
    """

    permission_classes = []

    def get(self, request, qr_id):
        resource = get_object_or_404(
            Resource.objects.select_related("product"), qr_code_id=qr_id
        )
        return Response(
            {
                "product": resource.product_id,
                "product_title": resource.product.title,
                "inventory_number": resource.inventory_number,
            }
        )


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Products with filters ``?category=`` (subtree), ``?section=`` (its
    categories' subtrees), ``?product_type=``, ``?pool=`` and ``?search=``."""

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductBriefSerializer

    def get_queryset(self):
        queryset = Product.objects.select_related("product_type").prefetch_related("images").all()
        params = self.request.query_params
        for key in ("product_type", "category", "section"):
            value = params.get(key)
            if value and not value.isdigit():
                return queryset.none()
        if params.get("product_type"):
            queryset = queryset.filter(product_type_id=params["product_type"])
        # Category navigation (#78): ?category= is the category's subtree,
        # ?section= the subtrees of the section's top-level categories.
        if params.get("category") or params.get("section"):
            tree = CategoryTree()
            if params.get("category"):
                ids = tree.subtree(int(params["category"]))
                if not ids:
                    return queryset.none()
                queryset = queryset.filter(categories__in=ids)
            if params.get("section"):
                roots = Category.objects.filter(
                    sections=params["section"], parent__isnull=True
                ).values_list("id", flat=True)
                queryset = queryset.filter(
                    categories__in=tree.subtree_of_all(roots)
                )
        if params.get("pool"):
            queryset = queryset.filter(resources__resource_pool_id=params["pool"])
        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        return visible_products(queryset.distinct(), self.request.user)

    @action(detail=False, methods=["get"])
    def featured(self, request):
        """Featured rows for the start page: most popular and newest products.

        Both are limited to products the requester may see (concept §3.4).
        Popularity is the number of real (non-cart, non-cancelled) booking items
        across a product's resources.
        """
        setting = ShopSetting.load()
        visible = visible_products(
            Product.objects.select_related("product_type").prefetch_related("images"), request.user
        )
        active_statuses = ["pending", "confirmed", "handed_out", "returned"]
        popular = (
            visible.annotate(
                lend_count=Count(
                    "resources__booking_items",
                    filter=Q(
                        resources__booking_items__booking__status__in=active_statuses
                    ),
                )
            )
            .filter(lend_count__gt=0)
            .order_by("-lend_count", "title")[:8]
            if setting.show_popular
            else []
        )
        newest = (
            visible.order_by("-created_at", "-id")[:8]
            if setting.show_new_arrivals
            else []
        )
        context = self.get_serializer_context()
        return Response(
            {
                "popular": ProductBriefSerializer(popular, many=True, context=context).data,
                "newest": ProductBriefSerializer(newest, many=True, context=context).data,
            }
        )


class ImageUploadMixin:
    """Adds an ``image`` sub-resource for uploading/clearing the model image.

    ``POST   .../<id>/image/``  (multipart, field ``image``) stores the file.
    ``DELETE .../<id>/image/``  removes the current image.

    The image field is read-only in the JSON serializer; this is the only way
    to change it. Returns the full serialized object so the client can refresh.
    """

    @action(
        detail=True,
        methods=["post", "delete"],
        url_path="image",
        parser_classes=[MultiPartParser, FormParser],
    )
    def image(self, request, *args, **kwargs):
        obj = self.get_object()
        if request.method == "DELETE":
            if obj.image:
                obj.image.delete(save=True)
            return Response(self.get_serializer(obj).data)

        upload = request.FILES.get("image")
        if upload is None:
            return Response({"detail": "No image file provided."}, status=400)
        if upload.content_type and not upload.content_type.startswith("image/"):
            return Response({"detail": "Uploaded file must be an image."}, status=400)
        obj.image.save(upload.name, upload, save=True)
        return Response(self.get_serializer(obj).data)


class SetViewSet(viewsets.ReadOnlyModelViewSet):
    """Borrower-facing sets: list (brief) and detail with products + pools."""

    queryset = ProductSet.objects.prefetch_related("products__product_type").all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SetDetailSerializer
        return SetBriefSerializer


class PositionOrderedMixin:
    """Adds manual ordering: new rows append at the end, plus a reorder action.

    The model must have an integer ordering field named by ``position_field``
    (default ``position``). ``POST <list>/reorder/`` accepts ``{"order": [id,
    ...]}`` listing every id exactly once and rewrites that field to the given
    order. Used by the admin drag-and-drop / arrow controls.
    """

    position_field = "position"

    def reorder_scope(self, request):
        """The rows one reorder call covers (every id must be listed once).
        Override to reorder within a subset, e.g. among siblings."""
        return self.get_queryset().model.objects.all()

    def perform_create(self, serializer):
        model = self.get_queryset().model
        field = self.position_field
        last = model.objects.order_by(f"-{field}").values_list(
            field, flat=True
        ).first()
        serializer.save(**{field: (last + 1) if last is not None else 0})

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        order = request.data.get("order")
        if not isinstance(order, list):
            return Response({"detail": "Provide an 'order' list of ids."}, status=400)
        try:
            ids = [int(value) for value in order]
        except (TypeError, ValueError):
            return Response({"detail": "Ids must be integers."}, status=400)
        model = self.get_queryset().model
        try:
            scope = self.reorder_scope(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        existing = set(scope.values_list("id", flat=True))
        if set(ids) != existing or len(ids) != len(existing):
            return Response(
                {"detail": "'order' must list every id exactly once."}, status=400
            )
        field = self.position_field
        by_id = model.objects.in_bulk(ids)
        updated = []
        for position, obj_id in enumerate(ids):
            obj = by_id[obj_id]
            setattr(obj, field, position)
            updated.append(obj)
        model.objects.bulk_update(updated, [field])
        return Response({"status": "ok", "count": len(updated)})


class ManageResourcePoolViewSet(PositionOrderedMixin, ImageUploadMixin, viewsets.ModelViewSet):
    """Resource pools (the lending locations).

    Admins have full CRUD. Lenders may only *read* — and only the pools they
    manage — so the pool pickers on the lender-facing inventory / QR-label pages
    work without exposing other pools or letting a lender edit a location.
    """

    queryset = ResourcePool.objects.all()
    serializer_class = ResourcePoolSerializer
    filter_backends = [SearchFilter]
    search_fields = ["name", "pool_id"]

    def get_permissions(self):
        if self.action == "lenders":
            return [IsAdmin()]
        if self.request.method in permissions.SAFE_METHODS:
            return [IsLenderOrAdmin()]
        return [IsAdmin()]

    def _lenders(self, pool):
        users = get_user_model().objects.filter(
            pool_memberships__resource_pool=pool,
            pool_memberships__role=PoolMembership.Role.MANAGER,
        )
        return PoolLenderSerializer(
            users.order_by("last_name", "first_name", "username"), many=True
        ).data

    @action(detail=True, methods=["get", "put"], url_path="lenders")
    def lenders(self, request, pk=None):
        """List (GET) or sync (PUT) the pool's lenders. Admin only."""
        pool = self.get_object()
        if request.method == "GET":
            return Response(self._lenders(pool))

        serializer = PoolLendersUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wanted = set(serializer.validated_data["user_ids"])

        with transaction.atomic():
            users = {
                u.id: u for u in get_user_model().objects.filter(pk__in=wanted)
            }
            missing = wanted - users.keys()
            if missing:
                return Response(
                    {"detail": f"Unknown user id(s): {sorted(missing)}."},
                    status=400,
                )
            # Deactivated users who are already lenders stay; only newly
            # added inactive users are rejected.
            existing = set(
                PoolMembership.objects.filter(
                    resource_pool=pool, role=PoolMembership.Role.MANAGER
                ).values_list("user_id", flat=True)
            )
            inactive = sorted(
                uid
                for uid, u in users.items()
                if not u.is_active and uid not in existing
            )
            if inactive:
                return Response(
                    {"detail": f"Inactive user id(s): {inactive}."}, status=400
                )
            PoolMembership.objects.filter(
                resource_pool=pool, role=PoolMembership.Role.MANAGER
            ).exclude(user_id__in=wanted).delete()
            for user_id in wanted:
                PoolMembership.objects.get_or_create(
                    user_id=user_id,
                    resource_pool=pool,
                    role=PoolMembership.Role.MANAGER,
                )
        return Response(self._lenders(pool))

    def get_queryset(self):
        queryset = ResourcePool.objects.all()
        if not _is_admin(self.request.user):
            queryset = queryset.filter(id__in=_managed_pool_ids(self.request.user))
            return queryset.order_by("position", "name")
        # Lending-area pool pickers opt in with ?scope=lending to get an admin's
        # own pools by default; the admin area's pool management stays complete.
        if (
            self.action == "list"
            and self.request.query_params.get("scope") == "lending"
        ):
            queryset = _narrow_to_admin_scope(self.request, queryset)
        return queryset.order_by("position", "name")

    def destroy(self, request, *args, **kwargs):
        pool = self.get_object()
        if pool.resources.exists():
            return Response(
                {"detail": "Cannot delete a pool that still has resources."},
                status=400,
            )
        pool.soft_delete(request.user)
        return Response(status=204)


class ManageDefectTicketViewSet(viewsets.ModelViewSet):
    """Per-pool defect → GitLab issue settings.

    Lenders manage this for the pools they manage (admins: all). Only the
    integration fields are editable here — full pool CRUD stays in the admin
    pool management. List/retrieve + patch only; never create or delete.
    """

    serializer_class = PoolDefectTicketSerializer
    permission_classes = [IsLenderOrAdmin]
    pagination_class = None
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        queryset = ResourcePool.objects.all().order_by("name")
        if not _is_admin(self.request.user):
            queryset = queryset.filter(id__in=_managed_pool_ids(self.request.user))
        elif self.action == "list":
            queryset = _narrow_to_admin_scope(self.request, queryset)
        return queryset


class ManageProductTypeViewSet(
    PositionOrderedMixin, ImageUploadMixin, viewsets.ModelViewSet
):
    """Admin CRUD for product types — templates with a dynamic attribute schema
    and the shop's grouping level below sections (#20). New types are appended
    (``position``); ``reorder`` and ``image`` actions as for sections."""

    queryset = ProductType.objects.prefetch_related("products", "sections").all()
    serializer_class = ProductTypeSerializer
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_permissions(self):
        # Lenders need to read the types for the product form's type select;
        # every write (incl. reorder, image, suggest-attributes) stays admin-only.
        if self.action in ("list", "retrieve"):
            return [IsLenderOrAdmin()]
        return [IsAdmin()]

    def destroy(self, request, *args, **kwargs):
        product_type = self.get_object()
        if product_type.products.exists():
            return Response(
                {"detail": "Cannot delete a product type that still has products."},
                status=400,
            )
        product_type.soft_delete(request.user)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="suggest-attributes")
    def suggest_attributes(self, request):
        """Propose attribute-schema entries for a product type (AI feature),
        using its name/description plus optional extra hints. AI-optional;
        returns 503 when disabled."""
        if not ai.is_enabled():
            return Response({"detail": "AI is not configured."}, status=503)
        name = str(request.data.get("name", "")).strip()
        description = str(request.data.get("description", "")).strip()
        hints = str(request.data.get("hints", "")).strip()
        if not (name or description or hints):
            return Response(
                {"detail": "Provide a product type name, description or hints."},
                status=400,
            )
        if any(len(value) > 2000 for value in (name, description, hints)):
            return Response({"detail": "Input is too long."}, status=400)
        existing_keys = request.data.get("existing_keys") or []
        if not isinstance(existing_keys, list):
            existing_keys = []
        existing = {
            str(k).strip()
            for k in existing_keys
            if str(k).strip()
        }
        system, user = build_attribute_prompt(name, description, hints, existing)
        try:
            payload = ai.chat_json(system, user)
        except ai.AIError:
            return Response({"detail": "AI request failed."}, status=502)
        raw = payload.get("attributes", []) if isinstance(payload, dict) else []
        if not isinstance(raw, list):
            raw = []
        attributes = []
        # Seed with keys the system already tracks per unit/product, so a
        # suggestion that duplicates a built-in field (e.g. inventory_number)
        # is dropped even if the model ignores the prompt instruction.
        seen = set(existing) | RESERVED_ATTRIBUTE_KEYS
        for attr in raw:
            try:
                entry = normalize_attribute(attr)
            except (ValueError, TypeError):
                continue
            if entry["key"] in seen:
                continue
            seen.add(entry["key"])
            attributes.append(entry)
            if len(attributes) >= 12:
                break
        return Response({"attributes": attributes})

    @action(detail=True, methods=["get"], url_path="attribute-usage")
    def attribute_usage(self, request, pk=None):
        """Per-attribute count of this type's products that carry a non-empty,
        non-default value — to warn before removing a schema attribute (§5.2).
        """
        product_type = self.get_object()
        schema = product_type.attribute_schema or []
        defaults = {a["key"]: a.get("default") for a in schema if a.get("key")}
        counts = {key: 0 for key in defaults}
        empty = (None, "", [], {})
        for attrs in product_type.products.values_list("attributes", flat=True):
            attrs = attrs or {}
            for key, default in defaults.items():
                value = attrs.get(key)
                if value in empty or value == default:
                    continue
                counts[key] += 1
        return Response(counts)


class ManageProductSetViewSet(viewsets.ModelViewSet):
    """Lender/admin CRUD for sets — products sensibly lent together (§5.5).

    Sets are part of the shared catalog (not pool-bound), so any lender may
    manage them, like products.
    """

    queryset = ProductSet.objects.prefetch_related("products").all()
    serializer_class = ProductSetManageSerializer
    permission_classes = [IsLenderOrAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete(request.user)
        return Response(status=204)


class ManageSectionViewSet(
    PositionOrderedMixin, ImageUploadMixin, viewsets.ModelViewSet
):
    """Admin CRUD for sections ("Sparten") — groupings of top-level
    categories (#78) and sets."""

    queryset = Section.objects.prefetch_related(
        "categories", "product_types", "sets"
    ).all()
    serializer_class = SectionManageSerializer
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["title"]

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete(request.user)
        return Response(status=204)


class ManageCategoryViewSet(
    PositionOrderedMixin, ImageUploadMixin, viewsets.ModelViewSet
):
    """Admin CRUD for categories — the shop navigation tree (#78, ADR-0011).

    The list is unpaginated and flat, in tree order (pre-order; siblings by
    ``position``, then name), each row with ``parent``, ``depth`` and
    ``path``; ``?search=`` filters by name and keeps the tree order. New
    categories are appended among their siblings, a moved one at the end of
    its new siblings. ``reorder`` takes ``{"parent": id|null, "order": [...]}``
    and must list every live child of that parent once. ``destroy`` is refused
    (400) while the category has live children; products and sections keep
    their assignment until the category is purged from the trash.
    Lenders may read (product form); every write is admin-only, as for
    sections and product types.
    """

    queryset = Category.objects.prefetch_related("products", "sections", "children")
    serializer_class = CategoryManageSerializer
    pagination_class = None
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsLenderOrAdmin()]
        return [IsAdmin()]

    def list(self, request, *args, **kwargs):
        rows = list(self.filter_queryset(self.get_queryset()))
        tree = CategoryTree()
        far = len(tree.order)
        rows.sort(key=lambda c: (tree.index(c.id) if c.id in tree else far, c.id))
        context = {**self.get_serializer_context(), "category_tree": tree}
        return Response(self.get_serializer_class()(rows, many=True, context=context).data)

    def _next_position(self, parent):
        last = (
            Category.objects.filter(parent=parent)
            .order_by("-position")
            .values_list("position", flat=True)
            .first()
        )
        return (last + 1) if last is not None else 0

    def perform_create(self, serializer):
        parent = serializer.validated_data.get("parent")
        serializer.save(position=self._next_position(parent))

    def perform_update(self, serializer):
        instance = serializer.instance
        if "parent" in serializer.validated_data:
            parent = serializer.validated_data["parent"]
            if (parent.pk if parent else None) != instance.parent_id:
                serializer.save(position=self._next_position(parent))
                return
        serializer.save()

    def reorder_scope(self, request):
        parent = request.data.get("parent")
        if parent in (None, ""):
            return Category.objects.filter(parent__isnull=True)
        try:
            return Category.objects.filter(parent_id=int(parent))
        except (TypeError, ValueError):
            raise ValueError("'parent' must be a category id or null.")

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.children.exists():
            return Response(
                {"detail": "Cannot delete a category that still has subcategories."},
                status=400,
            )
        category.soft_delete(request.user)
        return Response(status=204)


def _normalize_extraction(payload, schema):
    """Shape a model reply into {title:{de,en}, description:{de,en},
    short_description:{de,en}, attributes:{key:value}} — attributes limited to
    the schema's keys, coerced by type, empties dropped."""
    payload = payload if isinstance(payload, dict) else {}

    def loc(value):
        if isinstance(value, dict):
            return {"de": str(value.get("de") or "").strip(),
                    "en": str(value.get("en") or "").strip()}
        return {"de": str(value or "").strip(), "en": ""}

    raw = payload.get("attributes")
    raw = raw if isinstance(raw, dict) else {}
    attributes = {}
    for attr in schema:
        key = attr.get("key")
        if not key or key not in raw:
            continue
        value = raw[key]
        if value in (None, "", [], {}):
            continue
        atype = attr.get("type")
        if atype == "number":
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            value = int(num) if num.is_integer() else num
        elif atype in ("short_text", "long_text"):
            value = _normalize_attr_value(attr, value)
            if not any((value.get(lang) or "").strip() for lang in value):
                continue
        else:
            value = str(value).strip()
            if not value:
                continue
        attributes[key] = value
    return {
        "title": loc(payload.get("title")),
        "description": loc(payload.get("description")),
        # 200 = Product.short_description max_length.
        "short_description": {
            lang: text[:200]
            for lang, text in loc(payload.get("short_description")).items()
        },
        "attributes": attributes,
    }


class ManageProductViewSet(viewsets.ModelViewSet):
    """Lender/admin CRUD for products (catalog entries from a product type).

    Products are the shared catalog (not pool-bound), so any lender may manage
    them; physical units are scoped per pool on the inventory endpoint. The
    product gallery is managed via the ``images`` actions below.
    """

    queryset = Product.objects.select_related("product_type").prefetch_related("images").all()
    serializer_class = ProductManageSerializer
    permission_classes = [IsLenderOrAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["title", "description"]

    def perform_create(self, serializer):
        check_create_allowed(
            settings.MAX_PRODUCTS, Product.objects.count(), "products"
        )
        serializer.save()

    def get_queryset(self):
        queryset = (
            Product.objects.select_related("product_type")
            .prefetch_related("images", "complementary_products", "categories")
            .all()
        )
        # ?product_type=<id> narrows to the products of one product type.
        product_type = self.request.query_params.get("product_type")
        if product_type:
            if not product_type.isdigit():
                return queryset.none()
            queryset = queryset.filter(product_type_id=product_type)
        return queryset

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        if product.resources.exists():
            return Response(
                {"detail": "Cannot delete a product that still has resources."},
                status=400,
            )
        product.soft_delete(request.user)
        return Response(status=204)

    @action(
        detail=True,
        methods=["post"],
        url_path="images",
        parser_classes=[MultiPartParser, FormParser],
    )
    def images(self, request, pk=None):
        """Append one uploaded image (field ``image``) to the product gallery."""
        product = self.get_object()
        upload = request.FILES.get("image")
        if upload is None:
            return Response({"detail": "No image file provided."}, status=400)
        if upload.content_type and not upload.content_type.startswith("image/"):
            return Response({"detail": "Uploaded file must be an image."}, status=400)
        last = product.images.aggregate(m=Max("position"))["m"]
        image = ProductImage.objects.create(
            product=product,
            image=upload,
            position=(last + 1) if last is not None else 0,
        )
        return Response(
            ProductImageSerializer(image, context={"request": request}).data,
            status=201,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path="images/(?P<image_id>[0-9]+)",
    )
    def delete_image(self, request, pk=None, image_id=None):
        """Delete one gallery image of this product."""
        product = self.get_object()
        image = get_object_or_404(product.images, pk=image_id)
        image.image.delete(save=False)
        image.delete()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, pk=None):
        """Set the gallery order (and thereby the cover) to ``{"order": [id…]}``."""
        product = self.get_object()
        order = request.data.get("order")
        if not isinstance(order, list):
            return Response({"detail": "Provide an 'order' list of ids."}, status=400)
        try:
            ids = [int(value) for value in order]
        except (TypeError, ValueError):
            return Response({"detail": "Ids must be integers."}, status=400)
        existing = set(product.images.values_list("id", flat=True))
        if set(ids) != existing or len(ids) != len(existing):
            return Response(
                {"detail": "'order' must list every image id exactly once."},
                status=400,
            )
        by_id = product.images.in_bulk(ids)
        updated = []
        for position, image_id in enumerate(ids):
            image = by_id[image_id]
            image.position = position
            updated.append(image)
        ProductImage.objects.bulk_update(updated, ["position"])
        return Response(
            ProductImageSerializer(
                product.images.all(), many=True, context={"request": request}
            ).data
        )

    @action(
        detail=True,
        methods=["post", "delete"],
        url_path="attribute-pdf",
        parser_classes=[MultiPartParser, FormParser],
    )
    def attribute_pdf(self, request, *args, **kwargs):
        """Upload (POST) or remove (DELETE) the PDF for a ``pdf`` attribute.

        The attribute value in ``Product.attributes[key]`` holds the file's
        media URL. ``?key=`` selects the attribute; it must be a ``pdf``-typed
        attribute in the product's type schema.
        """
        product = self.get_object()
        key = request.query_params.get("key") or request.data.get("key")
        schema = product.product_type.attribute_schema or []
        attr = next(
            (a for a in schema if a.get("key") == key and a.get("type") == "pdf"),
            None,
        )
        if attr is None:
            return Response(
                {"detail": "No such PDF attribute on this product's type."},
                status=400,
            )

        attributes = dict(product.attributes or {})

        def _delete_existing():
            old = attributes.get(key) or ""
            prefix = settings.MEDIA_URL.rstrip("/")
            if old.startswith(prefix + "/"):
                name = old[len(prefix) + 1 :]
                if default_storage.exists(name):
                    default_storage.delete(name)

        if request.method == "DELETE":
            _delete_existing()
            attributes[key] = ""
            product.attributes = attributes
            product.save(update_fields=["attributes", "updated_at"])
            return Response(ProductManageSerializer(product, context=self.get_serializer_context()).data)

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file provided."}, status=400)
        if upload.content_type != "application/pdf" and not upload.name.lower().endswith(".pdf"):
            return Response({"detail": "File must be a PDF."}, status=400)
        if upload.size > 25 * 1024 * 1024:
            return Response({"detail": "PDF must be at most 25 MB."}, status=400)

        _delete_existing()
        name = f"product-docs/{product.id}-{key}-{uuid.uuid4().hex}.pdf"
        saved = default_storage.save(name, upload)
        url = default_storage.url(saved)
        if not url.startswith(("http://", "https://", "/")):
            url = "/" + url
        attributes[key] = url
        product.attributes = attributes
        product.save(update_fields=["attributes", "updated_at"])
        return Response(ProductManageSerializer(product, context=self.get_serializer_context()).data)

    @action(
        detail=False,
        methods=["post"],
        url_path="extract-from-pdf",
        parser_classes=[MultiPartParser, FormParser],
    )
    def extract_from_pdf(self, request):
        """Extract product fields from an uploaded PDF manual to pre-fill the
        form (AI feature 2). AI-optional; nothing is persisted."""
        if not ai.is_enabled():
            return Response({"detail": "AI is not configured."}, status=503)
        product_type = get_object_or_404(
            ProductType, pk=request.data.get("product_type")
        )
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No PDF file provided."}, status=400)
        if upload.size and upload.size > 20 * 1024 * 1024:
            return Response({"detail": "PDF is too large (max 20 MB)."}, status=400)
        is_pdf = (upload.content_type == "application/pdf") or upload.name.lower().endswith(".pdf")
        if not is_pdf:
            return Response({"detail": "Uploaded file must be a PDF."}, status=400)
        try:
            text = extract_pdf_text(upload)
        except PdfTextError:
            return Response({"detail": "No readable text in the PDF."}, status=422)
        system, user = build_product_extraction_prompt(product_type, text)
        try:
            payload = ai.chat_json(system, user)
        except ai.AIError:
            return Response({"detail": "AI request failed."}, status=502)
        return Response(_normalize_extraction(payload, product_type.attribute_schema or []))


class ManageInventoryViewSet(viewsets.ModelViewSet):
    """Lender/admin CRUD for the physical inventory (resources).

    Admins manage every resource; lenders only those in pools they manage —
    list, retrieve, edit, delete, QR and the defects overview are all scoped to
    their pools, and they may not create/move a resource into a pool they don't
    manage. Status-only transitions (defective/repaired) at the lending desk
    live on ``lending.ManageResourceViewSet``. Optional ?pool= / ?status=
    filters narrow the list.
    """

    serializer_class = ResourceManageSerializer
    permission_classes = [IsLenderOrAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["inventory_number", "serial_number", "product__title"]
    ordering_fields = [
        "inventory_number", "product__title", "resource_pool__name",
        "status", "condition_rating",
    ]
    ordering = ["inventory_number"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ResourceDetailManageSerializer
        return ResourceManageSerializer

    def get_queryset(self):
        queryset = Resource.objects.select_related("product", "resource_pool").all()
        if not _is_admin(self.request.user):
            queryset = queryset.filter(
                resource_pool_id__in=_managed_pool_ids(self.request.user)
            )
        pool = self.request.query_params.get("pool")
        if pool:
            queryset = queryset.filter(resource_pool_id=pool)
        elif self.action == "list" and _is_admin(self.request.user):
            # Default to an admin's own pools; detail actions stay unscoped.
            queryset = _narrow_to_admin_scope(
                self.request, queryset, "resource_pool_id"
            )
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        # New resources since a date — for printing only the freshly added labels.
        created_after = self.request.query_params.get("created_after")
        if created_after:
            day = parse_date(created_after)
            if day:
                queryset = queryset.filter(created_at__date__gte=day)
        return queryset

    def _check_pool_allowed(self, pool):
        """Lenders may only create/move a resource within pools they manage."""
        if _is_admin(self.request.user):
            return
        pool_id = getattr(pool, "id", pool)
        if pool_id not in _managed_pool_ids(self.request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You can only manage inventory in pools you manage.")

    def perform_create(self, serializer):
        check_create_allowed(
            settings.MAX_RESOURCES, Resource.objects.count(), "resources"
        )
        self._check_pool_allowed(serializer.validated_data.get("resource_pool"))
        serializer.save()

    def perform_update(self, serializer):
        pool = serializer.validated_data.get("resource_pool") or (
            serializer.instance.resource_pool
        )
        self._check_pool_allowed(pool)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        resource = self.get_object()
        if resource.booking_items.exists():
            return Response(
                {"detail": "Cannot delete a resource with booking history; "
                           "set its status to retired instead."},
                status=400,
            )
        resource.soft_delete(request.user)
        return Response(status=204)

    @action(detail=True, methods=["get"])
    def qr(self, request, pk=None):
        """PNG of the device's QR sticker (encodes the public /r/<qr_id> URL).

        Used by the printable-labels page (concept §6.2, phase 2).
        """
        from lending.qr import device_qr_url, make_qr_png

        resource = self.get_object()
        return HttpResponse(
            make_qr_png(device_qr_url(resource)), content_type="image/png"
        )

    @action(detail=False, methods=["get"])
    def defects(self, request):
        """Resources that are defective now or have been before, with a count
        of how often each has had a problem (concept §3.6)."""
        resources = (
            Resource.objects.select_related("product", "resource_pool")
            .annotate(defect_count=Count("defects"))
            .filter(defect_count__gt=0)
            .prefetch_related("defects")
            .order_by("-defect_count", "inventory_number")
        )
        if not _is_admin(request.user):
            resources = resources.filter(
                resource_pool_id__in=_managed_pool_ids(request.user)
            )
        else:
            resources = _narrow_to_admin_scope(request, resources, "resource_pool_id")
        rows = []
        for resource in resources:
            defects = list(resource.defects.all())
            open_defect = next((d for d in defects if d.resolved_at is None), None)
            last = max((d.created_at for d in defects), default=None)
            latest_defect = max(
                defects, key=lambda d: d.created_at, default=None
            )
            relevant = open_defect or latest_defect
            rows.append(
                {
                    "id": resource.id,
                    "inventory_number": resource.inventory_number,
                    "product_title": resource.product.title,
                    "pool_name": resource.resource_pool.name,
                    "status": resource.status,
                    "defect_count": resource.defect_count,
                    "currently_defective": (
                        resource.status == Resource.Status.DEFECTIVE
                    ),
                    "defect_note": open_defect.note if open_defect else "",
                    "defective_since": (
                        open_defect.created_at.isoformat() if open_defect else None
                    ),
                    "last_defect": last.isoformat() if last else None,
                    "gitlab_issue_url": relevant.gitlab_issue_url if relevant else "",
                }
            )
        return Response({"resources": rows})

    @action(detail=False, methods=["get"], url_path="suggest-number")
    def suggest_number(self, request):
        """Suggest the lowest free inventory number (and QR id) for a pool.

        Format ``<pool_id>-NNN``. Gaps left by deleted resources are reused,
        so the suggestion is the smallest unused number for that pool. The
        client may freely override it.
        """
        pool = ResourcePool.objects.filter(
            pk=request.query_params.get("pool")
        ).first()
        if pool is None:
            return Response({"detail": "Provide a valid 'pool'."}, status=400)
        if not _is_admin(request.user) and pool.id not in _managed_pool_ids(request.user):
            return Response({"detail": "You don't manage this pool."}, status=403)

        prefix = f"{pool.pool_id}-"
        used = set()
        for number in Resource.objects.filter(resource_pool=pool).values_list(
            "inventory_number", flat=True
        ):
            tail = number.rsplit("-", 1)[-1]
            if tail.isdigit():
                used.add(int(tail))

        inv_taken = set(Resource.objects.values_list("inventory_number", flat=True))
        qr_taken = set(Resource.objects.values_list("qr_code_id", flat=True))
        n = 1
        while True:
            inventory_number = f"{prefix}{n:03d}"
            qr_code_id = f"QR-{prefix}{n:03d}"
            if (
                n not in used
                and inventory_number not in inv_taken
                and qr_code_id not in qr_taken
            ):
                break
            n += 1
        return Response(
            {"inventory_number": inventory_number, "qr_code_id": qr_code_id}
        )


class ShopPoolsView(APIView):
    """GET /api/pools/ — resource pools the requester may access in the shop.

    Lets a borrower browse by location: the active pools they're eligible for
    (concept §3.4), each linking to its bookable stock (``/api/products/?pool=``).
    """

    permission_classes = []

    def get(self, request):
        pool_ids = eligible_pool_ids(request.user)
        pools = ResourcePool.objects.filter(
            is_active=True, id__in=pool_ids
        ).order_by("position", "name")
        return Response(
            PoolCardSerializer(pools, many=True, context={"request": request}).data
        )


class ShopPoolDetailView(APIView):
    """GET /api/pools/<id>/ — public info page for one pool (opening hours,
    address, contact). Limited to pools the requester may access."""

    permission_classes = []

    def get(self, request, pk):
        pool_ids = eligible_pool_ids(request.user)
        pool = get_object_or_404(
            ResourcePool, pk=pk, is_active=True, id__in=pool_ids
        )
        return Response(
            PoolDetailSerializer(pool, context={"request": request}).data
        )


class ShopPoolProductsGroupedView(APIView):
    """GET /api/pools/<id>/products-grouped/ — the pool's bookable products
    clustered by top-level category (#14, #78), for the pool page.

    Same eligibility/visibility rule as ``?pool=`` on the flat product list
    (``ProductViewSet``): a product must have a resource in this pool and pass
    ``visible_products``. Response is a list of
    ``{"category": {"id", "name"} | null, "products": [ProductBrief...]}``:
    top-level categories in tree order (``position``, then name), each with
    the pool's products of its whole subtree in shop order (daily before
    hourly, #19); empty groups omitted. A product in several categories
    appears in each of their groups. Products in no (live) category form a
    last group with ``"category": null`` ("Other"). 404s for a pool the
    requester can't access, same as the other pool endpoints.
    """

    permission_classes = []

    def get(self, request, pk):
        context = {"request": request}
        nav = shop_navigation(context)
        pool = get_object_or_404(
            ResourcePool, pk=pk, is_active=True, id__in=context["_eligible_pool_ids"]
        )
        pool_products = list(
            visible_products(
                Product.objects.prefetch_related("images")
                .filter(resources__resource_pool_id=pool.id)
                .distinct(),
                request.user,
                pool_ids=context["_eligible_pool_ids"],
            )
        )
        nav.add_products(pool_products)
        in_pool = {p.id for p in pool_products}
        grouped = set()
        groups = []
        for root_id in nav.tree.roots:
            products = nav.ordered_products(root_id, restrict=in_pool)
            if not products:
                continue
            grouped.update(p.id for p in products)
            root = nav.tree.nodes[root_id]
            groups.append({"category": {"id": root.id, "name": root.name}, "products": products})
        other = daily_first(
            sorted(
                (p for p in pool_products if p.id not in grouped),
                key=lambda p: (p.title.casefold(), p.id),
            )
        )
        if other:
            groups.append({"category": None, "products": other})
        for group in groups:
            group["products"] = ProductBriefSerializer(
                group["products"], many=True, context=context
            ).data
        return Response(groups)


class FooterPagesView(APIView):
    """Public list of footer links — published pages flagged for the footer.

    No authentication required (the footer shows on the landing page too).
    """

    permission_classes = []

    def get(self, request):
        pages = Page.objects.filter(is_published=True, show_in_footer=True)
        return Response(PageLinkSerializer(pages, many=True).data)


class PageDetailView(APIView):
    """Public read of one published content page by slug (``/pages/<slug>/``)."""

    permission_classes = []

    def get(self, request, slug):
        page = get_object_or_404(Page, slug=slug, is_published=True)
        return Response(PageDetailSerializer(page).data)


class ManagePageViewSet(PositionOrderedMixin, viewsets.ModelViewSet):
    """Admin CRUD for content pages (Imprint, Privacy, …).

    Pages carry a manual ``footer_order`` set by the reorder action; the admin
    reorders them directly in the overview list rather than typing a number.
    """

    queryset = Page.objects.all()
    serializer_class = PageManageSerializer
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["title", "slug"]
    position_field = "footer_order"


class WelcomeView(APIView):
    """Public welcome-page content for not-yet-logged-in visitors.

    Returns the admin-defined sanitized rich-HTML text and the active resource
    pools (with images) to present on the landing page. No authentication
    required.
    """

    permission_classes = []

    def get(self, request):
        pools = ResourcePool.objects.filter(is_active=True).order_by("position", "name")
        return Response(
            {
                "text": WelcomeSetting.load().text,
                "pools": PoolCardSerializer(
                    pools, many=True, context={"request": request}
                ).data,
            }
        )


class WelcomeSettingView(APIView):
    """Admin GET/PUT of the welcome page's sanitized rich-HTML text."""

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(
            WelcomeSettingSerializer(
                WelcomeSetting.load(), context={"request": request}
            ).data
        )

    def put(self, request):
        setting = WelcomeSetting.load()
        serializer = WelcomeSettingSerializer(
            setting, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NotificationSettingView(APIView):
    """Admin GET/PUT of the custom reservation-email text (de/en)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(NotificationSettingSerializer(NotificationSetting.load()).data)

    def put(self, request):
        setting = NotificationSetting.load()
        serializer = NotificationSettingSerializer(
            setting, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ShopSettingView(APIView):
    """Admin GET/PUT of the start-page display settings (which featured rows
    show, and how long products are flagged "new")."""

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(ShopSettingSerializer(ShopSetting.load()).data)

    def put(self, request):
        setting = ShopSetting.load()
        serializer = ShopSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TrashSettingView(APIView):
    """Admin GET/PUT of the trash retention window (#7): how long soft-deleted
    catalog objects are kept before `purge_trash` hard-deletes them."""

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(TrashSettingSerializer(TrashSetting.load()).data)

    def put(self, request):
        setting = TrashSetting.load()
        serializer = TrashSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


def _logo_url(setting, request):
    if not setting.logo:
        return None
    return request.build_absolute_uri(setting.logo.url) if request else setting.logo.url


class BrandingView(APIView):
    """GET /api/branding/ — public shop branding (the institution logo).

    Lightweight so the header can fetch it on any page, signed in or not.
    """

    permission_classes = []

    def get(self, request):
        return Response({"logo": _logo_url(WelcomeSetting.load(), request)})


class WelcomeLogoView(APIView):
    """Admin upload/clear of the shop logo (raster image or SVG)."""

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        setting = WelcomeSetting.load()
        upload = request.FILES.get("logo")
        if upload is None:
            return Response({"detail": "No logo file provided."}, status=400)
        is_image = bool(upload.content_type) and upload.content_type.startswith("image/")
        is_svg = (upload.name or "").lower().endswith(".svg")
        if not (is_image or is_svg):
            return Response(
                {"detail": "The logo must be an image or an SVG file."}, status=400
            )
        if upload.size > 5 * 1024 * 1024:
            return Response({"detail": "The logo must be at most 5 MB."}, status=400)
        if setting.logo:
            setting.logo.delete(save=False)
        setting.logo.save(upload.name, upload, save=True)
        return Response({"logo": _logo_url(setting, request)})

    def delete(self, request):
        setting = WelcomeSetting.load()
        if setting.logo:
            setting.logo.delete(save=True)
        return Response({"logo": None})


class RichImageUploadView(APIView):
    """POST /api/manage/rich-images/ — an image for rich-text fields (#5).

    Admin-only (they edit pages, the welcome text and pools). The image is
    decoded and re-encoded (#43): real format decides the extension, metadata
    such as EXIF/GPS/XMP is dropped (the ICC profile is kept), huge images
    are rejected, an APNG is stored as its first frame. Returns a relative
    /media/ URL: the sanitizer keeps only such image sources."""

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "No file uploaded."}, status=400)
        if upload.size > rich_images.RICH_IMAGE_MAX_BYTES:
            return Response({"detail": "Image is too large (max 5 MB)."}, status=400)
        try:
            data, ext = rich_images.process_rich_image(upload.read())
        except ValueError:
            return Response({"detail": "Uploaded file must be an image."}, status=400)
        name = default_storage.save(f"rich/{uuid.uuid4().hex}{ext}", ContentFile(data))
        media = "/" + settings.MEDIA_URL.strip("/") + "/"
        return Response({"url": media + name}, status=201)


class FavoritesView(APIView):
    """The current borrower's favorite products.

    ``GET`` lists them (only products still visible to the user); ``POST``
    ``{"product": <id>}`` adds one (idempotent).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        product_ids = Favorite.objects.filter(user=request.user).values_list(
            "product_id", flat=True
        )
        products = visible_products(
            Product.objects.filter(id__in=product_ids), request.user
        ).order_by("title")
        return Response(
            ProductBriefSerializer(
                products, many=True, context={"request": request}
            ).data
        )

    def post(self, request):
        product = get_object_or_404(Product, pk=request.data.get("product"))
        # Only products the user may access can be favorited.
        if not visible_products(
            Product.objects.filter(pk=product.pk), request.user
        ).exists():
            return Response({"detail": "No such product."}, status=404)
        Favorite.objects.get_or_create(user=request.user, product=product)
        return Response({"product": product.pk, "is_favorite": True}, status=201)


class FavoriteDetailView(APIView):
    """Remove a product from the current borrower's favorites."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, product_id):
        Favorite.objects.filter(user=request.user, product_id=product_id).delete()
        return Response(status=204)
