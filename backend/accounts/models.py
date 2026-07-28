# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""User accounts, roles and pool memberships."""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Application user.

    Roles are intentionally non-exclusive (ADR-0002):
    - *Admin* — via ``is_staff`` / ``is_superuser``.
    - *Lender* — derived from managing at least one pool (see ``PoolMembership``).
    - *Borrower* — any authenticated user (no extra record needed).
    """

    # OIDC subject identifier (stable, unique per identity provider).
    subject = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # True if the account was created via self-registration (deferred feature).
    is_self_registered = models.BooleanField(default=False)
    # Set when a lender confirms the account at first contact (ADR/concept §6.5).
    verified_at = models.DateTimeField(null=True, blank=True)
    # Snapshot of the OIDC claims from the last login, used to match
    # claim-based access groups (concept §3.4). Refreshed on every login.
    claims = models.JSONField(default=dict, blank=True)

    # Preferred UI/email language ("en"/"de"), set from the SPA; blank = use the
    # site default. Notification emails are sent in this language.
    language = models.CharField(max_length=10, blank=True)

    # Strike-driven suspension (concept §7.3). A block lasts until ``blocked_until``
    # or, when ``blocked_permanently`` is set, indefinitely.
    blocked_until = models.DateTimeField(null=True, blank=True)
    blocked_permanently = models.BooleanField(default=False)

    # Set when the account was anonymized by the data-retention job: all personal
    # data is scrubbed and the record kept only as a placeholder ("Gelöschter
    # Nutzer") so device/booking history stays intact (see accounts.retention).
    anonymized_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_anonymized(self):
        return self.anonymized_at is not None

    def is_blocked(self):
        """Whether the user is currently barred from borrowing."""
        if self.blocked_permanently:
            return True
        return bool(self.blocked_until and self.blocked_until > timezone.now())

    def __str__(self):
        return self.get_username()


class PoolMembership(models.Model):
    """Links a user to a resource pool with a management role.

    A user who manages at least one pool is, in domain terms, a *lender*.
    """

    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pool_memberships",
    )
    resource_pool = models.ForeignKey(
        "catalog.ResourcePool",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MANAGER)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "resource_pool", "role"],
                name="unique_pool_membership",
            )
        ]

    def __str__(self):
        return f"{self.user} – {self.resource_pool} ({self.role})"


class AccessGroup(models.Model):
    """A group used to gate which pools an account may see and book.

    Membership is the union of:
    - **manual members** (assigned by an admin), and
    - **claim matching**: a user whose OIDC claim ``claim_key`` contains any of
      ``claim_values`` is a member automatically (concept §3.4).

    A pool with no access groups is open to all authenticated users; a pool
    that lists groups is restricted to members of those groups (plus the pool's
    lenders and admins).
    """

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="access_groups", blank=True
    )
    # Optional OIDC claim-based membership. Empty claim_key = manual only.
    claim_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="OIDC claim to match (e.g. 'groups' or 'department').",
    )
    claim_values = ArrayField(
        models.CharField(max_length=255),
        default=list,
        blank=True,
        help_text="A user whose claim contains any of these values is a member.",
    )
    pools = models.ManyToManyField(
        "catalog.ResourcePool", related_name="access_groups", blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def default_strike_thresholds():
    """Default escalation: 3 strikes → 30d, 5 → 180d, 7 → permanent."""
    return [
        {"count": 3, "block_days": 30},
        {"count": 5, "block_days": 180},
        {"count": 7, "block_days": 0},  # 0 = permanent
    ]


class StrikeSetting(models.Model):
    """System-wide strike policy (concept §7.3). Singleton (pk forced to 1)."""

    # How long a single strike counts before it expires.
    strike_expiry_days = models.PositiveIntegerField(default=365)
    # Escalation steps: each {count, block_days}; block_days 0 = permanent.
    thresholds = models.JSONField(default=default_strike_thresholds)

    class Meta:
        verbose_name = "strike setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Strike policy"


class RetentionSetting(models.Model):
    """Data-retention policy for inactive accounts (GDPR). Singleton (pk=1).

    When ``enabled``, accounts with no activity for ``retention_days`` and no
    open lending process are anonymized by the ``anonymize_inactive_users``
    job. Off by default so it is switched on deliberately (concept §7 / privacy).
    """

    enabled = models.BooleanField(default=False)
    # Inactivity window before an account is anonymized (default 3 years).
    retention_days = models.PositiveIntegerField(default=1095)

    class Meta:
        verbose_name = "retention setting"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Data-retention policy"


class Strike(models.Model):
    """A warning issued to a user, with a mandatory reason (concept §7.3).

    Strikes are pool-wide (they attach to the user, not a pool) and expire after
    the configured period. Reaching a threshold suspends the account.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="strikes"
    )
    # The booking the strike was issued over, if any — lets the borrower see
    # which reservation earned the strike (concept §7.3). Kept on delete so the
    # strike survives if the booking is later removed.
    booking = models.ForeignKey(
        "lending.Booking",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="strikes",
    )
    reason = models.TextField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="issued_strikes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_active(self):
        return self.expires_at > timezone.now()

    def __str__(self):
        return f"Strike for {self.user} ({self.created_at:%Y-%m-%d})"
