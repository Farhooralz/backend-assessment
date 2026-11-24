"""Thin HTTP layer; all authorization and token rules live in services."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from access import services, tokens
from access.authentication import JWTAuthentication
from access.serializers import (
    DetailSerializer,
    InvoiceSerializer,
    LoginRequestSerializer,
    LogoutRequestSerializer,
    RefreshRequestSerializer,
    TokenPairSerializer,
    valid_body,
)

_BAD_BODY = {"detail": "invalid request body"}


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginRequestSerializer,
        responses={
            200: TokenPairSerializer,
            400: DetailSerializer,
            401: DetailSerializer,
            429: DetailSerializer,
        },
    )
    def post(self, request) -> Response:
        body = valid_body(request.data, "username", "password")
        if body is None:
            return Response(_BAD_BODY, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = services.login(body["username"], body["password"])
        except services.RateLimited:
            return Response({"detail": "too many failed login attempts"}, status=429)
        except services.InvalidCredentials:
            return Response({"detail": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(data, status=status.HTTP_200_OK)


class RefreshView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=RefreshRequestSerializer,
        responses={200: TokenPairSerializer, 400: DetailSerializer, 401: DetailSerializer},
    )
    def post(self, request) -> Response:
        body = valid_body(request.data, "refresh")
        if body is None:
            return Response(_BAD_BODY, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = services.refresh(body["refresh"])
        except services.InvalidRefresh:
            return Response(
                {"detail": "invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Close a session using a verified access token or a refresh token in the body."""

    authentication_classes: list = []  # chosen explicitly per request below
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request) -> str:
        # DRF converts AuthenticationFailed to 403 when no authenticator supplies
        # a header; logout has none of its own, so advertise Bearer explicitly.
        return "Bearer"

    @extend_schema(
        request=LogoutRequestSerializer,
        responses={204: None, 400: DetailSerializer, 401: DetailSerializer},
    )
    def post(self, request) -> Response:
        body = valid_body(request.data)
        if body is None:
            return Response(_BAD_BODY, status=status.HTTP_400_BAD_REQUEST)
        refresh = body.get("refresh")
        if refresh is not None:
            # An expired access token must not stop a client closing its session.
            try:
                claims = tokens.decode_token(refresh, "refresh")
            except tokens.TokenError as exc:
                raise AuthenticationFailed("invalid or expired refresh token") from exc
        else:
            if JWTAuthentication().authenticate(request) is None:
                raise AuthenticationFailed("invalid or expired access token")
            claims = request.jwt_claims  # already verified by the authentication class
        services.logout(claims)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceViewSet(ReadOnlyModelViewSet):
    """The IDOR fix: every action reads only rows visible to this user."""

    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return services.visible_invoices(self.request.user)
