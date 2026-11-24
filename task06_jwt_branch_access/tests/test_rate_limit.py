"""Per-account login throttling backed by one atomic Lua script in shared Redis."""

import multiprocessing
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from django.conf import settings
from django.db import connection
from rest_framework.test import APIClient

from access import rate_limit
from tests.conftest import LOGIN_URL
from tests.rate_limit_worker import run as spawn_worker

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


@pytest.mark.django_db
def test_spec_first_failed_login_sets_ttl_atomically(api, analyst) -> None:
    assert _fail(api).status_code == 401
    assert int(_redis().get(KEY)) == 1
    assert 0 < _redis().ttl(KEY) <= settings.LOGIN_FAILURE_WINDOW_SECONDS


class _RecordingClient:
    """Record Redis commands so a non-atomic INCR+EXPIRE pair becomes visible."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client
        self.commands: list[tuple[str, tuple]] = []

    def eval(self, *args: object) -> object:
        self.commands.append(("EVAL", args))
        return self._client.eval(*args)

    def incr(self, key: str) -> int:
        self.commands.append(("INCR", (key,)))
        return self._client.incr(key)

    def expire(self, key: str, seconds: int) -> bool:
        self.commands.append(("EXPIRE", (key, seconds)))
        return self._client.expire(key, seconds)


@pytest.mark.django_db
def test_spec_record_failure_uses_one_atomic_lua_script(monkeypatch) -> None:
    spy = _RecordingClient(_redis())
    monkeypatch.setattr(rate_limit, "redis_client", lambda: spy)
    assert rate_limit.record_failure("atomic-user") == 1
    assert [name for name, _ in spy.commands] == ["EVAL"]
    script = spy.commands[0][1][0]
    assert "INCR" in script and "EXPIRE" in script
    ttl = _redis().ttl(rate_limit.failure_key("atomic-user"))
    assert 0 < ttl <= settings.LOGIN_FAILURE_WINDOW_SECONDS


@pytest.mark.django_db
def test_spec_failed_login_does_not_precheck_counter(api, analyst, monkeypatch) -> None:
    def forbidden_precheck(username: str) -> bool:
        raise AssertionError("racy check-then-record is still present")

    monkeypatch.setattr(rate_limit, "is_limited", forbidden_precheck)
    assert _fail(api).status_code == 401


@pytest.mark.django_db
def test_spec_counter_expires_without_further_process_calls(api, analyst, monkeypatch) -> None:
    monkeypatch.setattr(settings, "LOGIN_FAILURE_WINDOW_SECONDS", 1)
    assert _fail(api).status_code == 401
    client = _redis()
    assert 0 < client.ttl(KEY) <= 1
    deadline = time.monotonic() + 3
    while client.exists(KEY) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not client.exists(KEY)  # Redis alone clears it, even if the worker died


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(25)
def test_spec_sixth_failed_login_across_concurrent_workers(api, analyst, monkeypatch) -> None:
    local = threading.local()

    def worker_client() -> redis.Redis:
        if not hasattr(local, "client"):
            local.client = _redis()
        return local.client

    monkeypatch.setattr(rate_limit, "redis_client", worker_client)
    barrier = threading.Barrier(6)
    statuses: list[int | None] = [None] * 6

    def worker(index: int) -> None:
        own_client = _redis()  # each worker owns a distinct Redis connection
        local.client = own_client
        try:
            barrier.wait(timeout=10)
            response = APIClient().post(
                LOGIN_URL, {"username": "analyst", "password": "wrong"}, format="json"
            )
            statuses[index] = response.status_code
            assert int(own_client.get(KEY)) >= 1
        finally:
            connection.close()  # each thread owns a separate PostgreSQL connection

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(worker, range(6)))

    assert statuses.count(429) == 1, statuses
    assert statuses.count(401) == 5, statuses
    assert int(_redis().get(KEY)) == 6


@pytest.mark.django_db
def test_spec_correct_password_rejected_while_locked(api, analyst) -> None:
    for _ in range(5):
        assert _fail(api).status_code == 401
    response = api.post(LOGIN_URL, {"username": "analyst", "password": "pw"}, format="json")
    assert response.status_code == 429
    assert int(_redis().get(KEY)) == 5  # a rejected correct-password attempt is not counted


@pytest.mark.django_db(transaction=True)
@pytest.mark.timeout(90)
def test_spec_sixth_failed_login_across_real_processes(api, analyst) -> None:
    """Six spawned workers share one Redis counter, whatever process they run in."""
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(6)
    queue = ctx.Queue()
    db_name = connection.settings_dict["NAME"]
    processes = [
        ctx.Process(target=spawn_worker, args=(db_name, barrier, queue, "analyst"))
        for _ in range(6)
    ]
    for process in processes:
        process.start()
    try:
        statuses = [queue.get(timeout=60) for _ in processes]
    finally:
        for process in processes:
            process.join(timeout=30)
    assert [process.exitcode for process in processes] == [0] * 6
    assert statuses.count(401) == 5, statuses
    assert statuses.count(429) == 1, statuses
    assert int(_redis().get(KEY)) == 6
