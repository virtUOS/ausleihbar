# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Serializers for the borrower-facing catalog API."""
import re
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from accounts import roles
from accounts.models import AccessGroup
from accounts.eligibility import eligible_pool_ids, visible_products

from . import sets as set_helpers
from .inventory import default_qr_code_id
from .richtext import clean_rich, rich_plain_text

from .navigation import CategoryTree, ShopNavigation
from .models import (
    Category,
    Favorite,
    NotificationSetting,
    Page,
    Product,
    ProductImage,
    ProductSet,
    ProductSetImage,
    ProductSetItem,
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
      translation columns (e.g. two product types with no English name);
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


class RichHtmlFieldsMixin:
    """Sanitize the listed rich-HTML fields on write (#5) — the backend is the
    security boundary for everything the rich-text editor sends."""

    rich_fields: tuple = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for key in self.rich_fields:
            if key in attrs and attrs[key] is not None:
                attrs[key] = clean_rich(attrs[key])
        return attrs


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ATTR_TYPES = {
    "short_text", "long_text", "date", "time", "number", "url", "media", "image",
    "pdf",
}
_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
# ``url`` attribute values must be web links (no javascript:/data: etc.).
_URL_SCHEME_RE = re.compile(r"^https?://\S", re.IGNORECASE)


def is_web_url(value):
    """True if ``value`` is a string starting with http:// or https://."""
    return isinstance(value, str) and bool(_URL_SCHEME_RE.match(value.strip()))


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


# Attribute types that can be filled in per device (scope "device", #106).
DEVICE_ATTR_TYPES = {"short_text", "long_text", "date", "time", "number", "url"}


def product_attributes(schema):
    """Schema entries that belong to the product (scope "product", default)."""
    return [a for a in (schema or []) if a.get("scope", "product") != "device"]


def device_attributes(schema):
    """Schema entries that are filled in per device (scope "device")."""
    return [a for a in (schema or []) if a.get("scope") == "device"]


def clean_attribute_values(schema_entries, attributes, skip_required_types=(), stored=None):
    """Keep only the keys of ``schema_entries``, normalise values, enforce
    ``required``. Free-text values are stored as ``{de,en}`` (issue #6) and
    count as filled when the canonical language is. Types in
    ``skip_required_types`` (e.g. pdf, uploaded separately) are not enforced.
    ``url`` values must be http(s) links unless unchanged from ``stored`` (the
    instance's current values), so legacy schemeless values stay saveable.
    Raises ``ValidationError({"attributes": ...})``."""
    stored = stored if isinstance(stored, dict) else {}
    if not isinstance(attributes, dict):
        raise serializers.ValidationError(
            {"attributes": "Must be an object of attribute values."}
        )
    default_lang = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    cleaned, errors = {}, {}
    for attr in schema_entries:
        key = attr["key"]
        value = _normalize_attr_value(attr, attributes.get(key, attr.get("default", "")))
        if attr.get("required") and attr.get("type") not in skip_required_types:
            if attr.get("type") in _TEXT_ATTR_TYPES:
                missing = not (value.get(default_lang) or "").strip()
            else:
                missing = value is None or value == ""
            if missing:
                label = resolve_translated_text(attr.get("label")) or key
                errors[key] = f"'{label}' is required."
        if (
            attr.get("type") == "url"
            and value not in (None, "")
            and value != stored.get(key)
            and not is_web_url(value)
        ):
            label = resolve_translated_text(attr.get("label")) or key
            errors[key] = f"'{label}' must be an http:// or https:// URL."
        cleaned[key] = value
    if errors:
        raise serializers.ValidationError({"attributes": errors})
    return cleaned


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
    scope = attr.get("scope") or "product"
    if scope not in ("product", "device"):
        raise ValueError(f"invalid scope '{scope}'")
    if scope == "device" and attr_type not in DEVICE_ATTR_TYPES:
        raise ValueError(f"type '{attr_type}' can't be filled in on the device")
    return {
        "key": key,
        "label": _clean_label(attr.get("label")),
        "type": attr_type,
        "scope": scope,
        "default": attr.get("default", ""),
        "visible": False if scope == "device" else bool(attr.get("visible", True)),
        "required": bool(attr.get("required", False)),
    }


class ProductImageSerializer(serializers.ModelSerializer):
    """One gallery image of a product."""

    class Meta:
        model = ProductImage
        fields = ["id", "image", "position"]


class ProductSetImageSerializer(serializers.ModelSerializer):
    """One gallery image of a set (#93 follow-up)."""

    class Meta:
        model = ProductSetImage
        fields = ["id", "image", "position"]


def _cover_url(product, request=None):
    """Absolute URL of a product's (or set's) cover — the first gallery
    image — or None. Prefetch ``images`` when serializing many.

    Built against the request so it matches DRF's ImageField output (absolute),
    which the SPA needs because the API host differs from the shop in dev.
    """
    first = product.images.all().first()
    if not (first and first.image):
        return None
    url = first.image.url
    return request.build_absolute_uri(url) if request else url


def new_product_cutoff(context):
    """The "new product" cutoff (``None`` = feature off), loaded from
    ``ShopSetting`` once and memoised in the serializer context."""
    if "_new_product_cutoff" not in context:
        days = ShopSetting.load().new_product_days
        context["_new_product_cutoff"] = (
            timezone.now() - timedelta(days=days) if days > 0 else None
        )
    return context["_new_product_cutoff"]


class ProductBriefSerializer(serializers.ModelSerializer):
    """Compact product representation for lists and cards."""

    image = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "short_description", "image", "lending_type",
            "use_type", "is_new",
        ]

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
            # Also memoised in the shared context, so the many product lists of
            # a grouped response (one per product type) load the setting once.
            cutoff = new_product_cutoff(self.context)
        self._new_cutoff = cutoff
        return bool(cutoff and obj.created_at >= cutoff)


def order_by_ids(items, ordered_ids):
    """Sort an iterable of objects by an explicit list of ids; items whose id is
    not listed keep their incoming order, after the listed ones. Used for the
    manual ordering of products-in-type, and product types/sets-in-section."""
    rank = {oid: i for i, oid in enumerate(ordered_ids or [])}
    return sorted(items, key=lambda obj: rank.get(obj.id, len(rank)))


def _request_user(context):
    request = context.get("request")
    return request.user if request else None


def _context_pool_ids(context):
    """``eligible_pool_ids`` of the requester, computed once per serialization
    and memoised in the (shared) serializer context."""
    if "_eligible_pool_ids" not in context:
        context["_eligible_pool_ids"] = eligible_pool_ids(_request_user(context))
    return context["_eligible_pool_ids"]


