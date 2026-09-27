# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Rich-text helpers (#5): conversions to/from the sanitized HTML subset.

The allowlist itself is basicbar's ``clean_html``; everything that stores rich
HTML goes through it.
"""
import html as _html
import re

import markdown as _markdown
from basicbar_integrations.html_sanitize import ALLOWED_TAGS, clean_html

clean_rich = clean_html

_TAG_RE = re.compile(r"</?(%s)(\s[^>]*)?/?>" % "|".join(sorted(ALLOWED_TAGS)), re.I)


def looks_like_html(text):
    """True if ``text`` already contains a tag from the rich allowlist."""
    return bool(text) and bool(_TAG_RE.search(text))


def markdown_to_html(text):
    if not text:
        return ""
    return clean_html(
        _markdown.markdown(text, extensions=["extra", "sane_lists", "nl2br"], output_format="html")
    )


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
