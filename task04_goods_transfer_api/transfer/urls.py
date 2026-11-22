"""Router registration for the transfer API."""

from rest_framework.routers import DefaultRouter

from transfer.views import TransferRequestViewSet

router = DefaultRouter()
router.register("transfers", TransferRequestViewSet, basename="transfer")

urlpatterns = router.urls
