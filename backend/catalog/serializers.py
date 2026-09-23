# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Serializers for the borrower-facing catalog API."""
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone, translation
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from accounts.eligibility import eligible_pool_ids, visible_products

from . import sets as set_helpers

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
    ResourceDefect,
    ResourcePool,
    Section,
    ShopSetting,
    TrashSetting,
    WelcomeSetting,
)

_DAY_KEYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

# Content languages for translatable fields (issue #6, Phase 2).
TRANSLATION_LANGS = [code for code, _ in settings.LANGUAGES]


def resolve_translated_text(value):
    """Resolve a translatable text to the active request language.

    Used for translatable strings living inside JSON (e.g. attribute_schema
    labels, issue #6 Phase 3), which modeltranslation can't handle. ``value``
    may be a plain string (the same text in every language, backward
    compatible) or a ``{lang: text}`` dict; a dict falls back default → other
    languages → any non-empty value, mirroring the modeltranslation fallback.
    """
    if not isinstance(value, dict):
        return value
    active = (translation.get_language() or settings.MODELTRANSLATION_DEFAULT_LANGUAGE)
    for lang in (active.split("-")[0], *settings.MODELTRANSLATION_FALLBACK_LANGUAGES):
        text = value.get(lang)
        if text:
            return text
    return next((text for text in value.values() if text), "")


class TranslatedFieldsMixin:
    """Expose django-modeltranslation's per-language columns for editing.

    A manage serializer sets ``translated_fields`` to the base field names and
    adds the ``<field>_<lang>`` variants to ``Meta.fields``. The form then edits
    each language explicitly (e.g. ``title_de`` / ``title_en``). This mixin:

    * keeps the bare field writable but optional — older callers that send
      ``{"title": "X"}`` keep working (it writes the request's active language,
      as modeltranslation does normally);
    * makes every per-language variant optional and normalises a blank
      translation to ``NULL`` so untranslated rows don't collide on the unique
      translation columns (e.g. two categories with no English title);
    * still requires, on create, that the canonical column gets populated — via
      the bare field or the default-language variant — when the base model
      field is required (modeltranslation keeps the bare column in sync with the
      default language, so an English-only payload would leave it NULL).

    A subclass that defines its own ``validate`` must call ``super().validate``
    so this normalisation still runs.
    """

    translated_fields: tuple = ()

    def get_fields(self):
        fields = super().get_fields()
        for base in self.translated_fields:
            for name in (base, *(f"{base}_{lang}" for lang in TRANSLATION_LANGS)):
                field = fields.get(name)
                if field is None:
                    continue
                # All variants (and the legacy bare field) are optional on
                # input; the canonical-required check happens in validate().
                field.required = False
                if hasattr(field, "allow_blank"):
                    field.allow_blank = True
                # Replace the default "… with this name de already exists."
                # uniqueness message (which leaks the internal column) with a
                # clear, translatable one.
                for validator in getattr(field, "validators", []):
                    if isinstance(validator, UniqueValidator):
                        validator.message = (
                            f"An entry with this {base} already exists."
                        )
        return fields

    def _base_required(self, base):
        model_field = self.Meta.model._meta.get_field(base)
        return not (model_field.blank or model_field.null or model_field.has_default())

    def validate(self, attrs):
        attrs = super().validate(attrs)
        default = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
        errors = {}
        for base in self.translated_fields:
            default_key = f"{base}_{default}"
            # Blank translations become NULL (no collision on unique columns).
            for lang in TRANSLATION_LANGS:
                key = f"{base}_{lang}"
                if attrs.get(key) == "":
                    attrs[key] = None
            # The canonical column must stay non-empty (it backs the bare NOT
            # NULL field via modeltranslation). On create it must be provided;
            # on update reject only a payload that *clears* it (touches the bare
            # or default-language key but leaves both empty) — an unrelated PATCH
            # that doesn't mention them keeps the stored value untouched.
            if self._base_required(base):
                touches_canonical = base in attrs or default_key in attrs
                provided = attrs.get(base) or attrs.get(default_key)
                if (self.instance is None or touches_canonical) and not provided:
                    errors[default_key] = "This field is required."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ATTR_TYPES = {
    "short_text", "long_text", "date", "time", "number", "url", "media", "image",
    "pdf",
}
_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def _clean_label(label):
    """Normalise an attribute label to a per-language ``{lang: text}`` dict.
    A plain string is treated as the default-language value (backward
    compatible); unknown languages are dropped, missing ones stored empty."""
    if isinstance(label, dict):
        values = {lang: str(label.get(lang) or "").strip() for lang in TRANSLATION_LANGS}
    else:
        values = {lang: "" for lang in TRANSLATION_LANGS}
        values[settings.MODELTRANSLATION_DEFAULT_LANGUAGE] = str(label or "").strip()
    return values


