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
from django.db import transaction

from accounts import roles
from accounts.models import AccessGroup

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
