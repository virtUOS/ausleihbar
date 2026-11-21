# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Course link ↔ system access group plumbing (LTI course pools).

Invariant: every ``LtiCourseLink`` owns exactly one ``AccessGroup`` with
``system_course`` = the link. While the link is active the group is the
pool's visibility group (``AccessGroup.pools`` = {pool}); switched off it
gates nothing, but keeps its members so switching on again restores them.
The group never carries rights (no ``lender_pools``, no ``is_admin``, no
claim rule). ``LtiCourseLink.save()`` calls ``ensure_course_group``, so the
invariant holds for every write path (API, Django admin, shell).
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import gettext as _
from modeltranslation.utils import build_localized_fieldname

from accounts import roles
from accounts.models import AccessGroup
from catalog.models import ResourcePool

from .models import LtiCourseLink

COURSE_GROUP_PREFIX = "Kurs"


def course_group_name(link) -> str:
    """The group's base name "Kurs ‹title› · ‹pool›" (before de-duplication)."""
    title = link.title or link.context_id
    return f"{COURSE_GROUP_PREFIX} {title} · {roles._pool_name(link.pool)}"


def ensure_course_group(link) -> AccessGroup:
    """Create or repair the system access group of ``link`` (idempotent).

    Keeps its name in sync with course title and pool name (suffixed if the
    name is taken), clears any rights/claim rule and sets its ``pools`` to
    ``{link.pool}`` when the link is active, ``{}`` otherwise."""
    base = course_group_name(link)
    with transaction.atomic():
        group = AccessGroup.objects.filter(system_course=link).first()
        if group is None:
            group = AccessGroup.objects.create(
                name=roles._free_name(base), system_course=link
            )
        else:
            changed = []
            name = roles._free_name(base, exclude_pk=group.pk)
            if group.name != name:
                group.name = name
                changed.append("name")
            if group.claim_key or group.claim_values:
                group.claim_key, group.claim_values = "", []
                changed += ["claim_key", "claim_values"]
            if group.is_admin:
                group.is_admin = False
                changed.append("is_admin")
            if changed:
                group.save(update_fields=changed)
        # ``manager="all_objects"``: the default related manager hides trashed
        # pools, and clear() through it would leave their rows behind.
        if group.lender_pools(manager="all_objects").exists():
            group.lender_pools(manager="all_objects").clear()
        wanted = {link.pool_id} if link.is_active else set()
        current = set(group.pools(manager="all_objects").values_list("pk", flat=True))
        if current != wanted:
            group.pools(manager="all_objects").clear()
            if link.is_active:
                group.pools.add(link.pool)
    return group


def create_link(
    *, platform, context_id, pool, title="", created_by=None
) -> tuple[LtiCourseLink, bool]:
    """Link the course (``platform`` + ``context_id``) to ``pool``.

    Returns ``(link, created)``. A new link starts active and gets its system
    group (attached to the pool) in the same transaction. An existing link is
    returned unchanged except for a refreshed non-empty ``title``."""
    with transaction.atomic():
        link, created = LtiCourseLink.objects.get_or_create(
            platform=platform,
            context_id=context_id,
            pool=pool,
            defaults={"title": title, "created_by": created_by},
        )
        if not created and title and link.title != title:
            link.title = title
            link.save(update_fields=["title", "updated_at"])
    return link, created


def set_link_active(link, active: bool) -> LtiCourseLink:
    """Switch the link on (group gates the pool) or off (group detached,
    members kept)."""
    if link.is_active != active:
        link.is_active = active
        link.save(update_fields=["is_active", "updated_at"])
    return link


def course_group(link) -> AccessGroup:
    """The link's system access group (repaired if missing)."""
    return AccessGroup.objects.filter(system_course=link).first() or ensure_course_group(link)


# --- Launch flow (instructor / learner) -------------------------------------


def refresh_course_title(platform, context_id, title) -> None:
    """Store the LMS course title on every link of the course (active or not),
    renaming their groups. An empty title keeps the stored one."""
    if not title:
        return
    for link in LtiCourseLink.objects.filter(
        platform=platform, context_id=context_id
    ).exclude(title=title):
        link.title = title
        link.save(update_fields=["title", "updated_at"])


def link_course(*, user, platform, context_id, pool, title="") -> LtiCourseLink:
    """An instructor links their course to ``pool`` (one they are lender of).

    Creates the link or switches an existing one back on. Raises
    ``PermissionDenied`` if ``user`` doesn't manage the pool."""
    if pool.pk not in roles.managed_pool_ids(user):
        raise PermissionDenied("Not a lender of this pool.")
    link, _ = create_link(
        platform=platform, context_id=context_id, pool=pool, title=title,
        created_by=user,
    )
    return set_link_active(link, True)


def _free_pool_id(name) -> str:
    base = (slugify(name).upper() or "POOL")[:56]
    taken = ResourcePool.all_objects
    pool_id, n = base, 1
    while taken.filter(pool_id__iexact=pool_id).exists():
        n += 1
        pool_id = f"{base}-{n}"
    return pool_id


def create_personal_pool(*, user, name) -> ResourcePool:
    """A lecturer's own pool: active, owned by ``user``, ``user`` its lender
    (system lender group), no opening hours yet (nobody can book until the
    owner enters them).

    Raises ``PermissionDenied`` while ``LtiSetting.instructors_create_pools``
    is off and ``ValidationError`` for an empty or taken name."""
    from .models import LtiSetting

    if not LtiSetting.load().instructors_create_pools:
        raise PermissionDenied("Instructors may not create pools.")
    name = (name or "").strip()
    max_length = ResourcePool._meta.get_field("name").max_length
    if not name:
        raise ValidationError(_("Please enter a name for the pool."))
    if len(name) > max_length:
        raise ValidationError(_("The name is too long."))
    name_fields = {"name", *(
        build_localized_fieldname("name", code)
        for code in settings.MODELTRANSLATION_LANGUAGES
    )}
    taken = Q()
    for field in name_fields:
        taken |= Q(**{f"{field}__iexact": name})
    if ResourcePool.all_objects.filter(taken).exists():
        raise ValidationError(_("A pool with this name already exists."))
    default_field = build_localized_fieldname(
        "name", settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    )
    with transaction.atomic():
        pool = ResourcePool.objects.create(
            pool_id=_free_pool_id(name),
            owner=user,
            is_personal=True,
            is_active=True,
            opening_hours={},
            **{"name": name, default_field: name},
        )
        # Saving the pool created its system lender group (accounts.signals).
        roles.ensure_pool_lender_group(pool).members.add(user)
    return pool


def course_links(platform, context_id):
    """All links of the course, with their (untrashed) pools."""
    return (
        LtiCourseLink.objects.filter(
            platform=platform, context_id=context_id, pool__deleted_at__isnull=True
        )
        .select_related("pool")
        .order_by("pool__name")
    )


def _open_links(platform, context_id):
    return course_links(platform, context_id).filter(
        is_active=True, pool__is_active=True
    )


def has_open_links(platform, context_id) -> bool:
    """Whether the course has an active link to an active pool."""
    return _open_links(platform, context_id).exists()


def join_course_groups(*, user, platform, context_id) -> list[ResourcePool]:
    """A learner launch: add ``user`` to the groups of every **active** link of
    the course whose pool is active. Returns those pools (name order)."""
    links = list(_open_links(platform, context_id))
    for link in links:
        course_group(link).members.add(user)
    return [link.pool for link in links]
