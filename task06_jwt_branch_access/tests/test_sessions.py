"""Login, refresh-rotation and logout/session-separation tests."""

import pytest
from django.contrib.auth import get_user_model

from access import tokens
from access.models import LoginSession
from tests.conftest import INVOICES_URL, LOGOUT_URL, REFRESH_URL, auth, login


@pytest.mark.django_db
def test_spec_login_returns_access_and_refresh_tokens(api, analyst) -> None:
    data = login(api)
    assert set(data) == {"access", "refresh"}
    assert tokens.decode_token(data["access"], "access")["sub"] == analyst.pk
    assert tokens.decode_token(data["refresh"], "refresh")["type"] == "refresh"
    assert LoginSession.objects.filter(user=analyst, revoked_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_spec_refresh_returns_new_token_pair(api, analyst) -> None:
    data = login(api)
    response = api.post(REFRESH_URL, {"refresh": data["refresh"]}, format="json")
    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}
    assert tokens.decode_token(response.data["access"], "access")["sub"] == analyst.pk


@pytest.mark.django_db
def test_spec_refresh_token_is_rotated_after_use(api, analyst) -> None:
    data = login(api)
    old_jti = tokens.decode_token(data["refresh"], "refresh")["jti"]
    response = api.post(REFRESH_URL, {"refresh": data["refresh"]}, format="json")
    assert response.status_code == 200
    new_jti = tokens.decode_token(response.data["refresh"], "refresh")["jti"]
    assert new_jti != old_jti
    session = LoginSession.objects.get(
        session_id=tokens.decode_token(data["access"], "access")["sid"]
    )
    assert session.refresh_jti == new_jti
    replay = api.post(REFRESH_URL, {"refresh": data["refresh"]}, format="json")
    assert replay.status_code == 401


@pytest.mark.django_db
def test_spec_reuse_of_old_refresh_revokes_session(api, analyst) -> None:
    data = login(api)
    session_id = tokens.decode_token(data["access"], "access")["sid"]
    first = api.post(REFRESH_URL, {"refresh": data["refresh"]}, format="json")
    rotated = first.data["refresh"]
    replay = api.post(REFRESH_URL, {"refresh": data["refresh"]}, format="json")
    assert replay.status_code == 401
    session = LoginSession.objects.get(session_id=session_id)
    assert session.revoked_at is not None
    fresh = api.post(REFRESH_URL, {"refresh": rotated}, format="json")
    assert fresh.status_code == 401


@pytest.mark.django_db
def test_spec_logout_revokes_session_and_access_token(api, analyst) -> None:
    data = login(api)
    assert api.get(INVOICES_URL, **auth(data["access"])).status_code == 200
    response = api.post(LOGOUT_URL, **auth(data["access"]))
    assert response.status_code in (200, 204)
    session = LoginSession.objects.get(
        session_id=tokens.decode_token(data["access"], "access")["sid"]
    )
    assert session.revoked_at is not None
    assert api.get(INVOICES_URL, **auth(data["access"])).status_code == 401


@pytest.mark.django_db
def test_spec_two_sessions_are_independent(api, analyst) -> None:
    first = login(api)
    second = login(api)
    assert LoginSession.objects.filter(user=analyst).count() == 2
    api.post(LOGOUT_URL, **auth(first["access"]))
    assert api.get(INVOICES_URL, **auth(first["access"])).status_code == 401
    assert api.get(INVOICES_URL, **auth(second["access"])).status_code == 200
    refresh = api.post(REFRESH_URL, {"refresh": second["refresh"]}, format="json")
    assert refresh.status_code == 200


@pytest.mark.django_db
def test_spec_access_token_sid_checked_each_request(api, analyst) -> None:
    data = login(api)
    session = LoginSession.objects.get(
        session_id=tokens.decode_token(data["access"], "access")["sid"]
    )
    assert api.get(INVOICES_URL, **auth(data["access"])).status_code == 200
    LoginSession.objects.filter(pk=session.pk).update(revoked_at=session.created_at)
    assert api.get(INVOICES_URL, **auth(data["access"])).status_code == 401


@pytest.mark.django_db
def test_spec_login_rejects_bad_password(api, analyst) -> None:
    response = api.post("/api/token/", {"username": "analyst", "password": "wrong"}, format="json")
    assert response.status_code == 401
    assert not LoginSession.objects.exists()


@pytest.mark.django_db
def test_spec_login_rejects_unknown_user(api, db) -> None:
    response = api.post("/api/token/", {"username": "nobody", "password": "pw"}, format="json")
    assert response.status_code == 401
    assert get_user_model().objects.filter(username="nobody").exists() is False
