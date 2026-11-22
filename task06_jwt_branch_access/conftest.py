"""Create this task's database and isolate its Redis index before tests run."""

import contextlib
import os

import psycopg
import pytest
import redis
from psycopg import errors as pg_errors

TASK_DB = "task06"
REDIS_DB = 6


def _pg_kwargs(dbname: str) -> dict:
    kwargs = {
        "dbname": dbname,
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
    }
    port = os.environ.get("POSTGRES_PORT", "5432")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if port:
        kwargs["port"] = int(port)
    if password:
        kwargs["password"] = password
    return kwargs


def pytest_configure() -> None:
    with (
        psycopg.connect(**_pg_kwargs("postgres"), autocommit=True) as conn,
        contextlib.suppress(pg_errors.DuplicateDatabase),
    ):
        conn.execute(f"CREATE DATABASE {TASK_DB}")


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
