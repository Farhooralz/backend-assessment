"""Login, refresh-rotation and logout/session-separation tests."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

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


@pytest.mark.django_db
def test_spec_refresh_locks_session_row_with_for_update(api, analyst) -> None:
    pair = login(api)
    with CaptureQueriesContext(connection) as ctx:
        response = api.post(REFRESH_URL, {"refresh": pair["refresh"]}, format="json")
    assert response.status_code == 200
    assert any("FOR UPDATE" in query["sql"] for query in ctx.captured_queries)


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(25)
def test_spec_concurrent_refresh_rotation_has_one_winner(api, analyst) -> None:
    pair = login(api)
    barrier = threading.Barrier(2)
    statuses: list[int | None] = [None, None]
    payloads: list[dict] = [{}, {}]

    def worker(index: int) -> None:
        worker_api = APIClient()
        try:
            barrier.wait(timeout=10)
            response = worker_api.post(REFRESH_URL, {"refresh": pair["refresh"]}, format="json")
            statuses[index] = response.status_code
            if response.status_code == 200:
                payloads[index] = dict(response.data)
        finally:
            connection.close()  # each thread owns a separate PostgreSQL connection

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, range(2)))

    assert sorted(statuses) == [200, 401], statuses
    winner = next(payload for payload in payloads if payload)
    sid = tokens.decode_token(pair["access"], "access")["sid"]
    session = LoginSession.objects.get(session_id=sid)
    assert session.revoked_at is not None  # the loser's stale-token reuse closed the session
    replay = api.post(REFRESH_URL, {"refresh": winner["refresh"]}, format="json")
    assert replay.status_code == 401
