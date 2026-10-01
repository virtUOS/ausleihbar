# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Root URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import whoami
from common.views import csp_report

urlpatterns = [
    # Not /admin/: that prefix belongs to the SPA's own admin routes (#48).
    path("django-admin/", admin.site.urls),
    # OIDC login/logout/silent/back-channel/callback and api/whoami/language/.
    path("", include("basicbar_auth.urls")),
    path("api/csp-report/", csp_report, name="csp-report"),
    path("api/whoami/", whoami),
    path("api/", include("lending.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("accounts.urls")),
]

# Serve uploaded media during local development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
