"""JWT issue/verify helpers with an injectable clock for deterministic expiry tests."""

from datetime import datetime, timedelta
from uuid import uuid4

import jwt
from django.conf import settings

from access.clocks import utcnow

ACCESS_TTL = timedelta(minutes=5)
REFRESH_TTL = timedelta(days=7)


class TokenError(Exception):
    """Base class for token failures."""


class InvalidToken(TokenError):
    """The token is malformed, wrongly typed or has the wrong signature."""


class ExpiredToken(TokenError):
    """The token's exp claim is in the past."""


def _resolved_now(now: datetime | None) -> datetime:
    return now if now is not None else utcnow()


def issue_access_token(user_id: int, session_id: str, *, now: datetime | None = None) -> str:
    """Create a short-lived access token bound to a live session id."""
    moment = _resolved_now(now)
    payload = {
        "sub": user_id,
        "sid": str(session_id),
        "type": "access",
        "jti": uuid4().hex,
        "iat": moment,
        "exp": moment + ACCESS_TTL,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def issue_refresh_token(
    user_id: int, session_id: str, jti: str, *, now: datetime | None = None
) -> str:
    """Create a long-lived refresh token whose jti is stored on the session."""
    moment = _resolved_now(now)
    payload = {
        "sub": user_id,
        "sid": str(session_id),
        "type": "refresh",
        "jti": jti,
        "iat": moment,
        "exp": moment + REFRESH_TTL,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str, *, now: datetime | None = None) -> dict:
    """Verify signature and expiry against the supplied clock, then return claims."""
    moment = _resolved_now(now)
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_exp": False,  # checked against the injectable clock below
                "verify_iat": False,
                "verify_nbf": False,
                "verify_sub": False,  # our subject is an integer user id
            },
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidToken("invalid token") from exc
    if payload.get("type") != expected_type:
        raise InvalidToken("wrong token type")
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise InvalidToken("missing exp claim")
    if exp <= moment.timestamp():
        raise ExpiredToken("token has expired")
    return payload
