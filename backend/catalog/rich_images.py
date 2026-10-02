# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Validation and metadata-stripping re-encode of rich-text images (#43, #68).

Shared by the rich-text image upload (``views.RichImageUploadView``) and the
admin ZIP import (``transfer._MediaImporter``), so an image reaches
``rich/`` storage only after the same checks either way.
"""
from io import BytesIO

RICH_IMAGE_MAX_BYTES = 5 * 1024 * 1024
# Decompression-bomb guards (#43): reject images above this many pixels, and
# animations above a frame count / summed pixel count (a <5 MB animation can
# hold many large frames, and every frame is decoded into memory). 60 MP in
# total is about 240 MB of RGBA in the worst case.
RICH_IMAGE_MAX_PIXELS = 40_000_000
RICH_IMAGE_MAX_FRAMES = 200
RICH_IMAGE_MAX_TOTAL_PIXELS = 60_000_000
# The real format (detected by Pillow) decides the stored extension. MPO
# (multi-picture JPEG from phones) is stored as a plain JPEG (first frame).
RICH_IMAGE_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "MPO": ".jpg", "GIF": ".gif", "WEBP": ".webp"}
# File extensions that already name a given stored extension's format (a
# ``.jpeg`` file holding a JPEG keeps its name on import).
RICH_IMAGE_EXTENSIONS = {".png": {".png"}, ".jpg": {".jpg", ".jpeg"},
                         ".gif": {".gif"}, ".webp": {".webp"}}


def _webp_is_lossless(header):
    """True if the RIFF/WebP ``header`` holds a lossless (``VP8L``) bitstream.

    Pillow doesn't report this (``info`` has no "lossless" key), so the chunk
    list is walked: a simple lossless file has ``VP8L`` at bytes 12-16; an
    extended one (``VP8X`` — ICC/EXIF/XMP/alpha) has it after other chunks."""
    if header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return False
    pos = 12
    while pos + 8 <= len(header):
        fourcc = header[pos:pos + 4]
        if fourcc == b"VP8L":
            return True
        if fourcc in {b"VP8 ", b"ANIM"}:
            return False
        size = int.from_bytes(header[pos + 4:pos + 8], "little")
        pos += 8 + size + (size & 1)
    return False


def process_rich_image(raw: bytes) -> tuple[bytes, str]:
    """Decode ``raw`` and re-encode it without metadata (#43).

    Returns ``(bytes, extension)`` — the extension (with the dot) follows the
    detected format. Raises ``ValueError`` if the data is larger than
    ``RICH_IMAGE_MAX_BYTES``, not an allowed image, or exceeds the pixel /
    frame limits. EXIF orientation is applied first; then EXIF (incl. GPS),
    XMP and comments are dropped in every branch. The ICC colour profile is
    kept (it describes colours, not a person). Animated GIF/WebP keep all
    frames, per-frame durations and (if the source had one) the loop count;
    a lossless WebP stays lossless. An animated PNG (APNG) is stored as its
    first frame only. Pillow's own decompression-bomb error (far above
    ``RICH_IMAGE_MAX_PIXELS``) ends up as "not a valid image"."""
    from PIL import Image, ImageOps, ImageSequence

    if len(raw) > RICH_IMAGE_MAX_BYTES:
        raise ValueError("file too large")

    def strip(image):
        for key in ("comment", "xmp", "XML:com.adobe.xmp", "exif"):
            image.info.pop(key, None)
        return image

    try:
        # MPO is not an opener of its own: the JPEG plugin returns an MPO file
        # object for multi-picture JPEGs (``format == "MPO"``).
        img = Image.open(BytesIO(raw), formats=["PNG", "JPEG", "GIF", "WEBP"])
        fmt = img.format
        if fmt not in RICH_IMAGE_FORMATS:
            raise ValueError("unsupported format")
        pixels = img.width * img.height
        if pixels > RICH_IMAGE_MAX_PIXELS:
            raise ValueError("too many pixels")
        frame_count = getattr(img, "n_frames", 1) if fmt in {"GIF", "WEBP"} else 1
        if frame_count > RICH_IMAGE_MAX_FRAMES:
            raise ValueError("too many frames")
        if frame_count * pixels > RICH_IMAGE_MAX_TOTAL_PIXELS:
            raise ValueError("animation too large")
        icc = img.info.get("icc_profile") or None
        out = BytesIO()
        if frame_count > 1:
            loop = img.info.get("loop")  # None: source had no loop value
            frames, durations = [], []
            for frame in ImageSequence.Iterator(img):
                frame.load()  # WebP only exposes the duration after load
                durations.append(frame.info.get("duration", 100))
                copy = frame.convert("RGBA") if fmt == "WEBP" else frame.copy()
                frames.append(strip(copy))
            kwargs = {"save_all": True, "append_images": frames[1:],
                      "duration": durations}
            if loop is not None:
                kwargs["loop"] = loop
            if fmt == "WEBP":
                kwargs.update(quality=90, exif=b"", xmp=b"")
                if icc:
                    kwargs["icc_profile"] = icc
            frames[0].save(out, format=fmt, **kwargs)
        else:
            img.load()
            img = strip(ImageOps.exif_transpose(img))
            if fmt in {"JPEG", "MPO"}:
                img.save(out, format="JPEG", quality=90, optimize=True,
                         exif=b"", xmp=b"", icc_profile=icc)
            elif fmt == "PNG":
                img.save(out, format="PNG", optimize=True)
            elif fmt == "GIF":
                img.save(out, format="GIF")
            else:  # WEBP
                kwargs = {"exif": b"", "xmp": b"", "icc_profile": icc or ""}
                if _webp_is_lossless(raw):
                    img.save(out, format="WEBP", lossless=True, **kwargs)
                else:
                    img.save(out, format="WEBP", quality=90, **kwargs)
    except ValueError:
        raise
    except Exception as exc:  # corrupt data, decompression bomb, I/O errors
        raise ValueError("not a valid image") from exc
    return out.getvalue(), RICH_IMAGE_FORMATS[fmt]
