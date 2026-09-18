# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Catalog domain models: product types, products, resources, grouping."""
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import SoftDeleteModel, TimeStampedModel

from .fields import EncryptedTextField


def default_closed_weekdays():
    """Default closed weekdays: Saturday and Sunday (Mon=0 … Sun=6)."""
    return [5, 6]


def default_attribute_schema():
    """Return an empty attribute schema for a new ProductType.

    The schema is a list of attribute definitions. Each entry describes a
    dynamic attribute, e.g.:

        {
            "key": "serial_number",
            "label": "Serial number",
            "type": "string",      # short_text, long_text, date, time, number,
                                   # url, media, image
            "default": "",
            "visible": True,       # shown to borrowers
            "required": False,     # mandatory when creating a product
        }
    """
    return []


class ProductType(SoftDeleteModel):
    """Reusable template defining dynamic attributes for products."""

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    attribute_schema = models.JSONField(default=default_attribute_schema, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(SoftDeleteModel):
    """Catalog entry derived from a ProductType.

    A product is a group of equivalent resources (ADR-0001, concept §1.3).
    """

    class LendingType(models.TextChoices):
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"

    product_type = models.ForeignKey(
        ProductType,
        on_delete=models.PROTECT,
        related_name="products",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Guidance shown to lenders at return time: what to check before taking the
    # device back (concept §6.3). Not shown to borrowers.
    return_info = models.TextField(blank=True)

    lending_type = models.CharField(
        max_length=10,
        choices=LendingType.choices,
        default=LendingType.DAYS,
    )
    min_duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum lending duration in the lending_type unit (overrides pool default).",
    )
    max_duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum lending duration in the lending_type unit (overrides pool default).",
    )
    min_gap = models.PositiveIntegerField(
        default=0,
        help_text="Minimum gap between two bookings of a device, in the "
        "lending_type unit (days/hours). 0 = no gap.",
    )
    missing_notice_lead = models.PositiveIntegerField(
        default=0,
        help_text="How far before pickup to warn the next borrower that the "
        "product is missing, in the lending_type unit. 0 = never notify.",
    )

    # Concrete attribute values matching the product type's attribute_schema.
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class ProductImage(TimeStampedModel):
    """One image in a product's gallery. The lowest ``position`` is the cover
    used on cards and as the product page's first image (concept §1.3)."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.title} image #{self.position}"


class ResourcePool(SoftDeleteModel):
    """Physical location that holds resources (concept §1.5)."""

    name = models.CharField(max_length=255, unique=True)
    pool_id = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)

    # Postal/building address (multi-line) and the specific room, kept separate.
    address = models.TextField(blank=True)
    room = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="pools/", blank=True, null=True)
    directions = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    # Optional note shown in this pool's block of borrower emails, e.g.
    # "This pool is only available to students of subject XY" (issue #30).
    # Translatable (de/en); appears wherever the pool is listed in a mail.
    email_note = models.TextField(blank=True)
    # Email the pool's contact (``email``) when one of its resources is marked
    # defective (concept §3.6). No effect if no contact email is set.
    notify_on_defect = models.BooleanField(default=True)
    # Email the pool's contact (``email``) when a borrower cancels a booking
    # that involves this pool (concept §6.5). No effect without a contact email.
    notify_on_cancellation = models.BooleanField(default=True)
    # Require borrowers to enter a message when their order includes a resource
    # from this pool. If any pool in a cart requires it, the note becomes
    # mandatory on submit (concept §6.1).
    require_booking_note = models.BooleanField(default=False)
    # Optionally open a GitLab issue when a resource here is marked defective
    # (per-pool, opt-in — most pools leave this blank). The full project URL
    # may differ per pool, server included, e.g.
    # "https://gitlab.example.com/group/project". The access token is
    # write-only: never returned by the API and hidden in the Django admin.
    defect_gitlab_url = models.URLField(blank=True)
    defect_gitlab_token = EncryptedTextField(blank=True, default="")

    # Structured opening hours incl. breaks, e.g. {"mon": [["09:00", "17:00"]], ...}.
    opening_hours = models.JSONField(default=dict, blank=True)
    # Weekdays the pool is closed (0=Mon … 6=Sun) — not bookable on those days.
    closed_weekdays = ArrayField(
        models.PositiveSmallIntegerField(),
        default=default_closed_weekdays,
        blank=True,
    )
    # Minimum lead time (in hours) required between booking and pickup.
    lead_time_hours = models.PositiveIntegerField(default=0)
    # How far into the future bookings are allowed (in months). Mandatory;
    # prevents stray bookings years ahead. Concept §1.5 / §3.5.
    max_booking_months = models.PositiveIntegerField(default=24)

    # Default lending duration bounds per lending type (override the system default).
    default_min_days = models.PositiveIntegerField(null=True, blank=True)
    default_max_days = models.PositiveIntegerField(null=True, blank=True)
    default_min_hours = models.PositiveIntegerField(null=True, blank=True)
    default_max_hours = models.PositiveIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Resource(SoftDeleteModel):
    """A single physical device or room available for lending (concept §1.4)."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        BLOCKED = "blocked", "Blocked"
        DEFECTIVE = "defective", "Defective"
        RETIRED = "retired", "Retired"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="resources",
    )
    resource_pool = models.ForeignKey(
        ResourcePool,
        on_delete=models.PROTECT,
        related_name="resources",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    # Human-readable, pool-scoped identifier, e.g. "DigiLab-001" (ADR concept C4).
    inventory_number = models.CharField(max_length=255, unique=True)
    qr_code_id = models.CharField(max_length=255, unique=True)
    # Manufacturer serial number of this physical unit (optional).
    serial_number = models.CharField(max_length=255, blank=True)
    # What is wrong, set when status is defective; cleared on repair.
    defect_note = models.CharField(max_length=500, blank=True)

    # Lender-internal quality rating (1–5 stars); does not affect bookability,
    # only allocation order (best rating first). Never shown to borrowers.
    condition_rating = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    condition_note = models.CharField(max_length=500, blank=True)

    storage_location = models.CharField(max_length=255, blank=True)
    procurement_date = models.DateField(null=True, blank=True)
    warranty_end = models.DateField(null=True, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    procuring_institution = models.CharField(max_length=255, blank=True)
    owning_institution = models.CharField(max_length=255, blank=True)

    # Optional overrides of the product's lending settings.
    lending_type = models.CharField(
        max_length=10,
        choices=Product.LendingType.choices,
        blank=True,
    )
    min_duration = models.PositiveIntegerField(null=True, blank=True)
    max_duration = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["inventory_number"]

    def __str__(self):
        return f"{self.inventory_number} ({self.product.title})"


class ResourceDefect(TimeStampedModel):
    """One recorded defect on a resource (history).

    ``created_at`` is when the defect was reported; ``resolved_at`` is set when
    the resource is returned to service. Records are created/closed
    automatically when a resource's status moves to/from ``defective``.
    """

    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="defects"
    )
    note = models.CharField(max_length=500, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Link to the GitLab issue opened for this defect, when the pool has the
    # integration configured (see ResourcePool.defect_gitlab_url).
    gitlab_issue_url = models.URLField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Defect on {self.resource_id} ({'resolved' if self.resolved_at else 'open'})"


class Category(SoftDeleteModel):
    """Groups products into a browsable category (concept §1.6)."""

    title = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    products = models.ManyToManyField(Product, related_name="categories", blank=True)
    # Manual display order of the products within this category (list of product
    # ids). Products not listed (e.g. newly added) sort after the listed ones.
    product_order = ArrayField(
        models.PositiveIntegerField(), default=list, blank=True
    )
    # Manual display order; new entries are appended at the end (concept §1.6).
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["position", "title"]

    def __str__(self):
        return self.title


class Section(SoftDeleteModel):
    """Groups categories into a section ("Sparte", concept §1.6).

    Renamed from the earlier ``Department`` to match the concept terminology
    (ADR-0003).
    """

    title = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="sections/", blank=True, null=True)
    categories = models.ManyToManyField(Category, related_name="sections", blank=True)
    sets = models.ManyToManyField("ProductSet", related_name="sections", blank=True)
    # Manual display order of the categories / sets within this section (lists of
    # ids). Entries not listed (e.g. newly added) sort after the listed ones.
    category_order = ArrayField(
        models.PositiveIntegerField(), default=list, blank=True
    )
    set_order = ArrayField(models.PositiveIntegerField(), default=list, blank=True)
    # Manual display order; new entries are appended at the end (concept §1.6).
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["position", "title"]

    def __str__(self):
        return self.title


class ProductSet(SoftDeleteModel):
    """A list of products frequently lent together (concept §1.1, C3).

    A set belongs to one resource pool; all its products are lent from there.
    """

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    resource_pool = models.ForeignKey(
        ResourcePool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_sets",
    )
    products = models.ManyToManyField(Product, related_name="product_sets", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WelcomeSetting(models.Model):
    """Public welcome page content shown to not-yet-logged-in visitors.

    A singleton (pk forced to 1). ``text`` is admin-editable Markdown; ``logo``
    is the institution's logo shown in the shop header (raster image or SVG —
    a FileField, since ImageField would reject SVG).
    """

    text = models.TextField(blank=True)
    logo = models.FileField(upload_to="branding/", blank=True, null=True)

    class Meta:
        verbose_name = "welcome setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Welcome page"


class NotificationSetting(models.Model):
    """Admin-editable custom text woven into the automatic reservation email.

    Singleton (pk=1). ``reservation_intro`` replaces the default opening line of
    the "reservation received" email; ``reservation_footer`` is a closing block
    shown before the signature. Both are optional and translatable (de/en) — the
    mail uses the borrower's language. The structured parts (pickup/pool details,
    booking number, link to "My bookings") are always kept (issue #30).
    """

    reservation_intro = models.TextField(blank=True)
    reservation_footer = models.TextField(blank=True)
    # Optional extra paragraphs woven into the other borrower emails, before the
    # signature (issue #30 follow-up). All optional and translatable.
    rescheduled_note = models.TextField(blank=True)   # booking moved by a closure
    cancellation_note = models.TextField(blank=True)  # booking cancelled by a closure
    reminder_note = models.TextField(blank=True)      # overdue pickup/return reminder
    defect_note = models.TextField(blank=True)        # reserved device unavailable

    class Meta:
        verbose_name = "notification setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Notification settings"


class ShopSetting(models.Model):
    """System-wide start-page (logged-in shop) display settings. Singleton (pk=1)."""

    # Admin-toggled rows on the start page.
    show_popular = models.BooleanField(default=True)
    show_new_arrivals = models.BooleanField(default=True)
    # A product shows the "new" label for this many days after it was created
    # (0 disables the label). System-wide, not per product.
    new_product_days = models.PositiveIntegerField(default=30)

    class Meta:
        verbose_name = "shop setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Shop settings"


class Page(TimeStampedModel):
    """An admin-editable content page (a small CMS), e.g. Imprint or Privacy.

    The ``body`` is Markdown, rendered client-side like the welcome page.
    Published pages can be linked from the site footer; ``slug`` is the public
    URL key (``/pages/<slug>``) and ``footer_order`` sorts the footer links.
    Unpublished pages stay editable in admin but are not publicly reachable —
    useful for drafting (e.g. a privacy statement awaiting review).
    """

    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Drafts: editable in admin, but hidden from the footer and the public view.
    is_published = models.BooleanField(default=True)
    # Whether a published page appears as a footer link.
    show_in_footer = models.BooleanField(default=True)
    footer_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["footer_order", "title"]

    def __str__(self):
        return self.title


class Favorite(TimeStampedModel):
    """A borrower's saved product for quick re-booking (concept §4.x).

    Per (user, product); the favorites page lets a borrower pick a period and
    check availability across their marked favorites before reserving.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="uniq_favorite_per_user"
            )
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"


class TrashSetting(models.Model):
    """Singleton (pk=1): how long trashed objects are kept before purge (#7)."""

    retention_days = models.PositiveIntegerField(
        default=30, validators=[MinValueValidator(1)]
    )

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Trash settings"
