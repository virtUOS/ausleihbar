# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Gallery and single-image uploads (#119).

Product and set galleries (``views.GalleryImagesMixin``) and the single
images of pools, sections and categories (``views.ImageUploadMixin``) go
through the rich-image processing (``rich_images.process_uploaded_image``:
real format, EXIF orientation applied, metadata stripped, pixel/frame limits)
with larger byte and pixel limits, downscaled to ``UPLOAD_IMAGE_MAX_EDGE`` on
the long edge, and are stored under a random name. The ZIP import uses the
same processing (``process_bytes``). Replaced or removed files are deleted
(after the transaction commits) unless another row still references them.
"""
import logging
import uuid

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.utils.translation import gettext as _

from .rich_images import ImageTooLarge, TooManyPixels, process_uploaded_image

logger = logging.getLogger(__name__)

UPLOAD_IMAGE_MAX_BYTES = 15 * 1024 * 1024
# Phone photos reach 48-50 MP; the stored image is downscaled anyway.
UPLOAD_IMAGE_MAX_PIXELS = 64_000_000
UPLOAD_IMAGE_MAX_EDGE = 4096


class InvalidImage(ValueError):
    """An upload was rejected; ``str(exc)`` is the user-facing message."""


def _too_large():
    return InvalidImage(_("The image is too large (max. 15 MB)."))


def _too_many_pixels():
    return InvalidImage(_("The image has too many pixels (max. 64 megapixels)."))


def _not_an_image():
    return InvalidImage(_("The file is not a supported image (PNG, JPEG, GIF, WebP)."))


def process_upload(upload) -> tuple[bytes, str]:
    """Validate and re-encode an uploaded file; return ``(bytes, extension)``.

    The size is checked before the file is read. Raises ``InvalidImage``
    with a translated message."""
    if upload.size is not None and upload.size > UPLOAD_IMAGE_MAX_BYTES:
        raise _too_large()
    return process_bytes(upload.read())


def process_bytes(raw) -> tuple[bytes, str]:
    """Validate, downscale and re-encode image bytes with the upload limits;
    return ``(bytes, extension)``. Raises ``InvalidImage`` (a ``ValueError``)
    with a translated message."""
    try:
        return process_uploaded_image(
            raw, UPLOAD_IMAGE_MAX_BYTES,
            max_pixels=UPLOAD_IMAGE_MAX_PIXELS, max_edge=UPLOAD_IMAGE_MAX_EDGE,
        )
    except ImageTooLarge:
        raise _too_large() from None
    except TooManyPixels:
        raise _too_many_pixels() from None
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
    file between several rows. References from rich-text HTML are not
    checked: rich images live in ``rich/``, which no file field uses."""
    return any(
        model._base_manager.filter(**{field.name: name}).exists()
        for model, field in _file_fields()
    )


def delete_file_if_unreferenced(name):
    """Delete the stored file ``name`` unless some row still references it.

    Call after the row that held it has been changed or deleted. Runs once
    the transaction commits (a rollback keeps the file), and never raises:
    the database change is already committed, so a failing check or delete
    is only logged."""
    if name:
        transaction.on_commit(lambda: _delete_now(name))


def _delete_now(name):
    try:
        if not is_file_referenced(name):
            default_storage.delete(name)
    except Exception:  # noqa: BLE001 — never turn a committed change into a 500
        logger.warning("Could not delete the unreferenced image %s", name, exc_info=True)