def shop_navigation(context):
    """The request's ``ShopNavigation`` (category tree + visible product
    links), built once and memoised in the shared serializer context, so
    serializing many sections/categories adds no per-item queries (#63)."""
    if "_shop_navigation" not in context:
        context["_shop_navigation"] = ShopNavigation(
            _request_user(context), _context_pool_ids(context)
        )
    return context["_shop_navigation"]


class CategoryBriefSerializer(serializers.ModelSerializer):
    """A category's own display fields (image as an absolute URL)."""

    class Meta:
        model = Category
        fields = ["id", "name", "description", "image"]


def child_filter_entry(cid, nav):
    """A subcategory as a filter chip: visible products of its whole subtree
    (``product_count``) and their ids (``product_ids``, sorted), likewise its
    visible sets (``set_count`` / ``set_ids``)."""
    ids = sorted(nav.product_ids(cid))
    set_ids = sorted(nav.set_ids(cid))
    return {
        "id": cid,
        "name": nav.tree.nodes[cid].name,
        "product_count": len(ids),
        "product_ids": ids,
        "set_count": len(set_ids),
        "set_ids": set_ids,
    }


def category_group(category, context, nav, with_products=True, with_children=False):
    """A category as a shop group: its fields, ``product_count`` (visible
    products of its whole subtree, deduplicated), ``set_count`` (likewise its
    visible sets), ``child_count`` (live subcategories) and — unless
    ``with_products`` is off — those products in shop order
    (``ShopNavigation.ordered_products``) and those sets by name (``sets``,
    set cards). ``with_children`` adds ``children``: the direct shown
    subcategories as filter entries (``child_filter_entry``). Preload the
    products and sets first (``nav.preload``)."""
    data = CategoryBriefSerializer(category, context=context).data
    data["product_count"] = nav.count(category.id)
    data["set_count"] = nav.set_count(category.id)
    shown = nav.shown_children(category.id)
    data["child_count"] = len(shown)
    if with_children:
        data["children"] = [child_filter_entry(cid, nav) for cid in shown]
    if with_products:
        new_product_cutoff(context)  # resolve once in the shared context
        data["products"] = ProductBriefSerializer(
            nav.ordered_products(category.id), many=True, context=context
        ).data
        data["sets"] = SetBriefSerializer(
            nav.ordered_sets(category.id), many=True, context=context
        ).data
    return data


def _section_product_count(section, nav):
    found = set()
    for cid in nav.section_roots(section):
        found |= nav.product_ids(cid)
    return len(found)


def visible_section_sets(section, context):
    """The section's directly linked sets the requester may see — live, with
    an active pool they are eligible for (the rule ``ShopNavigation`` applies
    to category sets) — in the section's order. Prefetch ``sets``."""
    pool_ids = _context_pool_ids(context)
    return order_by_ids(
        (
            s for s in section.sets.all()
            if s.resource_pool_id in pool_ids and s.deleted_at is None
        ),
        section.set_order,
    )


def _section_set_count(section, context, nav):
    """Distinct visible sets the shopper finds in a section: its direct sets
    plus those of its categories' subtrees."""
    found = {s.id for s in visible_section_sets(section, context)}
    for cid in nav.section_roots(section):
        found |= nav.set_ids(cid)
    return len(found)


class SectionListSerializer(serializers.ModelSerializer):
    """Start-page card of a section. Prefetch ``categories``; counts come from
    the request's ``ShopNavigation`` (no per-section query, #63)."""

    category_count = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    set_count = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            "id", "title", "description", "image", "category_count",
            "product_count", "set_count",
        ]

    def get_category_count(self, obj):
        return len(shop_navigation(self.context).section_roots(obj))

    def get_product_count(self, obj):
        """Distinct products the requester may see across the subtrees of
        this section's categories — what the shopper will find inside."""
        return _section_product_count(obj, shop_navigation(self.context))

    def get_set_count(self, obj):
        """Distinct visible sets (direct and in the categories' subtrees)."""
        return _section_set_count(obj, self.context, shop_navigation(self.context))


class SectionDetailSerializer(serializers.ModelSerializer):
    """Section with its top-level categories as shop groups (prefetch
    ``categories`` and ``sets__products``). Callers serializing several
    sections should ``preload`` all their categories on the shared
    ``shop_navigation`` first (one product query in total)."""

    categories = serializers.SerializerMethodField()
    sets = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ["id", "title", "description", "image", "categories", "sets"]

    def get_categories(self, obj):
        nav = shop_navigation(self.context)
        roots = nav.section_roots(obj)
        nav.preload(roots)
        return [
            category_group(nav.tree.nodes[cid], self.context, nav, with_children=True)
            for cid in roots
        ]

    def get_sets(self, obj):
        """The section's directly linked sets the requester may see (live,
        active and eligible pool) as set cards, in its order."""
        return SetBriefSerializer(
            visible_section_sets(obj, self.context), many=True, context=self.context
        ).data


class PoolBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourcePool
        fields = [
            "id", "name", "address", "room", "lead_time_hours",
            "max_booking_months", "accent_color",
        ]


def _eligible_pools(product, request):
    """Pools holding a resource of ``product``, position-ordered (#6), limited to
    the pools the requesting user may access."""
    pools = ResourcePool.objects.filter(resources__product=product).distinct().order_by(
        "position", "name"
    )
    if request:
        pools = pools.filter(id__in=eligible_pool_ids(request.user))
    return pools


def _bookable_pools(product, pool_ids=None):
    """Pools where ``product`` has a *bookable* unit — an AVAILABLE, non-trashed
    ``Resource`` — position-ordered, optionally limited to ``pool_ids``.

    Used for complementary devices (#23): unlike the parent product's own
    ``pools`` (any resource, any status — a separate follow-up), a complement's
    pool chips must match the shop's visibility rule, so only pools it could
    actually be picked up from are listed. All resource conditions are kept in
    one ``.filter()`` call so they're checked against the same resource row.
    """
    pools = ResourcePool.objects.filter(
        resources__product=product,
        resources__status=Resource.Status.AVAILABLE,
        resources__deleted_at__isnull=True,
    ).distinct().order_by("position", "name")
    if pool_ids is not None:
        pools = pools.filter(id__in=pool_ids)
    return pools


