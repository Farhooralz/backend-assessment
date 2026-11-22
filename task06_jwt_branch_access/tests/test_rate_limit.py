"""Per-account login throttling backed by shared Redis state."""

import os

import pytest
import redis
from django.conf import settings

from tests.conftest import LOGIN_URL

KEY = "login_failures:analyst"


def _redis() -> redis.Redis:
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", settings.REDIS_HOST),
        port=int(os.environ.get("REDIS_PORT", settings.REDIS_PORT) or "6379"),
        db=settings.REDIS_DB,
    )


def _fail(api) -> object:
    return api.post(LOGIN_URL, {"username": "analyst", "password": "wrong"}, format="json")


@pytest.mark.django_db
def test_spec_sixth_failed_login_returns_429(api, analyst) -> None:
    for _ in range(5):
        assert _fail(api).status_code == 401
    assert _fail(api).status_code == 429


@pytest.mark.django_db
def test_spec_failed_login_counter_is_stored_in_redis_with_window(api, analyst) -> None:
    client = _redis()
    for _ in range(5):
        _fail(api)
    assert int(client.get(KEY)) == 5
    ttl = client.ttl(KEY)
    assert 0 < ttl <= settings.LOGIN_FAILURE_WINDOW_SECONDS


@pytest.mark.django_db
def test_spec_rate_limit_shared_between_workers(api, analyst) -> None:
    worker2 = _redis()  # an independent Redis connection, as a second worker would hold
    for _ in range(3):
        assert _fail(api).status_code == 401
    assert int(worker2.get(KEY)) == 3
    worker2.incr(KEY)  # simulate another worker recording two more failures
    worker2.incr(KEY)
    assert int(_redis().get(KEY)) == 5
    assert _fail(api).status_code == 429


@pytest.mark.django_db
def test_spec_successful_login_resets_counter(api, analyst) -> None:
    for _ in range(3):
        _fail(api)
    assert int(_redis().get(KEY)) == 3
    response = api.post(LOGIN_URL, {"username": "analyst", "password": "pw"}, format="json")
    assert response.status_code == 200
    assert _redis().get(KEY) is None


@pytest.mark.django_db
def test_spec_rate_limit_is_per_account(api, analyst, customer) -> None:
    for _ in range(5):
        assert _fail(api).status_code == 401
    assert _fail(api).status_code == 429
    response = api.post(LOGIN_URL, {"username": "customer", "password": "pw"}, format="json")
    assert response.status_code == 200
