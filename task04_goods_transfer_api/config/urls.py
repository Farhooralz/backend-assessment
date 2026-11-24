"""Root URL configuration: public docs plus the authenticated transfer API."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

# Docs are intentionally public; the transfer viewset keeps its own auth and permissions.
public_docs = {
    "permission_classes": [AllowAny],
    "authentication_classes": [],
}

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(**public_docs), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema", **public_docs),
        name="api-docs",
    ),
    path("api/auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("api/", include("transfer.urls")),
]
