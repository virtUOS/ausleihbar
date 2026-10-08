# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Derived properties for product sets (concept §1.1 / §4.5 / §5.5).

A set is booked from its assigned pool, its availability follows the scarcest
product, and its duration limits come from the products.
"""


def set_lending_type(products):
    """A set is hourly if any product is hourly (the finest unit drives it)."""
    return "hours" if any(p.lending_type == "hours" for p in products) else "days"


def set_durations(products, pool_id=None):
    """(min, max) lending duration of the set in its unit.

    Each product contributes its effective limits (device → product → pool
    default, #109) over its bookable units in the set's pool ``pool_id``
    (without units there: the product's own values). The most restricted
    product drives: max is the shortest product max; a daily product in an
    hourly set is converted days→hours (×24). Min is the longest min among the
    products that share the set's granularity (daily products in an hourly set
    round up, so they don't raise the hourly min).
    """
    from lending.durations import calendar_limits

    unit = set_lending_type(products)
    maxes, mins = [], []
    for product in products:
        if pool_id is None:
            low, high = product.min_duration or None, product.max_duration or None
        else:
            low, high = calendar_limits(product, {pool_id})
        to_hours = unit == "hours" and product.lending_type == "days"
        factor = 24 if to_hours else 1
        if high:
            maxes.append(high * factor)
        if low and product.lending_type == unit:
            mins.append(low)
    return (max(mins) if mins else None, min(maxes) if maxes else None)
