"""Business rules: visibility, login, refresh rotation and logout."""

from uuid import uuid4

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from access import rate_limit, tokens
from access.clocks import utcnow
from access.models import Invoice, LoginSession, Membership


class InvalidCredentials(Exception):
    """Username/password pair did not authenticate."""


class RateLimited(Exception):
    """Too many failed attempts inside the window."""


class InvalidRefresh(Exception):
    """Refresh token is unknown, expired, revoked or being reused."""


def visible_invoices(user):
    """Scope invoices to active analyst branches plus the customer's own rows.

    Queried fresh on every request so a membership change is visible immediately.
    """
    branch_ids = Membership.objects.filter(
        user=user, role=Membership.ROLE_ANALYST, is_active=True
    ).values_list("branch_id", flat=True)
    return Invoice.objects.filter(Q(branch_id__in=branch_ids) | Q(customer=user)).distinct()


def login(username: str, password: str) -> dict:
    """Authenticate, enforce the shared throttle, and open a fresh session."""
    if rate_limit.is_limited(username):
        raise RateLimited("too many failed login attempts")
    user = authenticate(username=username, password=password)
    if user is None:
        rate_limit.record_failure(username)
        raise InvalidCredentials("invalid username or password")
    rate_limit.clear_failures(username)
    session = LoginSession.objects.create(user=user, refresh_jti=uuid4().hex)
    sid = str(session.session_id)
    return {
        "access": tokens.issue_access_token(user.pk, sid),
        "refresh": tokens.issue_refresh_token(user.pk, sid, session.refresh_jti),
    }


def find_session(sid: str) -> LoginSession | None:
    try:
        return LoginSession.objects.select_related("user").get(session_id=sid)
    except (LoginSession.DoesNotExist, ValidationError, ValueError):
        return None


def refresh(refresh_token: str) -> dict:
    """Rotate the refresh jti; replay of an old jti revokes the whole session."""
    try:
        claims = tokens.decode_token(refresh_token, "refresh")
    except tokens.TokenError as exc:
        raise InvalidRefresh("invalid refresh token") from exc
    reused = False
    with transaction.atomic():
        session = find_session(claims.get("sid", ""))
        if (
            session is None
            or not session.is_live
            or session.user_id != claims.get("sub")
            or not session.user.is_active
        ):
            raise InvalidRefresh("session is not active")
        if session.refresh_jti != claims.get("jti"):
            session.revoked_at = utcnow()
            session.save(update_fields=["revoked_at"])
            reused = True
        else:
            session.refresh_jti = uuid4().hex
            session.save(update_fields=["refresh_jti"])
        sid = str(session.session_id)
        result = {
            "access": tokens.issue_access_token(session.user_id, sid),
            "refresh": tokens.issue_refresh_token(session.user_id, sid, session.refresh_jti),
        }
    # The revocation must commit; raising inside the atomic block would roll it back.
    if reused:
        raise InvalidRefresh("refresh token reuse detected")
    return result


def logout(access_claims: dict) -> None:
    """Close exactly the session named by the access token's sid."""
    with transaction.atomic():
        session = find_session(access_claims.get("sid", ""))
        if session is None or session.user_id != access_claims.get("sub"):
            return
        if session.is_live:
            session.revoked_at = utcnow()
            session.save(update_fields=["revoked_at"])