class ProductDetailSerializer(serializers.ModelSerializer):
    product_type_name = serializers.CharField(source="product_type.name", read_only=True)
    visible_attributes = serializers.SerializerMethodField()
    pools = serializers.SerializerMethodField()
    sets = serializers.SerializerMethodField()
    effective_min_duration = serializers.SerializerMethodField()
    effective_max_duration = serializers.SerializerMethodField()
    duration_limits_by_pool = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    complementary_products = serializers.SerializerMethodField()
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
            "use_type",
            "requires_handout",
            "min_duration",
            "max_duration",
            "product_type_name",
            "visible_attributes",
            "pools",
            "sets",
            "effective_min_duration",
            "effective_max_duration",
            "duration_limits_by_pool",
            "is_favorite",
            "complementary_products",
        ]

    def get_is_favorite(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return Favorite.objects.filter(user=user, product=obj).exists()

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def _duration_limits(self, obj):
        """Per-pool and overall effective lending-duration limits (#109).

        Each bookable unit in a pool the requester may use resolves device →
        product → pool default; a pool shows the widest range of its units and
        the overall range is the widest over all pools (the page isn't
        pool-specific; the cart then picks a unit that fits). Without bookable
        units the product's own values apply. ``None`` = no limit. Computed
        once per product in a constant number of queries.
        """
        cache = self.__dict__.setdefault("_duration_cache", {})
        if obj.pk not in cache:
            from lending.durations import bookable_limits_by_pool, widest

            rows = bookable_limits_by_pool(obj, self._eligible_pool_ids)
            if rows:
                overall = widest((r["min"], r["max"]) for r in rows)
            else:
                overall = (obj.min_duration or None, obj.max_duration or None)
            cache[obj.pk] = (overall, rows)
        return cache[obj.pk]

    def get_effective_min_duration(self, obj):
        return self._duration_limits(obj)[0][0]

    def get_effective_max_duration(self, obj):
        """Maximum lending duration in the lending-type unit, with inheritance
        (widest over the bookable pools; ``None`` = not limited)."""
        return self._duration_limits(obj)[0][1]

    def get_duration_limits_by_pool(self, obj):
        return self._duration_limits(obj)[1]

    def get_sets(self, obj):
        return [
            {"id": s.id, "name": s.name} for s in obj.product_sets.all()
        ]

    def get_visible_attributes(self, obj):
        """Join the product type's schema with the product's values.

        Only attributes flagged ``visible`` are exposed to borrowers.
        """
        schema = product_attributes(obj.product_type.attribute_schema)
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
        return PoolBriefSerializer(
            _eligible_pools(obj, self.context.get("request")), many=True
        ).data

    @property
    def _eligible_pool_ids(self):
        # Computed once per serializer instance (M1) — reused for both the
        # complements gate and each complement's pool chips, instead of
        # recomputing eligibility per complement. ``None`` when there's no
        # request, matching ``get_pools``' no-request (no-filter) behaviour.
        if not hasattr(self, "_eligible_pool_ids_cache"):
            request = self.context.get("request")
            self._eligible_pool_ids_cache = (
                eligible_pool_ids(request.user) if request else None
            )
        return self._eligible_pool_ids_cache

    def get_complementary_products(self, obj):
        # Complementary devices (#23): curated order, gated by the same shop
        # visibility rule as any other product (visible_products — a bookable
        # unit in a pool this user may access), each with the pools they can
        # actually pick a unit up from (bookable units only). No availability.
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        pool_ids = self._eligible_pool_ids
        complements = obj.complementary_products.select_related(
            "product_type"
        ).prefetch_related("images")
        if request:
            complements = visible_products(complements, user, pool_ids=pool_ids)
        items = order_by_ids(complements, obj.complementary_order)
        rows = []
        for product in items:
            pools = _bookable_pools(product, pool_ids)
            if not pools.exists():
                continue
            rows.append({
                "id": product.id,
                "title": product.title,
                "short_description": product.short_description,
                # Thumbnail (cover image) + type for the emoji fallback.
                "image": _cover_url(product, request),
                "product_type_name": product.product_type.name,
                "pools": PoolBriefSerializer(pools, many=True).data,
            })
        return rows


class SetBriefSerializer(serializers.ModelSerializer):
    """A set card (#93 follow-up): cover ``image``, ``description_text``
    (the rich description as plain text, for the excerpt), the live items as
    ``{product: {id, title}, quantity}`` and ``item_count`` (sum of the
    quantities). Prefetch ``items__product`` and ``images``."""

    item_count = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    description_text = serializers.SerializerMethodField()

    class Meta:
        model = ProductSet
        fields = [
            "id", "name", "image", "description_text", "item_count", "items",
        ]

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.ordered_items())

    def get_items(self, obj):
        return [
            {
                "product": {"id": item.product_id, "title": item.product.title},
                "quantity": item.quantity,
            }
            for item in obj.ordered_items()
        ]

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def get_description_text(self, obj):
        return rich_plain_text(obj.description)


class SetDetailSerializer(serializers.ModelSerializer):
    """A set with its products, its pool and derived duration limits.

    ``items`` lists each product (brief) with the quantity the set needs, in
    the set's order (#93). ``description`` is rich HTML.
    ``image`` is the cover, ``images`` the ordered gallery.
    """

    items = serializers.SerializerMethodField()
    lending_type = serializers.SerializerMethodField()
    min_duration = serializers.SerializerMethodField()
    max_duration = serializers.SerializerMethodField()
    # Same values as min/max_duration, named like the product detail (#109).
    effective_min_duration = serializers.SerializerMethodField()
    effective_max_duration = serializers.SerializerMethodField()
    pool = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    images = ProductSetImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductSet
        fields = [
            "id", "name", "description", "image", "images", "items",
            "lending_type", "min_duration", "max_duration",
            "effective_min_duration", "effective_max_duration", "pool",
        ]

    def _lines(self, obj):
        cache = self.__dict__.setdefault("_lines_cache", {})
        if obj.pk not in cache:
            items = obj.ordered_items()
            briefs = ProductBriefSerializer(
                [i.product for i in items], many=True, context=self.context
            ).data
            cache[obj.pk] = (items, briefs)
        return cache[obj.pk]

    def _products(self, obj):
        return [i.product for i in self._lines(obj)[0]]

    def get_items(self, obj):
        items, briefs = self._lines(obj)
        return [
            {"product": brief, "quantity": item.quantity}
            for item, brief in zip(items, briefs)
        ]

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def get_lending_type(self, obj):
        return set_helpers.set_lending_type(self._products(obj))

    def _durations(self, obj):
        # Effective limits in the set's pool; the most restricted product drives.
        cache = self.__dict__.setdefault("_durations_cache", {})
        if obj.pk not in cache:
            cache[obj.pk] = set_helpers.set_durations(
                self._products(obj), obj.resource_pool_id
            )
        return cache[obj.pk]

    def get_min_duration(self, obj):
        return self._durations(obj)[0]

    def get_max_duration(self, obj):
        return self._durations(obj)[1]

    get_effective_min_duration = get_min_duration
    get_effective_max_duration = get_max_duration

    def get_pool(self, obj):
        """The set's pool, only if the requester may access it."""
        pool = obj.resource_pool
        if pool is None:
            return None
        request = self.context.get("request")
        if request and pool.id not in eligible_pool_ids(request.user):
            return None
        return PoolBriefSerializer(pool).data


