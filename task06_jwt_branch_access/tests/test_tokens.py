"""Token-format, lifetime and controlled-clock tests (no DB required)."""

from datetime import timedelta

import jwt
import pytest
from django.conf import settings

from access import tokens
from access.clocks import utcnow


def test_spec_uses_jwt_library() -> None:
    token = tokens.issue_access_token(7, "session-7")
    assert token.count(".") == 2  # a compact JWS: header.payload.signature
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": False, "verify_sub": False},
    )
    assert payload["sub"] == 7
    assert payload["type"] == "access"


def test_spec_access_token_lifetime_is_five_minutes() -> None:
    t0 = utcnow()
    token = tokens.issue_access_token(1, "s", now=t0)
    tokens.decode_token(token, "access", now=t0 + timedelta(minutes=4, seconds=59))
    with pytest.raises(tokens.ExpiredToken):
        tokens.decode_token(token, "access", now=t0 + timedelta(minutes=5))


def test_spec_refresh_token_lifetime_is_seven_days() -> None:
    t0 = utcnow()
    token = tokens.issue_refresh_token(1, "s", "jti", now=t0)
    tokens.decode_token(token, "refresh", now=t0 + timedelta(days=7, seconds=-1))
    with pytest.raises(tokens.ExpiredToken):
        tokens.decode_token(token, "refresh", now=t0 + timedelta(days=7))


def test_spec_access_token_carries_sid() -> None:
    token = tokens.issue_access_token(3, "session-3")
    assert tokens.decode_token(token, "access")["sid"] == "session-3"


def test_spec_wrong_token_type_is_rejected() -> None:
    access = tokens.issue_access_token(1, "s")
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_token(access, "refresh")


def test_spec_tampered_token_is_rejected() -> None:
    token = tokens.issue_access_token(1, "s")
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_token(token + "tampered", "access")
