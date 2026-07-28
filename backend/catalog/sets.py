# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Derived properties for product sets (concept §1.1 / §4.5 / §5.5).

A set is booked from its assigned pool, its availability follows the scarcest
product, and its duration limits come from the products.
"""


def set_lending_type(products):
    """A set is hourly if any product is hourly (the finest unit drives it)."""
    return "hours" if any(p.lending_type == "hours" for p in products) else "days"


def set_durations(products):
    """(min, max) lending duration of the set in its unit.

    Max is the shortest product max (the binding one); a daily product in an
    hourly set is converted days→hours (×24). Min is the longest min among the
    products that share the set's granularity (daily products in an hourly set
    round up, so they don't raise the hourly min).
    """
    unit = set_lending_type(products)
    maxes, mins = [], []
    for product in products:
        to_hours = unit == "hours" and product.lending_type == "days"
        factor = 24 if to_hours else 1
        if product.max_duration:
            maxes.append(product.max_duration * factor)
        if product.min_duration and product.lending_type == unit:
            mins.append(product.min_duration)
    return (max(mins) if mins else None, min(maxes) if maxes else None)