def _attr_filled(attr, value):
    """True if a stored attribute value counts as non-empty."""
    if attr.get("type") in _TEXT_ATTR_TYPES and isinstance(value, dict):
        return any((v or "").strip() for v in value.values())
    return value not in (None, "", [], {})


def _move_product_values_to_devices(product_type, attrs, copy_keys):
    """A property moved from product to device scope: seed every empty device
    value with its product's value (only for ``copy_keys``, i.e. an unchanged
    type), then drop the key from the products so a later switch back starts
    empty (#106)."""
    for product in product_type.products.prefetch_related("resources"):
        product_values = dict(product.attributes or {})
        for attr in attrs:
            key = attr["key"]
            value = product_values.get(key)
            if key in copy_keys and _attr_filled(attr, value):
                value = _normalize_attr_value(attr, value)
                for resource in product.resources.all():
                    current = resource.attributes or {}
                    if _attr_filled(attr, current.get(key)):
                        continue
                    resource.attributes = {**current, key: value}
                    resource.save(update_fields=["attributes", "updated_at"])
        removed = [a["key"] for a in attrs if a["key"] in product_values]
        if removed:
            for key in removed:
                product_values.pop(key)
            product.attributes = product_values
            product.save(update_fields=["attributes", "updated_at"])


class ProductTypeSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for the admin product-type management UI."""

    translated_fields = ("name", "description")

    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = ProductType
        fields = [
            "id", "name", "name_de", "name_en", "description",
            "description_de", "description_en", "attribute_schema",
            "product_count",
        ]

    def update(self, instance, validated_data):
        old_schema = instance.attribute_schema or []
        old_scopes = {a["key"]: a.get("scope", "product") for a in old_schema}
        old_types = {a["key"]: a.get("type") for a in old_schema}
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            moved = [
                a for a in device_attributes(instance.attribute_schema)
                if old_scopes.get(a["key"]) == "product"
            ]
            if moved:
                same_type = {
                    a["key"] for a in moved if old_types.get(a["key"]) == a.get("type")
                }
                _move_product_values_to_devices(instance, moved, same_type)
        return instance

    def validate_attribute_schema(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Must be a list of attribute definitions."
            )
        seen = set()
        cleaned = []
        fixed_fields = {f.name for f in Resource._meta.get_fields() if f.concrete}
        for index, attr in enumerate(value, start=1):
            try:
                entry = normalize_attribute(attr)
            except ValueError as exc:
                raise serializers.ValidationError(f"Attribute #{index}: {exc}")
            if entry["scope"] == "device" and entry["key"] in fixed_fields:
                raise serializers.ValidationError(
                    f"Attribute #{index}: key '{entry['key']}' is a fixed device field."
                )
            if entry["key"] in seen:
                raise serializers.ValidationError(f"Duplicate key '{entry['key']}'.")
            seen.add(entry["key"])
            cleaned.append(entry)
        return cleaned


class ResourceManageSerializer(serializers.ModelSerializer):
    """Read/write representation for the admin inventory (resource) UI."""

    product_title = serializers.CharField(source="product.title", read_only=True)
    pool_name = serializers.CharField(source="resource_pool.name", read_only=True)
    product_type = serializers.IntegerField(source="product.product_type_id", read_only=True)
    lent_until = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = [
            "id", "product", "product_title", "product_type", "resource_pool", "pool_name",
            "lent_until", "overdue",
            "inventory_number", "qr_code_id", "status", "defect_note",
            "condition_rating", "condition_note",
            "storage_location", "procurement_date", "warranty_end", "value",
            "procuring_institution", "owning_institution",
            "serial_number", "attributes",
            # Own lending-duration limits (#109); empty = inherit.
            "min_duration", "max_duration",
        ]
        # #50: the QR code ID is assigned automatically when left empty; it
        # stays editable for existing third-party labels.
        extra_kwargs = {"qr_code_id": {"required": False, "allow_blank": True}}

    def get_lent_until(self, obj):
        """End of the current handed-out appointment, else None. The list
        annotates it; other responses fall back to one query."""
        if not hasattr(obj, "lent_until"):
            from lending.models import BookingItem

            item = (
                BookingItem.objects.filter(
                    resource=obj, is_active=True,
                    handed_out_at__isnull=False, returned_at__isnull=True,
                ).order_by("-handed_out_at").first()
            )
            obj.lent_until = item.period.upper if item else None
        value = obj.lent_until
        return serializers.DateTimeField().to_representation(value) if value else None

    def get_overdue(self, obj):
        value = getattr(obj, "lent_until", None)
        if value is None:
            self.get_lent_until(obj)
            value = obj.lent_until
        # Same rule as the day overview: past the end of its last day.
        return value is not None and (
            timezone.localtime(value - timedelta(microseconds=1)).date()
            < timezone.localdate()
        )

    def validate_qr_code_id(self, value):
        return (value or "").strip()

    def validate(self, attrs):
        # Device property values must match the (possibly newly chosen)
        # product's type (#106).
        product = attrs.get("product") or getattr(self.instance, "product", None)
        attributes = attrs.get("attributes")
        if attributes is None and self.instance is not None and (
            "product" in attrs and attrs["product"] != self.instance.product
        ):
            attributes = self.instance.attributes  # re-check against a new product
        if attributes is None and self.instance is None and product is not None:
            attributes = {}  # enforce required device properties on create
        if product is not None and attributes is not None:
            attrs["attributes"] = clean_attribute_values(
                device_attributes(product.product_type.attribute_schema), attributes,
                stored=getattr(self.instance, "attributes", None),
            )
        low = attrs.get("min_duration", getattr(self.instance, "min_duration", None))
        high = attrs.get("max_duration", getattr(self.instance, "max_duration", None))
        if low and high and low > high:
            raise serializers.ValidationError(
                {"min_duration": "The minimum duration can't exceed the maximum."}
            )
        self._validate_effective_limits(attrs, low, high)
        return super().validate(attrs)

    def _validate_effective_limits(self, attrs, low, high):
        """Reject a device whose *effective* min exceeds its effective max
        (#109) — e.g. an own max of 3 days below the product's min of 5 —
        which would make it unbookable."""
        from types import SimpleNamespace

        from lending.durations import effective_limits_detail, format_range, lending_unit

        product = attrs.get("product") or getattr(self.instance, "product", None)
        pool = attrs.get("resource_pool") or getattr(self.instance, "resource_pool", None)
        if product is None or pool is None:
            return
        detail = effective_limits_detail(
            SimpleNamespace(min_duration=low, max_duration=high), product, pool
        )
        (eff_min, min_source), (eff_max, max_source) = detail["min"], detail["max"]
        if eff_min and eff_max and eff_min > eff_max:
            unit = lending_unit(product.lending_type)
            sources = {
                "resource": "this device", "product": "the product",
                "pool": "the pool's default",
            }
            raise serializers.ValidationError({
                "min_duration" if min_source == "resource" else "max_duration": (
                    f"The effective minimum lending duration "
                    f"({format_range(eff_min, eff_min, unit)}, from "
                    f"{sources[min_source]}) exceeds the effective maximum "
                    f"({format_range(eff_max, eff_max, unit)}, from "
                    f"{sources[max_source]}); the device could never be booked."
                )
            })

    def to_representation(self, instance):
        """Adds the effective limits and where they come from (#109):
        ``effective_(min|max)_duration`` + ``…_source`` (resource | product |
        pool | none), ``inherited_(min|max)_duration`` + ``…_source`` (what
        applies without the device's own value) and ``lending_unit``."""
        from lending.durations import effective_limits_detail, lending_unit

        data = super().to_representation(instance)
        detail = effective_limits_detail(instance)
        data["lending_unit"] = lending_unit(instance.product.lending_type)
        for key, prefix in (
            ("min", "effective_min_duration"), ("max", "effective_max_duration"),
            ("inherited_min", "inherited_min_duration"),
            ("inherited_max", "inherited_max_duration"),
        ):
            data[prefix], data[f"{prefix}_source"] = detail[key]
        return data

    def create(self, validated_data):
        if not validated_data.get("qr_code_id"):
            validated_data["qr_code_id"] = default_qr_code_id(
                validated_data.get("inventory_number", "")
            )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Never clear an ID: printed labels depend on it.
        if "qr_code_id" in validated_data and not validated_data["qr_code_id"]:
            validated_data.pop("qr_code_id")
        return super().update(instance, validated_data)


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


def validate_pickable_categories(value):
    """A ``categories`` write may only name pickable categories: live ones
    (the PK field already rejects trashed ones) not below a trashed ancestor
    — those are unreachable in the shop. Returns them deduplicated."""
    tree = CategoryTree()
    hidden = [c.name for c in value if c.id not in tree]
    if hidden:
        raise serializers.ValidationError(
            "These categories sit below a trashed category: " + ", ".join(hidden)
        )
    return list(dict.fromkeys(value))


def store_categories(instance, categories, related_name):
    """Replace ``instance.categories`` by ``categories``, keeping the links to
    unpickable categories (trashed, or below a trashed one) — restoring such a
    category brings the product/set back with it. ``related_name`` is the
    reverse accessor on ``Category`` (``products`` / ``product_sets``)."""
    tree = CategoryTree()
    kept = [
        c for c in Category.all_objects.filter(**{related_name: instance})
        if c.id not in tree
    ]
    instance.categories.set(list(dict.fromkeys([*categories, *kept])))


class ProductSetItemInputSerializer(serializers.Serializer):
    """One ``{product, quantity}`` entry of a set's ``items`` (#93)."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1, max_value=999, default=1)


def set_units_by_pool(product_sets):
    """``{(pool_id, product_id): n}`` for the items of many sets in one
    grouped query — the manage list's ``units_in_pool`` (see
    ``set_units_in_pool`` for what counts)."""
    pool_ids, product_ids = set(), set()
    for product_set in product_sets:
        if product_set.resource_pool_id is None:
            continue
        pool_ids.add(product_set.resource_pool_id)
        product_ids.update(i.product_id for i in product_set.ordered_items())
    if not pool_ids or not product_ids:
        return {}
    rows = (
        Resource.objects.filter(
            resource_pool_id__in=pool_ids, product_id__in=product_ids
        )
        .exclude(status=Resource.Status.RETIRED)
        .values("resource_pool_id", "product_id")
        .annotate(n=Count("id"))
    )
    return {(r["resource_pool_id"], r["product_id"]): r["n"] for r in rows}


class ProductSetManageListSerializer(serializers.ListSerializer):
    """Counts the units in pool for a whole page at once (no per-row query)."""

    def to_representation(self, data):
        objs = list(data.all() if hasattr(data, "all") else data)
        self.child._units_by_pool = set_units_by_pool(objs)
        return super().to_representation(objs)


def set_units_in_pool(product_ids, pool_id):
    """``{product_id: n}`` — units of these products in ``pool_id`` that count
    for a set (#93): every live unit that is not retired (available, blocked
    and defective ones count). Products without such a unit are missing."""
    if pool_id is None or not product_ids:
        return {}
    rows = (
        Resource.objects.filter(resource_pool_id=pool_id, product_id__in=product_ids)
        .exclude(status=Resource.Status.RETIRED)
        .values("product_id")
        .annotate(n=Count("id"))
    )
    return {row["product_id"]: row["n"] for row in rows}


class ProductSetManageSerializer(
    RichHtmlFieldsMixin, TranslatedFieldsMixin, serializers.ModelSerializer
):
    """Read/write representation for admin set management (concept §5.5).

    A set is a list of products lent together from one pool (#93):

    * ``resource_pool`` is required on create and update (older sets without
      one stay readable);
    * ``items`` — ``[{product, quantity}]`` in display order; a write replaces
      them all. On read each item also carries ``title`` and
      ``units_in_pool`` (non-retired units of the product in the set's pool).
      Every product needs at least one such unit, no duplicates, quantity ≥ 1;
      A quantity may not exceed those units (#93 follow-up);
    * ``products`` (read-only) — the product ids in item order;
    * ``categories`` — shop categories (ids, any depth), validated like a
      product's;
    * ``images`` (read-only) — the gallery, managed via the ``images/``
      actions; ``image`` is its cover. ``description`` is rich HTML.
    """

    translated_fields = ("name", "description")
    rich_fields = ("description", "description_de", "description_en")

    items = ProductSetItemInputSerializer(many=True, required=False, write_only=True)
    products = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    pool_name = serializers.CharField(
        source="resource_pool.name", read_only=True, default=None
    )
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Category.objects.all(), required=False
    )
    # Gallery managed via the multipart ``images`` actions, not via JSON.
    image = serializers.SerializerMethodField()
    images = ProductSetImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductSet
        fields = [
            "id", "name", "name_de", "name_en", "description",
            "description_de", "description_en", "image", "images",
            "categories", "resource_pool", "pool_name", "items", "products",
            "product_count",
        ]
        list_serializer_class = ProductSetManageListSerializer

    def validate_items(self, value):
        seen = set()
        for entry in value:
            product = entry["product"]
            if product.pk in seen:
                raise serializers.ValidationError(
                    _("“%(title)s” is listed more than once.") % {"title": product.title}
                )
            seen.add(product.pk)
        return value

    def validate_categories(self, value):
        return validate_pickable_categories(value)

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        if "resource_pool" in attrs:
            pool = attrs["resource_pool"]
        else:
            pool = instance.resource_pool if instance else None
        if pool is None:
            raise serializers.ValidationError(
                {"resource_pool": [_("Choose the pool the set is lent from.")]}
            )
        # Sets are shared, but a lender may only choose a pool they manage;
        # keeping a set's unchanged pool is fine.
        unchanged = instance is not None and instance.resource_pool_id == pool.pk
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            not unchanged
            and not roles.is_app_admin(user)
            and pool.pk not in roles.managed_pool_ids(user)
        ):
            raise serializers.ValidationError(
                {"resource_pool": [_("You can only choose a pool you manage.")]}
            )
        if "items" in attrs:
            lines = [
                (entry["product"], entry.get("quantity", 1)) for entry in attrs["items"]
            ]
        elif instance is not None:
            lines = [(item.product, item.quantity) for item in instance.ordered_items()]
        else:
            lines = []
        units = set_units_in_pool([p.pk for p, _q in lines], pool.pk)
        errors = []
        for product, quantity in lines:
            count = units.get(product.pk, 0)
            if not count:
                errors.append(
                    _("“%(title)s” has no device in the pool “%(pool)s”.")
                    % {"title": product.title, "pool": pool.name}
                )
            elif quantity > count:
                # The set can never be booked with more units than the pool
                # has (#93 follow-up) — same count as the form's "M im Pool".
                errors.append(
                    _("“%(title)s”: only %(count)s in the pool.")
                    % {"title": product.title, "count": count}
                )
        if errors:
            raise serializers.ValidationError({"items": errors})
        return attrs

    def _write_items(self, product_set, items):
        """Replace the items of live products by ``items`` (in that order).
        Items of trashed products are hidden from the form, so they are kept
        and appended after — restoring the product brings it back."""
        hidden = list(
            ProductSetItem.objects.filter(
                product_set=product_set, product__deleted_at__isnull=False
            ).order_by("position", "id")
        )
        ProductSetItem.objects.filter(
            product_set=product_set, product__deleted_at__isnull=True
        ).delete()
        ProductSetItem.objects.bulk_create(
            ProductSetItem(
                product_set=product_set,
                product=entry["product"],
                quantity=entry.get("quantity", 1),
                position=position,
            )
            for position, entry in enumerate(items)
        )
        for offset, item in enumerate(hidden):
            item.position = len(items) + offset
        ProductSetItem.objects.bulk_update(hidden, ["position"])

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        with transaction.atomic():
            product_set = super().create(validated_data)
            self._write_items(product_set, items)
        return product_set

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        categories = validated_data.pop("categories", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if categories is not None:
                store_categories(instance, categories, "product_sets")
            if items is not None:
                self._write_items(instance, items)
            instance._prefetched_objects_cache = {}
        return instance

    def _items(self, obj):
        cache = self.__dict__.setdefault("_items_cache", {})
        if obj.pk not in cache:
            cache[obj.pk] = obj.ordered_items()
        return cache[obj.pk]

    def get_products(self, obj):
        return [item.product_id for item in self._items(obj)]

    def get_product_count(self, obj):
        return len(self._items(obj))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        items = self._items(instance)
        pool_id = instance.resource_pool_id
        by_pool = getattr(self, "_units_by_pool", None)
        if by_pool is not None:
            units = {
                item.product_id: by_pool.get((pool_id, item.product_id), 0)
                for item in items
            }
        else:
            units = set_units_in_pool([item.product_id for item in items], pool_id)
        data["items"] = [
            {
                "product": item.product_id,
                "title": item.product.title,
                "quantity": item.quantity,
                "units_in_pool": units.get(item.product_id, 0),
            }
            for item in items
        ]
        return data


class CategoryManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for admin category management (#78).

    ``parent`` (null = top-level) is validated against cycles and trashed
    parents (``Category.validate_parent``); only top-level categories may sit
    in ``sections``. ``depth``/``path`` (names root → self) come from a
    ``CategoryTree`` in the context (the list view passes one, so rows cost
    no per-level queries) or, for a single object, from ``ancestors()``.
    ``products`` are the directly assigned products (``{id, title}``) in shop
    order;
    ``product_order`` takes only ids of those products.
    """

    translated_fields = ("name", "description")

    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), allow_null=True, required=False
    )
    sections = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Section.objects.all(), required=False
    )
    product_order = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    products = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    child_count = serializers.SerializerMethodField()
    depth = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    # Set via the dedicated multipart upload action, not via JSON.
    image = serializers.ImageField(read_only=True)
    # Managed via the dedicated reorder action; new entries are appended.
    position = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id", "name", "name_de", "name_en", "description",
            "description_de", "description_en", "image", "parent", "position",
            "depth", "path", "sections", "products", "product_order",
            "product_count", "child_count",
        ]
        # No auto-generated validators for the unique live-name constraints:
        # DRF ignores their conditions (parent IS NULL, not trashed) and
        # would make ``name`` required. The view turns the DB's
        # IntegrityError into a 400 instead.
        validators = []
        extra_kwargs = {
            field: {"validators": []} for field in ("name", "name_de", "name_en")
        }

    def _chain(self, obj):
        """Ancestor names, root first. The list view passes ``category_nodes``
        (every category incl. trashed, one query) so even rows below a
        trashed parent cost no per-level queries."""
        nodes = self.context.get("category_nodes")
        if nodes is None:
            return [c.name for c in obj.ancestors()]
        chain, seen = [], {obj.id}
        node = nodes.get(obj.parent_id)
        while node is not None and node.id not in seen:
            seen.add(node.id)
            chain.append(node.name)
            node = nodes.get(node.parent_id)
        return list(reversed(chain))

    def get_depth(self, obj):
        return len(self._chain(obj))

    def get_path(self, obj):
        return [*self._chain(obj), obj.name]

    def get_products(self, obj):
        rank = {pid: i for i, pid in enumerate(obj.product_order or [])}
        return [
            {"id": p.id, "title": p.title}
            for p in sorted(
                obj.products.all(),
                key=lambda p: (rank.get(p.id, len(rank)), p.title.casefold(), p.id),
            )
        ]

    def get_product_count(self, obj):
        return len(obj.products.all())

    def get_child_count(self, obj):
        return len(obj.children.all())

    def to_representation(self, instance):
        # Emit only ids of current direct products (the stored order may name
        # products that were trashed or unassigned since).
        data = super().to_representation(instance)
        current = {p.id for p in instance.products.all()}
        data["product_order"] = [
            pid for pid in data.get("product_order") or [] if pid in current
        ]
        return data

    def validate_product_order(self, value):
        allowed = (
            {p.id for p in self.instance.products.all()}
            if self.instance is not None
            else set()
        )
        return [pid for pid in dict.fromkeys(value) if pid in allowed]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as DjangoValidationError

        attrs = super().validate(attrs)
        instance = self.instance
        parent = attrs.get("parent", instance.parent if instance else None)
        if "parent" in attrs:
            node = instance or Category()
            try:
                node.validate_parent(parent)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"parent": exc.messages})
        if parent is not None:
            if "sections" in attrs:
                in_sections = bool(attrs["sections"])
            else:
                in_sections = bool(instance and instance.sections.exists())
            if in_sections:
                raise serializers.ValidationError(
                    {"sections": "Only top-level categories can be placed in a section."}
                )
        return attrs


class SectionManageSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for admin section ("Sparte") management.

    ``categories`` are the section's top-level categories (the shop
    navigation, #78), returned and stored in ``category_order``.
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

    def validate_categories(self, value):
        if any(c.parent_id is not None for c in value):
            raise serializers.ValidationError(
                "Only top-level categories can be placed in a section."
            )
        return list(dict.fromkeys(value))

    def to_representation(self, instance):
        # Return categories and sets in their saved manual
        # order so the editor can render and reorder them.
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

    _ORDER_FIELDS = (
        ("categories", "category_order"),
        ("sets", "set_order"),
    )

    def _store_orders(self, instance, items):
        update = []
        for field, order_field in self._ORDER_FIELDS:
            if items.get(field) is not None:
                setattr(instance, order_field, [obj.pk for obj in items[field]])
                update.append(order_field)
        if update:
            instance.save(update_fields=update)

    def create(self, validated_data):
        items = {f: validated_data.get(f, []) for f, _ in self._ORDER_FIELDS}
        instance = super().create(validated_data)
        self._store_orders(instance, items)
        return instance

    def update(self, instance, validated_data):
        items = {f: validated_data.get(f) for f, _ in self._ORDER_FIELDS}
        instance = super().update(instance, validated_data)
        self._store_orders(instance, items)
        return instance


