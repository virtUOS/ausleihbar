# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)
"""Central trash bin across the soft-deletable catalog models."""
from datetime import timedelta

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsLenderOrAdmin
from .models import (
    Category,
    Product,
    ProductSet,
    ProductType,
    Resource,
    ResourcePool,
    Section,
    TrashSetting,
)
from .views import _is_admin, _managed_pool_ids

# type slug -> (model, label attribute, is_admin_only)
TRASH_TYPES = {
    "section": (Section, "title", True),
    "category": (Category, "title", True),
    "product-type": (ProductType, "name", True),
    "product": (Product, "title", False),
    "resource": (Resource, "inventory_number", False),
    "set": (ProductSet, "name", False),
    "pool": (ResourcePool, "name", True),
}


def _visible_dead(model, is_admin_only, user):
    """Trashed rows of `model` the user may manage."""
    qs = model.all_objects.dead()
    if _is_admin(user):
        return qs
    if is_admin_only:
        return qs.none()
    # Lender: only rows tied to pools they manage.
    pool_ids = _managed_pool_ids(user)
    if model is Resource:
        return qs.filter(resource_pool_id__in=pool_ids)
    if model is Product:
        return qs.filter(resources__resource_pool_id__in=pool_ids).distinct()
    if model is ProductSet:
        return qs.filter(resource_pool_id__in=pool_ids)
    return qs.none()


class TrashView(APIView):
    permission_classes = [IsAuthenticated, IsLenderOrAdmin]

    def _rows(self, user):
        retention = TrashSetting.load().retention_days
        rows = []
        for slug, (model, label_attr, admin_only) in TRASH_TYPES.items():
            for obj in _visible_dead(model, admin_only, user).select_related("deleted_by"):
                rows.append({
                    "type": slug,
                    "id": obj.id,
                    "label": getattr(obj, label_attr, str(obj)),
                    "deleted_at": obj.deleted_at,
                    "deleted_by": obj.deleted_by.get_full_name() if obj.deleted_by else None,
                    "purge_at": obj.deleted_at + timedelta(days=retention),
                })
        rows.sort(key=lambda r: r["deleted_at"], reverse=True)
        return rows

    def get(self, request):
        return Response(self._rows(request.user))

    def delete(self, request):
        # Empty the trash the caller may manage.
        for slug, (model, _label, admin_only) in TRASH_TYPES.items():
            _visible_dead(model, admin_only, request.user).delete()
        return Response(status=204)


class TrashItemView(APIView):
    permission_classes = [IsAuthenticated, IsLenderOrAdmin]

    def _get(self, slug, pk, user):
        if slug not in TRASH_TYPES:
            return None
        model, _label, admin_only = TRASH_TYPES[slug]
        return _visible_dead(model, admin_only, user).filter(pk=pk).first()

    def delete(self, request, type, pk):  # hard-delete one
        obj = self._get(type, pk, request.user)
        if obj is None:
            return Response({"detail": "Not found."}, status=404)
        obj.delete()
        return Response(status=204)


class TrashRestoreView(APIView):
    permission_classes = [IsAuthenticated, IsLenderOrAdmin]

    def post(self, request, type, pk):
        model_tuple = TRASH_TYPES.get(type)
        if model_tuple is None:
            return Response({"detail": "Unknown type."}, status=404)
        model, _label, admin_only = model_tuple
        obj = _visible_dead(model, admin_only, request.user).filter(pk=pk).first()
        if obj is None:
            return Response({"detail": "Not found."}, status=404)
        obj.restore()
        return Response({"detail": "Restored."})
