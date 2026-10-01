# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Catalog structure helpers (issue #20: product types replace categories).

``derive_section_types`` turns the old Section → Category → Product structure
into the new Section → ProductType → Product one. It works on plain data only
(no models, no ORM) so both the data migration (with historical models) and the
ZIP import of old archives can feed it.
"""


def derive_section_types(sections):
    """Derive each section's product types from its former categories.

    ``sections`` is an ordered list (section display order) of::

        {"key": <section key>,
         "categories": [                      # in the section's category order
             {"key": <category key>,
              "products": [                   # in the category's product order
                  {"product_type": <type key>, "title": <str>}, ...]},
             ...]}

    Keys can be anything hashable (ids, titles). The caller is responsible for
    the input ordering and for leaving out trashed rows.

    Returns ``(section_types, category_types)``:

    * ``section_types`` — ``{section_key: [type keys]}``: the product types of
      the section's categories' products in first-appearance order (categories
      in order, products in order), without duplicates.
    * ``category_types`` — ``{category_key: type_key | None}``: the single
      product type of a category whose products all share one type, else
      ``None`` (no products, or products of several types).

    Both dicts preserve input order, so iterating ``section_types`` and its
    lists yields the global first-appearance order of the types.
    """
    section_types = {}
    category_types = {}
    for section in sections:
        seen = set()
        types = []
        for category in section.get("categories", []):
            category_seen = []
            for product in category.get("products", []):
                type_key = product["product_type"]
                if type_key not in category_seen:
                    category_seen.append(type_key)
                if type_key not in seen:
                    seen.add(type_key)
                    types.append(type_key)
            category_types[category["key"]] = (
                category_seen[0] if len(category_seen) == 1 else None
            )
        section_types[section["key"]] = types
    return section_types, category_types
