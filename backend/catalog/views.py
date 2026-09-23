# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Read-only catalog API for the borrower-facing shop, plus admin management."""
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
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
from accounts.permissions import IsAdmin, IsLenderOrAdmin
from basicbar_integrations import ai, translation_service
from basicbar_integrations.views import TranslateView as BaseTranslateView
from common.limits import check_create_allowed
from .ai_prompts import (
    RESERVED_ATTRIBUTE_KEYS,
    build_attribute_prompt,
    build_product_extraction_prompt,
)
from .pdf_extract import PdfTextError, extract_pdf_text
from .serializers import _normalize_attr_value, normalize_attribute


def _is_admin(user):
    """Admins (staff/superusers) are unscoped; lenders are limited to their pools."""
    return bool(user.is_staff or user.is_superuser)


def _managed_pool_ids(user):
    """Ids of the pools a lender manages (via PoolMembership)."""
    return set(user.pool_memberships.values_list("resource_pool_id", flat=True))

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
    CategoryManageSerializer,
    CategoryWithProductsSerializer,
    NotificationSettingSerializer,
    PageDetailSerializer,
    PageLinkSerializer,
    PageManageSerializer,
    ProductBriefSerializer,
    ProductImageSerializer,
    ProductDetailSerializer,
    ProductManageSerializer,
    ProductSetManageSerializer,
    ProductTypeSerializer,
    order_by_ids,
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


class SectionViewSet(viewsets.ReadOnlyModelViewSet):
    """Sections ("Sparten") — the top-level grouping shown on the start page."""

    queryset = Section.objects.prefetch_related("categories__products__images").all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SectionDetailSerializer
        return SectionListSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategoryWithProductsSerializer

    def get_queryset(self):
        queryset = Category.objects.prefetch_related("products__images").all()
        section = self.request.query_params.get("section")
        if section:
            queryset = queryset.filter(sections__id=section)
        return queryset


