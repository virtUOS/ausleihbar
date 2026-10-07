# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Catalog structure helpers (#78: categories return as shop navigation).

``categories_from_types`` maps the ADR-0010 navigation (Section → ProductType
→ Product) onto categories (Section → Category → Product). It works on plain
data only (no models, no ORM), so the ZIP import of ADR-0010-era archives can
feed it with natural keys.

Note: migration ``catalog/0052_product_types_to_categories`` applies the same
rules to the database with its own frozen code; changes here do not (and must
not) affect it.
"""


def categories_from_types(types, sections):
    """Which product types become top-level categories, and each section's
    category order.

    ``types`` — every (live) product type: ``{"key", "name", "position"}``.
    ``sections`` — ``{"key", "types": [type keys in the section],
    "type_order": [type keys]}`` (the section's ``product_type_order``).
    Keys can be anything hashable (ids, names); unknown type keys are ignored.

    Returns ``(converted, section_categories)``:

    * ``converted`` — the keys of the types that sit in at least one section,
      by ``(position, name)``: each becomes one top-level category;
    * ``section_categories`` — ``{section key: [type keys]}``: the section's
      ``type_order`` entries that are in the section, then the section's other
      types in ``converted`` order (like before, unordered types sort after).
    """
    by_key = {t["key"]: t for t in types}
    in_sections = {
        key for section in sections for key in section.get("types", []) if key in by_key
    }
    converted = sorted(
        in_sections, key=lambda k: (by_key[k].get("position") or 0, by_key[k]["name"])
    )
    section_categories = {}
    for section in sections:
        members = {k for k in section.get("types", []) if k in by_key}
        order = list(dict.fromkeys(k for k in section.get("type_order", []) if k in members))
        order += [k for k in converted if k in members and k not in order]
        section_categories[section["key"]] = order
    return converted, section_categories
