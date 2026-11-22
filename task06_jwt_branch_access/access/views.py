"""Thin HTTP layer; all authorization and token rules live in services."""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from access import services, tokens
from access.serializers import InvoiceSerializer

logger = logging.getLogger(__name__)


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        username = request.data.get("username", "")
        logger.info("login attempt for user %s", username)
        try:
            data = services.login(username, request.data.get("password", ""))
        except services.RateLimited:
            return Response({"detail": "too many failed login attempts"}, status=429)
        except services.InvalidCredentials:
            return Response({"detail": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(data, status=status.HTTP_200_OK)


class RefreshView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        try:
            data = services.refresh(request.data.get("refresh", ""))
        except services.InvalidRefresh:
            return Response(
                {"detail": "invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        claims = tokens.decode_token(request.auth, "access")
        services.logout(claims)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceViewSet(ReadOnlyModelViewSet):
    """The IDOR fix: every action reads only rows visible to this user."""

    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return services.visible_invoices(self.request.user)