class SearchView(APIView):
    """GET /api/search/?q= — shop search across products, categories and sections.

    Products match by title/description (visibility-filtered, as on the product
    list). Categories and sections match by their own name and are returned with
    their content (categories → their visible products; sections → their
    categories with products), so searching a grouping's name surfaces it and
    what's inside it.
    """

    permission_classes = []

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response({"sections": [], "categories": [], "products": []})
        context = {"request": request}
        sections = (
            Section.objects.filter(title__icontains=query)
            .prefetch_related("categories__products", "sets")
            .order_by("position", "title")
        )
        categories = (
            Category.objects.filter(title__icontains=query)
            .prefetch_related("products")
            .order_by("position", "title")
        )
        products = visible_products(
            Product.objects.select_related("product_type")
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .distinct(),
            request.user,
        )
        return Response(
            {
                "sections": SectionDetailSerializer(
                    sections, many=True, context=context
                ).data,
                "categories": CategoryWithProductsSerializer(
                    categories, many=True, context=context
                ).data,
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
    """Products with filtering by category/section and a simple text search."""

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductBriefSerializer

    def get_queryset(self):
        queryset = Product.objects.select_related("product_type").prefetch_related("images").all()
        params = self.request.query_params
        if params.get("category"):
            queryset = queryset.filter(categories__id=params["category"])
        if params.get("section"):
            queryset = queryset.filter(categories__sections__id=params["section"])
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
        existing = set(model.objects.values_list("id", flat=True))
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
        if self.request.method in permissions.SAFE_METHODS:
            return [IsLenderOrAdmin()]
        return [IsAdmin()]

    def get_queryset(self):
        queryset = ResourcePool.objects.all()
        if not _is_admin(self.request.user):
            queryset = queryset.filter(id__in=_managed_pool_ids(self.request.user))
            return queryset.order_by("position", "name")
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
        return queryset


class ManageProductTypeViewSet(viewsets.ModelViewSet):
    """Admin CRUD for product types (templates with a dynamic attribute schema)."""

    queryset = ProductType.objects.all()
    serializer_class = ProductTypeSerializer
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["name"]

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


class ManageCategoryViewSet(
    PositionOrderedMixin, ImageUploadMixin, viewsets.ModelViewSet
):
    """Admin CRUD for categories (browsable groupings of products)."""

    queryset = Category.objects.prefetch_related("products__images").all()
    serializer_class = CategoryManageSerializer
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["title"]

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete(request.user)
        return Response(status=204)


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
    """Admin CRUD for sections ("Sparten") — groupings of categories."""

    queryset = Section.objects.prefetch_related("categories").all()
    serializer_class = SectionManageSerializer
    permission_classes = [IsAdmin]
    filter_backends = [SearchFilter]
    search_fields = ["title"]

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete(request.user)
        return Response(status=204)


def _normalize_extraction(payload, schema):
    """Shape a model reply into {title:{de,en}, description:{de,en},
    attributes:{key:value}} — attributes limited to the schema's keys, coerced
    by type, empties dropped."""
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
            .prefetch_related("categories", "images")
            .all()
        )
        # ?category=<id> narrows to one category; ?category=none → uncategorised.
        category = self.request.query_params.get("category")
        if category == "none":
            queryset = queryset.filter(categories__isnull=True)
        elif category:
            queryset = queryset.filter(categories__id=category)
        return queryset.distinct()

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
    clustered by category (issue #14), for the pool page's grouped display.

    Same eligibility/visibility rule as ``?pool=`` on the flat product list
    (``ProductViewSet``): a product must have a resource in this pool and pass
    ``visible_products``. Response is a list of
    ``{"category": {"id", "title"} | null, "products": [ProductBrief...]}``,
    categories in ``Category.position`` order, with a trailing ``null``
    bucket for pool products in no category. A product in several categories
    appears in each. 404s for a pool the requester can't access, same as the
    other pool endpoints.
    """

    permission_classes = []

    def get(self, request, pk):
        pool_ids = eligible_pool_ids(request.user)
        pool = get_object_or_404(
            ResourcePool, pk=pk, is_active=True, id__in=pool_ids
        )

        pool_products = visible_products(
            Product.objects.select_related("product_type")
            .prefetch_related("images")
            .filter(resources__resource_pool_id=pool.id)
            .distinct(),
            request.user,
        )
        by_id = {product.id: product for product in pool_products}
        remaining_ids = set(by_id)

        context = {"request": request}
        groups = []
        for category in Category.objects.order_by("position", "title"):
            category_ids = set(
                category.products.values_list("id", flat=True)
            ) & set(by_id)
            if not category_ids:
                continue
            remaining_ids -= category_ids
            # Respect the category's own curated order (product_order), the
            # same manual ordering the admin's reorder controls maintain and
            # CategoryWithProductsSerializer.get_products() applies — this
            # grouped view is now the primary pool-browsing UI, so an
            # admin-arranged order must carry over here too.
            products = order_by_ids(
                [by_id[pid] for pid in category_ids], category.product_order
            )
            groups.append(
                {
                    "category": {"id": category.id, "title": category.title},
                    "products": ProductBriefSerializer(
                        products, many=True, context=context
                    ).data,
                }
            )

        if remaining_ids:
            # No curated order applies to the uncategorised bucket; fall back
            # to a stable, deterministic order (title, then id as tiebreak)
            # rather than arbitrary queryset/DB order.
            remaining = sorted(
                (by_id[pid] for pid in remaining_ids),
                key=lambda p: (p.title.lower(), p.id),
            )
            groups.append(
                {
                    "category": None,
                    "products": ProductBriefSerializer(
                        remaining, many=True, context=context
                    ).data,
                }
            )

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

    Returns the admin-defined Markdown text and the active resource pools
    (with images) to present on the landing page. No authentication required.
    """

    permission_classes = []

    def get(self, request):
        pools = ResourcePool.objects.filter(is_active=True).order_by("name")
        return Response(
            {
                "text": WelcomeSetting.load().text,
                "pools": PoolCardSerializer(
                    pools, many=True, context={"request": request}
                ).data,
            }
        )


class WelcomeSettingView(APIView):
    """Admin GET/PUT of the welcome page Markdown text."""

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
