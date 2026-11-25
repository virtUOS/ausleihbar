# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Root URL configuration."""
from basicbar_lti.views import lti_jwks, lti_login, lti_register
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import whoami
from common.views import MetricsView, csp_report

urlpatterns = [
    # Not /admin/: that prefix belongs to the SPA's own admin routes (#48).
    path("django-admin/", admin.site.urls),
    # OIDC login/logout/silent/back-channel/callback and api/whoami/language/.
    path("", include("basicbar_auth.urls")),
    # Prometheus scrape endpoint, outside /api/; token-guarded inside the view.
    path("metrics", MetricsView.as_view()),
    # LTI 1.3 tool endpoints (OIDC initiation, public keys); the course
    # launch and the instructor's course pages live in the lti app.
    path("lti/login/", lti_login, name="lti-login"),
    path("lti/jwks/", lti_jwks, name="lti-jwks"),
    path("lti/register/", lti_register, name="lti-register"),
    path("", include("lti.urls")),
    path("api/csp-report/", csp_report, name="csp-report"),
    path("api/whoami/", whoami),
    path("api/", include("lti.api_urls")),
    path("api/", include("lending.urls")),
    path("api/", include("desksharing.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("accounts.urls")),
]

# Serve uploaded media during local development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