_TEXT_ATTR_TYPES = {"short_text", "long_text"}


def _normalize_attr_value(attr, value):
    """Normalise one attribute value to its stored shape for a schema entry.
    Free-text types (short_text/long_text) become a per-language ``{de,en}``
    dict (a plain string maps to the canonical language); every other type is
    returned unchanged (language-neutral)."""
    if attr.get("type") not in _TEXT_ATTR_TYPES:
        return value
    if isinstance(value, dict):
        return {lang: str(value.get(lang) or "").strip() for lang in TRANSLATION_LANGS}
    values = {lang: "" for lang in TRANSLATION_LANGS}
    values[settings.MODELTRANSLATION_DEFAULT_LANGUAGE] = str(value or "").strip()
    return values


def normalize_attribute(attr):
    """Validate & normalise one attribute-schema entry. Raises ``ValueError``
    if the entry is not an object, lacks a valid key, or has an unknown type."""
    if not isinstance(attr, dict):
        raise ValueError("must be an object")
    key = str(attr.get("key", "")).strip()
    if not key:
        raise ValueError("needs a key")
    if not _KEY_RE.match(key):
        raise ValueError(f"key '{key}' is invalid")
    attr_type = attr.get("type")
    if attr_type not in _ATTR_TYPES:
        raise ValueError(f"invalid type '{attr_type}'")
    return {
        "key": key,
        "label": _clean_label(attr.get("label")),
        "type": attr_type,
        "default": attr.get("default", ""),
        "visible": bool(attr.get("visible", True)),
        "required": bool(attr.get("required", False)),
    }


class ProductImageSerializer(serializers.ModelSerializer):
    """One gallery image of a product."""

    class Meta:
        model = ProductImage
        fields = ["id", "image", "position"]


def _cover_url(product, request=None):
    """Absolute URL of a product's cover (first gallery image), or None.

    Built against the request so it matches DRF's ImageField output (absolute),
    which the SPA needs because the API host differs from the shop in dev.
    """
    first = product.images.all().first()
    if not (first and first.image):
        return None
    url = first.image.url
    return request.build_absolute_uri(url) if request else url


class ProductBriefSerializer(serializers.ModelSerializer):
    """Compact product representation for lists and cards."""

    image = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "title", "short_description", "image", "lending_type", "is_new"]

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def get_is_new(self, obj):
        """Whether the product is still within the system-wide "new" window.
        The cutoff is computed once per serialization (memoised on the reused
        child instance) to avoid a settings query per product."""
        if not obj.created_at:
            return False
        cutoff = getattr(self, "_new_cutoff", "unset")
        if cutoff == "unset":
            days = ShopSetting.load().new_product_days
            cutoff = timezone.now() - timedelta(days=days) if days > 0 else None
            self._new_cutoff = cutoff
        return bool(cutoff and obj.created_at >= cutoff)


def order_by_ids(items, ordered_ids):
    """Sort an iterable of objects by an explicit list of ids; items whose id is
    not listed keep their incoming order, after the listed ones. Used for the
    manual ordering of products-in-category, and categories/sets-in-section."""
    rank = {oid: i for i, oid in enumerate(ordered_ids or [])}
    return sorted(items, key=lambda obj: rank.get(obj.id, len(rank)))


class CategoryWithProductsSerializer(serializers.ModelSerializer):
    products = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "title", "description", "product_count", "products"]

    def _visible(self, obj):
        request = self.context.get("request")
        user = request.user if request else None
        return visible_products(obj.products.all(), user)

    def get_products(self, obj):
        ordered = order_by_ids(self._visible(obj), obj.product_order)
        return ProductBriefSerializer(
            ordered, many=True, context=self.context
        ).data

    def get_product_count(self, obj):
        return self._visible(obj).count()


