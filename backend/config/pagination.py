# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Default API pagination.

Page-numbered with a fixed default size, but clients may request a larger page
via ``?page_size=`` (capped) — used by admin pickers that need the full list of
options while normal list views page through 25 at a time.
"""
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 2000
