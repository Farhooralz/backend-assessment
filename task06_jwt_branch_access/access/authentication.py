"""DRF authentication: verify the access JWT and that its session is still live."""

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from access import tokens
from access.services import find_session


class JWTAuthentication(BaseAuthentication):
    """Accept ``Authorization: Bearer <access token>`` only for live sessions."""

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "").split()
        if len(header) != 2 or header[0].lower() != "bearer":
            return None
        token = header[1]
        try:
            claims = tokens.decode_token(token, "access")
        except tokens.TokenError as exc:
            raise AuthenticationFailed("invalid or expired access token") from exc
        session = find_session(claims.get("sid", ""))
        if (
            session is None
            or not session.is_live
            or session.user_id != claims.get("sub")
            or not session.user.is_active
        ):
            raise AuthenticationFailed("session is not active")
        return (session.user, token)

    def authenticate_header(self, request) -> str:
        return "Bearer"
