# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Prompt builders for AI-assisted catalog editing."""

from .serializers import _ATTR_TYPES

_TYPES = ", ".join(sorted(_ATTR_TYPES))

# Fields the system already tracks per physical unit (Resource) or on the
# product itself — the model must not propose these as product-type attributes,
# because doing so duplicates a built-in field (e.g. the inventory number /
# Bestandsnummer). Also used server-side to drop such entries defensively.
RESERVED_ATTRIBUTE_KEYS = frozenset({
    # per-unit Resource fields
    "inventory_number", "qr_code_id", "serial_number", "status", "defect_note",
    "storage_location", "procurement_date", "warranty_end", "value",
    "procuring_institution", "owning_institution",
    # product-level fields
    "title", "name", "description", "lending_type", "min_duration",
    "max_duration", "return_info",
})


def build_attribute_prompt(name, description, hints, existing_keys) -> tuple[str, str]:
    """Return (system, user) prompts asking the model for inventory-relevant
    attributes for a product type, as strict JSON. The type's ``name`` and
    ``description`` are the context; ``hints`` are optional extra guidance from
    the editor. Any of the three may be empty (at least one is set)."""
    system = (
        "You help configure a device/room lending catalogue. For the described "
        "product type, propose a compact list of recurring, inventory-relevant "
        "attributes. Reply with STRICT JSON only, an object of the form "
        '{"attributes": [ {"key": "...", "label": {"de": "...", "en": "..."}, '
        '"type": "...", "default": "", "visible": true, "required": false} ]}. '
        "Rules: key is snake_case (letters, digits, underscore; starts with a "
        f"letter). label has short technical terms in German and English. type "
        f"is exactly one of: {_TYPES}. Set visible=true for borrower-relevant "
        "specs (e.g. resolution) and false for internal fields. Set "
        "required=true only for fields that are always needed. "
        "Do NOT propose fields the system already tracks per physical unit or on "
        "the product itself: inventory number (Bestandsnummer), QR code id, "
        "serial number, status, defect note, storage location, procurement date, "
        "warranty end, value, owning/procuring institution, and the product's own "
        "title/name/description/lending duration. "
        "At most 12 attributes, no duplicates, no prose outside the JSON."
    )
    parts = []
    if name:
        parts.append(f"Product type name: {name}")
    if description:
        parts.append(f"Description: {description}")
    if hints:
        parts.append(f"Additional hints: {hints}")
    user = "\n".join(parts)
    if existing_keys:
        user += "\nDo not propose these existing keys again: " + ", ".join(sorted(existing_keys))
    return system, user


def build_product_extraction_prompt(product_type, pdf_text) -> tuple[str, str]:
    """Return (system, user) prompts asking the model to extract catalogue data
    for the given product type from a device manual's text, as strict JSON."""
    schema = product_type.attribute_schema or []
    lines = []
    for attr in schema:
        label = attr.get("label")
        if isinstance(label, dict):
            label = label.get("de") or label.get("en") or attr.get("key")
        lines.append(f"- {attr.get('key')} — {label} — {attr.get('type')}")
    attr_block = "\n".join(lines) if lines else "(none)"
    system = (
        "You extract catalogue data for a device/room lending system from the "
        "text of a product's manual. Reply with STRICT JSON only, an object: "
        '{"title": {"de": "...", "en": "..."}, "description": {"de": "...", '
        '"en": "..."}, "attributes": { "<key>": <value> }}. '
        "title: short (manufacturer + model). description: 1-3 factual sentences. "
        "Provide title and description in BOTH German and English. "
        "For attributes, fill ONLY the given keys, each value matching its type "
        "(number as a number, date as YYYY-MM-DD; for short_text/long_text give "
        'an object {"de": "...", "en": "..."} with both languages; otherwise short '
        "text). Omit a key entirely if the manual does not state it — never invent "
        "values. No prose outside the JSON."
    )
    user = f"Attributes (key — label — type):\n{attr_block}\n\nManual text:\n{pdf_text}"
    return system, user
