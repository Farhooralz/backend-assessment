"""URL configuration for the token endpoints and the invoice viewset."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from access import views

router = DefaultRouter()
router.register("invoices", views.InvoiceViewSet, basename="invoice")

urlpatterns = [
    path("api/token/", views.LoginView.as_view(), name="token-login"),
    path("api/token/refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("api/token/logout/", views.LogoutView.as_view(), name="token-logout"),
    path("api/", include(router.urls)),
]
