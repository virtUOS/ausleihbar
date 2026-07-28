# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Root URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from basicbar_auth.oidc import SilentLoginView, backchannel_logout
from accounts.views import SetLanguageView, logout_view, whoami

urlpatterns = [
    path("admin/", admin.site.urls),
    path("oidc/logout-redirect/", logout_view, name="spa-logout"),
    path("oidc/silent/", SilentLoginView.as_view(), name="oidc-silent"),
    path(
        "oidc/backchannel-logout/",
        backchannel_logout,
        name="oidc-backchannel-logout",
    ),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("api/whoami/language/", SetLanguageView.as_view()),
    path("api/whoami/", whoami),
    path("api/", include("lending.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("accounts.urls")),
]

# Serve uploaded media during local development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
