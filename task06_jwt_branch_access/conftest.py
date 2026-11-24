"""Create this task's database and isolate its Redis index before tests run."""

import os

import pytest
import redis

from access.db_utils import ensure_database

TASK_DB = "task06"
REDIS_DB = 6


def pytest_configure() -> None:
    ensure_database(TASK_DB)


@pytest.fixture(scope="session", autouse=True)
def clean_redis() -> object:
    client = redis.Redis(
        host=os.environ.get("REDIS_HOST", "127.0.0.1"),
        port=int(os.environ.get("REDIS_PORT", "6379") or "6379"),
        db=REDIS_DB,
    )
    client.flushdb()
    yield client
    client.flushdb()