class ProductManageSerializer(RichHtmlFieldsMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    """Read/write representation for the admin product management UI."""

    translated_fields = ("title", "description", "short_description", "return_info")
    rich_fields = (
        "description", "description_de", "description_en",
        "return_info", "return_info_de", "return_info_en",
    )

    product_type_name = serializers.CharField(
        source="product_type.name", read_only=True
    )
    resource_count = serializers.IntegerField(source="resources.count", read_only=True)
    # Complementary devices (#23) — written as an ordered id list; the order is
    # kept in ``complementary_order``. The link itself is symmetric.
    complementary_products = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Product.objects.all(), required=False
    )
    # Shop navigation (#78): the categories this product is listed in (ids,
    # any depth; a product may sit in several).
    categories = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Category.objects.all(), required=False
    )

    def validate_categories(self, value):
        return validate_pickable_categories(value)
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
            "product_type", "product_type_name", "lending_type", "use_type",
            "requires_handout", "min_duration",
            "max_duration", "min_gap", "missing_notice_lead",
            "attributes", "complementary_products", "categories",
            "resource_count", "pool_duration_defaults",
        ]

    # Per pool holding a unit of this product: its default min/max in the
    # product's lending unit (#109) — what "inherit from pool" resolves to.
    pool_duration_defaults = serializers.SerializerMethodField()

    def get_pool_duration_defaults(self, obj):
        from lending.durations import pool_defaults

        # Only active pools with bookable (available) units — the pools whose
        # defaults can actually apply.
        pools = {
            r.resource_pool for r in obj.resources.all()
            if r.status == Resource.Status.AVAILABLE and r.resource_pool.is_active
        }
        rows = []
        for pool in sorted(pools, key=lambda p: (p.position, p.name)):
            low, high = pool_defaults(pool, obj.lending_type)
            rows.append({"pool_id": pool.id, "pool_name": pool.name, "min": low, "max": high})
        return rows

    def get_image(self, obj):
        return _cover_url(obj, self.context.get("request"))

    def _clean_attributes(self, product_type, attributes):
        # PDF attributes are uploaded via a separate multipart endpoint, so
        # the JSON value may legitimately be empty at save time.
        schema = product_attributes(product_type.attribute_schema)
        # A pdf value is only ever written by the attribute-pdf upload
        # endpoint: via JSON only "" (clear) or the stored value is accepted,
        # never an arbitrary path (security review #1).
        stored = (getattr(self.instance, "attributes", None) or {}) if self.instance else {}
        # The stored pdf value only counts under the same product type: after a
        # type switch it may be a value of a differently typed attribute.
        same_type = (
            self.instance is not None
            and product_type.pk == self.instance.product_type_id
        )
        if isinstance(attributes, dict):
            errors = {}
            for attr in schema:
                key = attr["key"]
                if attr.get("type") != "pdf" or key not in attributes:
                    continue
                value = attributes[key]
                if value in (None, "") or (same_type and value == stored.get(key)):
                    continue
                label = resolve_translated_text(attr.get("label")) or key
                errors[key] = (
                    f"'{label}' can only be set by uploading a PDF"
                    " (clear it when changing the product type)."
                )
            if errors:
                raise serializers.ValidationError({"attributes": errors})
        return clean_attribute_values(
            schema, attributes, skip_required_types=("pdf",), stored=stored,
        )

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
        low = attrs.get("min_duration", getattr(self.instance, "min_duration", None))
        high = attrs.get("max_duration", getattr(self.instance, "max_duration", None))
        if low and high and low > high:
            raise serializers.ValidationError(
                {"min_duration": "The minimum duration can't exceed the maximum."}
            )
        return super().validate(attrs)

    def validate_complementary_products(self, value):
        seen, cleaned = set(), []
        for product in value:
            if self.instance is not None and product.pk == self.instance.pk:
                raise serializers.ValidationError("A product can't complement itself.")
            if product.pk not in seen:
                seen.add(product.pk)
                cleaned.append(product)
        return cleaned

    def to_representation(self, instance):
        # Sort exactly like the borrower path (order_by_ids on the same
        # queryset + order), so an unlisted id (e.g. linked from the other
        # side) sorts the same way here as on the product detail page (M4).
        data = super().to_representation(instance)
        data["complementary_products"] = [
            p.pk for p in order_by_ids(
                instance.complementary_products.all(), instance.complementary_order
            )
        ]
        return data

    def _store_complements(self, instance, items):
        instance.complementary_products.set(items)
        instance.complementary_order = [p.pk for p in items]
        instance.save(update_fields=["complementary_order"])

    def create(self, validated_data):
        items = validated_data.pop("complementary_products", None)
        instance = super().create(validated_data)
        if items is not None:
            self._store_complements(instance, items)
        return instance

    def update(self, instance, validated_data):
        items = validated_data.pop("complementary_products", None)
        categories = validated_data.pop("categories", None)
        instance = super().update(instance, validated_data)
        if items is not None:
            self._store_complements(instance, items)
        if categories is not None:
            store_categories(instance, categories, "products")
        return instance


