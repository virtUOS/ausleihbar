# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Gallery and single-image uploads (#119).

Product and set galleries (``views.GalleryImagesMixin``) and the single
images of pools, sections and categories (``views.ImageUploadMixin``) go
through the rich-image processing (``rich_images.process_uploaded_image``:
real format, EXIF orientation applied, metadata stripped, pixel/frame limits)
with a larger byte limit, and are stored under a random name. Replaced or
removed files are deleted unless another row still references them.
"""
import logging
import uuid

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.utils.translation import gettext as _

from .rich_images import ImageTooLarge, process_uploaded_image

logger = logging.getLogger(__name__)

UPLOAD_IMAGE_MAX_BYTES = 15 * 1024 * 1024


class InvalidImage(ValueError):
    """An upload was rejected; ``str(exc)`` is the user-facing message."""


def _too_large():
    return InvalidImage(_("The image is too large (max. 15 MB)."))


def _not_an_image():
    return InvalidImage(_("The file is not a supported image (PNG, JPEG, GIF, WebP)."))


def process_upload(upload) -> tuple[bytes, str]:
    """Validate and re-encode an uploaded file; return ``(bytes, extension)``.

    The size is checked before the file is read. Raises ``InvalidImage``
    with a translated message."""
    if upload.size is not None and upload.size > UPLOAD_IMAGE_MAX_BYTES:
        raise _too_large()
    try:
        return process_uploaded_image(upload.read(), UPLOAD_IMAGE_MAX_BYTES)
    except ImageTooLarge:
        raise _too_large() from None
    except ValueError:
        raise _not_an_image() from None


def save_processed(field_file, data, ext, save=True):
    """Store re-encoded image bytes in ``field_file`` (an ``ImageField`` of a
    model instance) under its ``upload_to`` with a random name — the client's
    file name is never used."""
    field_file.save(f"{uuid.uuid4().hex}{ext}", ContentFile(data), save=save)


def _file_fields():
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if isinstance(field, models.FileField):
                yield model, field


def is_file_referenced(name) -> bool:
    """True if any file/image field of any model (trashed rows included —
    ``_base_manager`` of a soft-delete model is ``all_objects``) holds
    ``name``. Category images migrated from product types (#78) may share a
    file between several rows."""
    return any(
        model._base_manager.filter(**{field.name: name}).exists()
        for model, field in _file_fields()
    )


def delete_file_if_unreferenced(name):
    """Delete the stored file ``name`` unless some row still references it.
    Call after the row that held it has been changed or deleted."""
    if not name or is_file_referenced(name):
        return
    try:
        default_storage.delete(name)
    except OSError:
        logger.warning("Could not delete the unreferenced image %s", name, exc_info=True)
