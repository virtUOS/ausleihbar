# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Extract plain text from an uploaded PDF for AI product extraction (Feature 2).

Digital manuals carry a text layer; scanned PDFs do not — there is no OCR here,
so a text-less PDF raises ``PdfTextError`` and the caller reports it cleanly.
"""

import re


class PdfTextError(Exception):
    """The PDF has no extractable text (e.g. a scan) or could not be read."""


def extract_pdf_text(file, *, max_chars: int = 12000) -> str:
    """Return the concatenated, whitespace-normalised text of ``file`` (a
    file-like object), capped at ``max_chars``. Raises ``PdfTextError`` when the
    PDF is unreadable or holds no extractable text."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(file)
        parts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises various errors on malformed/encrypted files
        raise PdfTextError(str(exc)) from exc
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if not text:
        raise PdfTextError("no extractable text")
    return text[:max_chars]