class ResourcePoolSerializer(RichHtmlFieldsMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    """Full read/write representation for the admin pool management UI."""

    translated_fields = (
        "name", "description", "address", "room", "directions", "email_note",
    )
    rich_fields = (
        "description", "description_de", "description_en",
        "directions", "directions_de", "directions_en",
    )

    resource_count = serializers.IntegerField(source="resources.count", read_only=True)
    # Set via the dedicated multipart upload action, not via JSON.
    image = serializers.ImageField(read_only=True)
    # Access groups that grant access to this pool (reverse of
    # AccessGroup.pools): read as {id, name}; written via ``access_group_ids``
    # (replaces the assignment) so the pool form can edit visibility in place
    # (#138). Pool writes are admin-only (see ManageResourcePoolViewSet).
    access_groups = serializers.SerializerMethodField()
    access_group_ids = serializers.PrimaryKeyRelatedField(
        source="access_groups",
        many=True,
        write_only=True,
        required=False,
        queryset=AccessGroup.objects.all(),
    )

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
            "is_active", "resource_count", "access_groups", "access_group_ids",
            "position", "accent_color",
        ]

    # Read-only here — set via the reorder action, not direct edits.
    position = serializers.IntegerField(read_only=True)

    def get_access_groups(self, obj):
        return [{"id": g.id, "name": g.name} for g in obj.access_groups.all()]

    def create(self, validated_data):
        groups = validated_data.pop("access_groups", None)
        with transaction.atomic():
            pool = super().create(validated_data)
            if groups is not None:
                pool.access_groups.set(groups)
        return pool

    def update(self, instance, validated_data):
        groups = validated_data.pop("access_groups", None)
        with transaction.atomic():
            pool = super().update(instance, validated_data)
            if groups is not None:
                pool.access_groups.set(groups)
        return pool

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