class SectionListSerializer(serializers.ModelSerializer):
    category_count = serializers.IntegerField(source="categories.count", read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ["id", "title", "description", "image", "category_count", "product_count"]

    def get_product_count(self, obj):
        """Distinct products the requester may see across this section's
        categories — what the shopper will actually find inside."""
        request = self.context.get("request")
        user = request.user if request else None
        products = Product.objects.filter(categories__sections=obj).distinct()
        return visible_products(products, user).count()


class SectionDetailSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()
    sets = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ["id", "title", "description", "image", "categories", "sets"]

    def get_categories(self, obj):
        ordered = order_by_ids(obj.categories.all(), obj.category_order)
        return CategoryWithProductsSerializer(
            ordered, many=True, context=self.context
        ).data

    def get_sets(self, obj):
        return [
            {"id": s.id, "name": s.name, "product_count": s.products.count()}
            for s in order_by_ids(obj.sets.all(), obj.set_order)
        ]


class PoolBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourcePool
        fields = [
            "id", "name", "address", "room", "lead_time_hours",
            "max_booking_months", "accent_color",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    product_type_name = serializers.CharField(source="product_type.name", read_only=True)
    visible_attributes = serializers.SerializerMethodField()
    pools = serializers.SerializerMethodField()
    sets = serializers.SerializerMethodField()
    effective_max_duration = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    # `image` stays as the cover (first gallery image) for back-compat; `images`
    # is the full ordered gallery for the product page.
    image = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "short_description",
            "image",
            "images",
            "lending_type",
            "min_duration",
            "max_duration",
            "product_type_name",
            "visible_attributes",
            "pools",
            "sets",
            "effective_max_duration",
            "is_favorite",
        ]

    def get_is_favorite(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return Favorite.objects.filter(user=user, product=obj).exists()

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def get_effective_max_duration(self, obj):
        """Maximum lending duration in the lending-type unit, with inheritance.

        The product's own ``max_duration`` wins; otherwise it's inherited from
        the default of the pool(s) the product is stocked in (the most
        permissive, since the page isn't pool-specific). ``None`` means no
        limit — shown to borrowers as "not limited".
        """
        if obj.max_duration:
            return obj.max_duration
        field = (
            "default_max_days" if obj.lending_type == "days" else "default_max_hours"
        )
        defaults = [
            getattr(pool, field)
            for pool in ResourcePool.objects.filter(resources__product=obj).distinct()
            if getattr(pool, field)
        ]
        return max(defaults) if defaults else None

    def get_sets(self, obj):
        return [
            {"id": s.id, "name": s.name} for s in obj.product_sets.all()
        ]

    def get_visible_attributes(self, obj):
        """Join the product type's schema with the product's values.

        Only attributes flagged ``visible`` are exposed to borrowers.
        """
        schema = obj.product_type.attribute_schema or []
        values = obj.attributes or {}
        result = []
        for attr in schema:
            if attr.get("visible"):
                key = attr.get("key")
                result.append(
                    {
                        "key": key,
                        "label": resolve_translated_text(attr.get("label")) or key,
                        "type": attr.get("type"),
                        "value": resolve_translated_text(
                            values.get(key, attr.get("default"))
                        ),
                    }
                )
        return result

    def get_pools(self, obj):
        # Position-ordered (#6) so the product page's pool selector matches the
        # shop's pool order (#10).
        pools = ResourcePool.objects.filter(resources__product=obj).distinct().order_by(
            "position", "name"
        )
        request = self.context.get("request")
        if request:
            pools = pools.filter(id__in=eligible_pool_ids(request.user))
        return PoolBriefSerializer(pools, many=True).data


class SetBriefSerializer(serializers.ModelSerializer):
    """Compact set representation for the start-page sets row."""

    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = ProductSet
        fields = ["id", "name", "product_count"]


class SetDetailSerializer(serializers.ModelSerializer):
    """A set with its products, its pool and derived duration limits."""

    products = ProductBriefSerializer(many=True, read_only=True)
    lending_type = serializers.SerializerMethodField()
    min_duration = serializers.SerializerMethodField()
    max_duration = serializers.SerializerMethodField()
    pool = serializers.SerializerMethodField()

    class Meta:
        model = ProductSet
        fields = [
            "id", "name", "description", "products", "lending_type",
            "min_duration", "max_duration", "pool",
        ]

    def get_lending_type(self, obj):
        return set_helpers.set_lending_type(list(obj.products.all()))

    def _durations(self, obj):
        return set_helpers.set_durations(list(obj.products.all()))

    def get_min_duration(self, obj):
        return self._durations(obj)[0]

    def get_max_duration(self, obj):
        return self._durations(obj)[1]

    def get_pool(self, obj):
        """The set's pool, only if the requester may access it."""
        pool = obj.resource_pool
        if pool is None:
            return None
        request = self.context.get("request")
        if request and pool.id not in eligible_pool_ids(request.user):
            return None
        return PoolBriefSerializer(pool).data


class ProductTypeSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for the admin product-type management UI."""

    translated_fields = ("name", "description")

    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = ProductType
        fields = [
            "id", "name", "name_de", "name_en", "description",
            "description_de", "description_en", "attribute_schema", "product_count",
        ]

    def validate_attribute_schema(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Must be a list of attribute definitions."
            )
        seen = set()
        cleaned = []
        for index, attr in enumerate(value, start=1):
            try:
                entry = normalize_attribute(attr)
            except ValueError as exc:
                raise serializers.ValidationError(f"Attribute #{index}: {exc}")
            if entry["key"] in seen:
                raise serializers.ValidationError(f"Duplicate key '{entry['key']}'.")
            seen.add(entry["key"])
            cleaned.append(entry)
        return cleaned


class ResourceManageSerializer(serializers.ModelSerializer):
    """Read/write representation for the admin inventory (resource) UI."""

    product_title = serializers.CharField(source="product.title", read_only=True)
    pool_name = serializers.CharField(source="resource_pool.name", read_only=True)

    class Meta:
        model = Resource
        fields = [
            "id", "product", "product_title", "resource_pool", "pool_name",
            "inventory_number", "qr_code_id", "status", "defect_note",
            "condition_rating", "condition_note",
            "storage_location", "procurement_date", "warranty_end", "value",
            "procuring_institution", "owning_institution",
        ]


class ResourceDefectSerializer(serializers.ModelSerializer):
    reported_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ResourceDefect
        fields = ["id", "note", "reported_at", "resolved_at"]


class ResourceDetailManageSerializer(ResourceManageSerializer):
    """Resource representation for the detail view: adds defect & lending history."""

    defects = ResourceDefectSerializer(many=True, read_only=True)
    bookings = serializers.SerializerMethodField()

    class Meta(ResourceManageSerializer.Meta):
        fields = ResourceManageSerializer.Meta.fields + ["defects", "bookings"]

    def get_bookings(self, obj):
        items = (
            obj.booking_items.select_related("booking__borrower")
            .order_by("-id")[:50]
        )
        history = []
        for item in items:
            booking = item.booking
            period = item.period
            history.append(
                {
                    "booking_id": booking.id,
                    "status": booking.status,
                    "borrower": booking.borrower.get_username(),
                    "start": period.lower.isoformat() if period and period.lower else None,
                    "end": period.upper.isoformat() if period and period.upper else None,
                }
            )
        return history


class CategoryManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for admin category management.

    ``products`` is the set of products assigned to this category (M2M).
    """

    translated_fields = ("title", "description")

    products = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Product.objects.all(), required=False
    )
    product_count = serializers.IntegerField(source="products.count", read_only=True)
    # The sections ("Sparten") this category belongs to — assignable from the
    # category side (reverse of Section.categories).
    sections = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Section.objects.all(), required=False
    )
    # Set via the dedicated multipart upload action, not via JSON.
    image = serializers.ImageField(read_only=True)
    # Managed via the dedicated reorder action; new entries are appended.
    position = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id", "title", "title_de", "title_en", "description",
            "description_de", "description_en", "image", "products",
            "product_count", "sections", "position",
        ]

    def to_representation(self, instance):
        # Return assigned products in the saved manual order so the editor can
        # render and reorder them.
        data = super().to_representation(instance)
        order = instance.product_order or []
        rank = {pid: i for i, pid in enumerate(order)}
        data["products"] = sorted(
            data.get("products", []), key=lambda pid: rank.get(pid, len(rank))
        )
        return data

    def _store_order(self, instance, products):
        """Persist the order the products were sent in as ``product_order``."""
        instance.product_order = [p.pk for p in products]
        instance.save(update_fields=["product_order"])

    def create(self, validated_data):
        products = validated_data.get("products", [])
        instance = super().create(validated_data)
        self._store_order(instance, products)
        return instance

    def update(self, instance, validated_data):
        products = validated_data.get("products", None)
        instance = super().update(instance, validated_data)
        if products is not None:
            self._store_order(instance, products)
        return instance


class ProductSetManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for admin set management (concept §5.5).

    A set is a list of products lent together from one pool.
    """

    translated_fields = ("name", "description")

    products = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Product.objects.all(), required=False
    )
    product_count = serializers.IntegerField(source="products.count", read_only=True)
    pool_name = serializers.CharField(
        source="resource_pool.name", read_only=True, default=None
    )

    class Meta:
        model = ProductSet
        fields = [
            "id", "name", "name_de", "name_en", "description",
            "description_de", "description_en", "resource_pool", "pool_name",
            "products", "product_count",
        ]


class SectionManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for admin section ("Sparte") management.

    ``categories`` is the set of categories grouped under this section (M2M).
    """

    translated_fields = ("title", "description")

    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Category.objects.all(), required=False
    )
    category_count = serializers.IntegerField(
        source="categories.count", read_only=True
    )
    sets = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ProductSet.objects.all(), required=False
    )
    # Set via the dedicated multipart upload action, not via JSON.
    image = serializers.ImageField(read_only=True)
    # Managed via the dedicated reorder action; new entries are appended.
    position = serializers.IntegerField(read_only=True)

    class Meta:
        model = Section
        fields = [
            "id", "title", "title_de", "title_en", "description",
            "description_de", "description_en", "image", "categories",
            "category_count", "sets", "position",
        ]

    def to_representation(self, instance):
        # Return categories and sets in their saved manual order so the editor
        # can render and reorder them.
        data = super().to_representation(instance)
        for field, order in (
            ("categories", instance.category_order),
            ("sets", instance.set_order),
        ):
            rank = {oid: i for i, oid in enumerate(order or [])}
            data[field] = sorted(
                data.get(field, []), key=lambda oid: rank.get(oid, len(rank))
            )
        return data

    def _store_orders(self, instance, categories, sets):
        update = []
        if categories is not None:
            instance.category_order = [c.pk for c in categories]
            update.append("category_order")
        if sets is not None:
            instance.set_order = [s.pk for s in sets]
            update.append("set_order")
        if update:
            instance.save(update_fields=update)

    def create(self, validated_data):
        categories = validated_data.get("categories", [])
        sets = validated_data.get("sets", [])
        instance = super().create(validated_data)
        self._store_orders(instance, categories, sets)
        return instance

    def update(self, instance, validated_data):
        categories = validated_data.get("categories", None)
        sets = validated_data.get("sets", None)
        instance = super().update(instance, validated_data)
        self._store_orders(instance, categories, sets)
        return instance


class ProductManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for the admin product management UI."""

    translated_fields = ("title", "description", "short_description", "return_info")

    product_type_name = serializers.CharField(
        source="product_type.name", read_only=True
    )
    resource_count = serializers.IntegerField(source="resources.count", read_only=True)
    # Categories this product belongs to — assignable from the product side
    # (reverse of Category.products).
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Category.objects.all(), required=False
    )
    # Gallery managed via the dedicated multipart `images` actions, not via JSON.
    # `image` is the cover (first image) for the list thumbnail; `images` is the
    # full ordered gallery.
    image = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "title", "title_de", "title_en", "description",
            "description_de", "description_en", "short_description",
            "short_description_de", "short_description_en", "return_info",
            "return_info_de", "return_info_en", "image", "images",
            "product_type", "product_type_name", "lending_type", "min_duration",
            "max_duration", "min_gap", "missing_notice_lead",
            "attributes", "categories", "resource_count",
        ]

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def _clean_attributes(self, product_type, attributes):
        """Keep only schema-defined keys, normalise values, enforce required.
        Free-text values are stored as ``{de,en}`` (issue #6); required is met
        when the canonical language is filled."""
        if not isinstance(attributes, dict):
            raise serializers.ValidationError(
                {"attributes": "Must be an object of attribute values."}
            )
        default_lang = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
        cleaned, errors = {}, {}
        for attr in product_type.attribute_schema or []:
            key = attr["key"]
            value = _normalize_attr_value(attr, attributes.get(key, attr.get("default", "")))
            # PDF attributes are uploaded via a separate multipart endpoint, so
            # the JSON value may legitimately be empty at save time — don't
            # enforce "required" here for them.
            if attr.get("required") and attr.get("type") != "pdf":
                if attr.get("type") in _TEXT_ATTR_TYPES:
                    missing = not (value.get(default_lang) or "").strip()
                else:
                    missing = value is None or value == ""
                if missing:
                    label = resolve_translated_text(attr.get("label")) or key
                    errors[key] = f"'{label}' is required."
            cleaned[key] = value
        if errors:
            raise serializers.ValidationError({"attributes": errors})
        return cleaned

    def validate(self, attrs):
        # Attribute values must match the (possibly newly chosen) product type.
        product_type = attrs.get("product_type") or getattr(
            self.instance, "product_type", None
        )
        attributes = attrs.get("attributes")
        if attributes is None and self.instance is not None:
            attributes = self.instance.attributes
        if product_type is not None and attributes is not None:
            attrs["attributes"] = self._clean_attributes(product_type, attributes)
        return super().validate(attrs)


class ResourcePoolSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Full read/write representation for the admin pool management UI."""

    translated_fields = (
        "name", "description", "address", "room", "directions", "email_note",
    )

    resource_count = serializers.IntegerField(source="resources.count", read_only=True)
    # Set via the dedicated multipart upload action, not via JSON.
    image = serializers.ImageField(read_only=True)
    # Access groups that grant access to this pool (reverse of
    # AccessGroup.pools). Read-only here — the assignment is edited on the
    # access-group side; shown so admins see a pool's visibility at a glance.
    access_groups = serializers.SerializerMethodField()

    class Meta:
        model = ResourcePool
        fields = [
            "id", "name", "name_de", "name_en", "pool_id", "description",
            "description_de", "description_en", "address", "address_de",
            "address_en", "room", "room_de", "room_en", "image",
            "directions", "directions_de", "directions_en", "phone", "email",
            "email_note", "email_note_de", "email_note_en",
            "notify_on_defect", "notify_on_cancellation", "require_booking_note",
            "opening_hours", "closed_weekdays",
            "lead_time_hours", "max_booking_months", "default_min_days",
            "default_max_days", "default_min_hours", "default_max_hours",
            "is_active", "resource_count", "access_groups",
            "position", "accent_color",
        ]

    # Read-only here — set via the reorder action, not direct edits.
    position = serializers.IntegerField(read_only=True)

    def get_access_groups(self, obj):
        return [{"id": g.id, "name": g.name} for g in obj.access_groups.all()]

    def validate_closed_weekdays(self, value):
        cleaned = []
        for day in value:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise serializers.ValidationError(
                    "Entries must be integers 0 (Mon) to 6 (Sun)."
                )
            if day not in cleaned:
                cleaned.append(day)
        return cleaned

    def validate_opening_hours(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Must be an object keyed by weekday (mon … sun)."
            )
        for key, ranges in value.items():
            if key not in _DAY_KEYS:
                raise serializers.ValidationError(
                    f"Unknown weekday '{key}'. Use mon, tue, wed, thu, fri, sat, sun."
                )
            if not isinstance(ranges, list):
                raise serializers.ValidationError(
                    f"'{key}' must be a list of [from, to] time pairs."
                )
            for pair in ranges:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise serializers.ValidationError(
                        f"Each range for '{key}' must be a [from, to] pair."
                    )
                start, end = str(pair[0]), str(pair[1])
                if not (_TIME_RE.match(start) and _TIME_RE.match(end)):
                    raise serializers.ValidationError(
                        f"Times for '{key}' must be in HH:MM 24h format."
                    )
                if start >= end:
                    raise serializers.ValidationError(
                        f"For '{key}', '{start}' must be before '{end}'."
                    )
        return value


class PoolDefectTicketSerializer(serializers.ModelSerializer):
    """Per-pool GitLab defect-ticket integration, edited by lenders in the
    lending area.

    The access token is write-only — it is never returned; a boolean reports
    only whether one is stored. On update, the token is set when a non-empty
    value is sent, cleared when an empty string is sent, and left untouched when
    the field is omitted entirely.
    """

    defect_gitlab_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    defect_gitlab_token_set = serializers.SerializerMethodField()

    class Meta:
        model = ResourcePool
        fields = [
            "id",
            "name",
            "defect_gitlab_url",
            "defect_gitlab_token",
            "defect_gitlab_token_set",
        ]
        read_only_fields = ["id", "name"]

    def get_defect_gitlab_token_set(self, obj) -> bool:
        return bool(obj.defect_gitlab_token)

    def update(self, instance, validated_data):
        if "defect_gitlab_token" in validated_data:
            # Empty string clears it; a value sets it; absent key keeps it.
            instance.defect_gitlab_token = validated_data.pop("defect_gitlab_token")
        return super().update(instance, validated_data)


class NotificationSettingSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Admin read/write of the custom reservation-email text (de/en)."""

    translated_fields = (
        "reservation_intro", "reservation_footer", "rescheduled_note",
        "cancellation_note", "reminder_note", "defect_note",
    )

    class Meta:
        model = NotificationSetting
        fields = [
            "reservation_intro", "reservation_intro_de", "reservation_intro_en",
            "reservation_footer", "reservation_footer_de", "reservation_footer_en",
            "rescheduled_note", "rescheduled_note_de", "rescheduled_note_en",
            "cancellation_note", "cancellation_note_de", "cancellation_note_en",
            "reminder_note", "reminder_note_de", "reminder_note_en",
            "defect_note", "defect_note_de", "defect_note_en",
        ]


class WelcomeSettingSerializer(serializers.ModelSerializer):
    """Admin read/write of the welcome page text; logo is read-only here
    (uploaded via the dedicated multipart endpoint)."""

    logo = serializers.SerializerMethodField()

    class Meta:
        model = WelcomeSetting
        fields = ["text", "logo"]

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class ShopSettingSerializer(serializers.ModelSerializer):
    """Admin read/write of the start-page display settings."""

    class Meta:
        model = ShopSetting
        fields = ["show_popular", "show_new_arrivals", "new_product_days"]

    def validate_new_product_days(self, value):
        if value > 3650:
            raise serializers.ValidationError("That's more than ten years.")
        return value


class TrashSettingSerializer(serializers.ModelSerializer):
    """Admin read/write of the trash retention window (#7)."""

    class Meta:
        model = TrashSetting
        fields = ["retention_days"]


class PageManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Admin CRUD for content pages (Imprint, Privacy, …)."""

    translated_fields = ("title", "body")

    class Meta:
        model = Page
        fields = [
            "id",
            "slug",
            "title",
            "title_de",
            "title_en",
            "body",
            "body_de",
            "body_en",
            "is_published",
            "show_in_footer",
            "footer_order",
            "updated_at",
        ]
        # footer_order is managed by the reorder action (drag/arrows in the
        # admin overview), not set directly on create/update.
        read_only_fields = ["updated_at", "footer_order"]


class PageLinkSerializer(serializers.ModelSerializer):
    """Public footer link: just enough to render the link, no body."""

    class Meta:
        model = Page
        fields = ["slug", "title"]


class PageDetailSerializer(serializers.ModelSerializer):
    """Public read of a single published page's Markdown body."""

    class Meta:
        model = Page
        fields = ["slug", "title", "body", "updated_at"]


class PoolCardSerializer(serializers.ModelSerializer):
    """Public, read-only pool card for the welcome page (no contact details)."""

    class Meta:
        model = ResourcePool
        fields = ["id", "name", "description", "room", "image", "position", "accent_color"]


class PoolDetailSerializer(serializers.ModelSerializer):
    """Public, read-only pool info page: where and when to pick things up
    (concept §1.5) — opening hours, address and contact, no admin-only fields."""

    class Meta:
        model = ResourcePool
        fields = [
            "id", "name", "description", "room", "image",
            "address", "directions", "phone", "email",
            "opening_hours", "closed_weekdays", "accent_color",
        ]
