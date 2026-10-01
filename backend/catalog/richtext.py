# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Rich-text helpers (#5): conversions to/from the sanitized HTML subset.

The allowlist itself is basicbar's ``clean_html``; everything that stores rich
HTML goes through it.
"""
import html as _html
import re

import markdown as _markdown
from basicbar_integrations.html_sanitize import clean_html

# A value is only treated as already-HTML when it *starts* with one of the
# block tags the rich editor itself produces (M2). A Markdown source can
# legitimately contain an inline "<br>" or a stray "<" without being HTML —
# checking anywhere in the text (the previous approach) misclassified those.
_HTML_LIKE_RE = re.compile(r"^\s*<(p|h2|h3|ul|ol)\b", re.I)

# Headings the allowlist doesn't keep are remapped instead of dropped:
# h1 reads as a page-level title we don't want inside rich content, so it
# steps down to h2; h4-h6 all collapse to the one remaining sub-level, h3.
_HEADING_RE = re.compile(r"<(/?)(h[1456])(\s[^>]*)?>", re.I)
_HEADING_MAP = {"h1": "h2", "h4": "h3", "h5": "h3", "h6": "h3"}


def _remap_headings(html):
    def repl(match):
        closing, tag, attrs = match.group(1), match.group(2).lower(), match.group(3) or ""
        return f"<{closing}{_HEADING_MAP[tag]}{attrs}>"

    return _HEADING_RE.sub(repl, html)


def clean_rich(html):
    """Sanitize ``html`` to the rich allowlist, treating a body with no
    visible content as empty (M1) — e.g. an editor left with just
    ``<p></p>`` or ``<p><br></p>`` should store "", not markup."""
    cleaned = clean_html(html)
    if not cleaned:
        return cleaned
    if "<img" not in cleaned and not re.sub(r"<[^>]+>", "", cleaned).strip():
        return ""
    return cleaned


def looks_like_html(text):
    """True if ``text`` already looks like rich HTML rather than Markdown or
    plain text (M2) — i.e. it starts with a block tag from the allowlist."""
    return bool(text) and bool(_HTML_LIKE_RE.match(text))


def markdown_to_html(text):
    if not text:
        return ""
    # No "nl2br": a single newline (a hard-wrapped paragraph) must render as
    # a space, matching the previous client-side react-markdown rendering —
    # only a blank line starts a new paragraph (I3).
    html = _markdown.markdown(text, extensions=["extra", "sane_lists"], output_format="html")
    return clean_html(_remap_headings(html))


def plain_to_html(text):
    if not text:
        return ""
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    body = "".join(
        "<p>" + "<br>".join(_html.escape(line.strip()) for line in p.splitlines()) + "</p>"
        for p in paragraphs
    )
    return clean_html(body)


def html_to_text(html):
    """Readable plain text for plain-text emails."""
    if not html:
        return ""
    text = re.sub(r"<a\s[^>]*href=\"([^\"]*)\"[^>]*>(.*?)</a>",
                  lambda m: m.group(2) if _strip(m.group(2)) == m.group(1) else f"{m.group(2)} ({m.group(1)})",
                  html, flags=re.I | re.S)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|h2|h3|ul|ol|li)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _strip(s):
    return re.sub(r"<[^>]+>", "", s).strip()


class RichHtmlModelMixin:
    """Sanitize this model's rich-HTML fields on every ``save()`` (I1).

    ``RichHtmlFieldsMixin`` (in ``serializers.py``) only covers the DRF write
    path; the Django admin and any other ORM caller (management commands, a
    data import, the shell) call ``.save()`` directly and would otherwise
    store whatever HTML they were given, unsanitized — a stored-XSS hole.
    This mixin closes that gap at the model level, which the serializer
    mixin then makes redundant-but-harmless for the API path.

    Subclasses set ``rich_fields`` to every column that holds rich HTML,
    including each per-language column and the bare (untranslated) name,
    e.g. ``("body", "body_de", "body_en")``.

    Note: ``QuerySet.update()`` (and other bulk/raw SQL writes) bypasses
    ``save()`` entirely, so it bypasses this mixin too — nothing sanitizes a
    bulk update of one of these fields.
    """

    rich_fields: tuple = ()

    def save(self, *args, **kwargs):
        fields = self.rich_fields
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            fields = [f for f in fields if f in update_fields]
        for field in fields:
            value = getattr(self, field, None)
            if value:
                setattr(self, field, clean_rich(value))
        super().save(*args, **kwargs)


def _rich_media_re():
    from django.conf import settings

    prefix = "/" + settings.MEDIA_URL.strip("/") + "/"
    return re.compile(
        r"(?:https?://[^/\"'\s<>]+)?" + re.escape(prefix) + r"(rich/[^\"'\s<>?#)]+)", re.I
    )


def rich_media_names(html):
    """Storage names (``rich/<file>``) of the uploaded rich images referenced
    by ``html`` — relative ``/media/rich/…`` or absolute ``http(s)://host/media/rich/…``."""
    if not html:
        return set()
    return {m.group(1) for m in _rich_media_re().finditer(html)}