def _origin(url) -> tuple[str, str]:
    """(scheme, host[:port]) of ``url``, lower-cased (empty parts for an
    empty/odd value)."""
    parts = urlsplit((url or "").strip())
    return parts.scheme.lower(), parts.netloc.lower()


class PoolDefectTicketSerializer(serializers.ModelSerializer):
    """Per-pool GitLab defect-ticket integration, edited by lenders in the
    lending area.

    The access token is write-only — it is never returned; a boolean reports
    only whether one is stored. On update, the token is set when a non-empty
    value is sent, cleared when an empty string is sent, and left untouched when
    the field is omitted entirely — unless the URL moves to another
    scheme/host/port without a new token in the same request, which clears it
    (the token is bound to its origin).
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
        elif "defect_gitlab_url" in validated_data and _origin(
            validated_data["defect_gitlab_url"]
        ) != _origin(instance.defect_gitlab_url):
            # The token is bound to its origin: moving the URL to another
            # scheme/host/port without re-entering the token drops it, so
            # nobody can redirect a stored token to a server of their choosing
            # (or downgrade it to clear-text http).
            instance.defect_gitlab_token = ""
        return super().update(instance, validated_data)


class NotificationSettingSerializer(TranslatedFieldsMixin, serializers.ModelSerializer):
    """Admin read/write of the custom reservation-email text (de/en)."""

    translated_fields = (
        "reservation_intro", "reservation_footer", "rescheduled_note",
        "cancellation_note", "reminder_note", "defect_note",
        "pickup_reminder_note",
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
            "pickup_reminder_enabled",
            "pickup_reminder_send_time",
            "pickup_reminder_note", "pickup_reminder_note_de",
            "pickup_reminder_note_en",
            "confirmation_send_time",
        ]


class WelcomeSettingSerializer(RichHtmlFieldsMixin, serializers.ModelSerializer):
    """Admin read/write of the welcome page text; logo is read-only here
    (uploaded via the dedicated multipart endpoint)."""

    rich_fields = ("text",)

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


class PageManageSerializer(RichHtmlFieldsMixin, TranslatedFieldsMixin, serializers.ModelSerializer):
    """Admin CRUD for content pages (Imprint, Privacy, …)."""

    translated_fields = ("title", "body")
    rich_fields = ("body", "body_de", "body_en")

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
    """Public read of a single published page's sanitized rich-HTML body."""

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


class PoolLenderSerializer(serializers.ModelSerializer):
    """Compact user shape for a pool's lender list."""

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = fields


class PoolLendersUpdateSerializer(serializers.Serializer):
    """The full set of users who should be lenders (managers) of a pool."""

    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=2**31 - 1),
        allow_empty=True,
    )
