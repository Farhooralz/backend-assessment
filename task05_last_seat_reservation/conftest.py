"""Create the isolated task database before pytest-django connects to it."""

import contextlib
import os

import psycopg
import pytest

DB_NAME = "task05"


def _pg_params(dbname: str) -> dict[str, str]:
    """Translate the shared env contract into psycopg connection parameters."""
    params = {
        "dbname": dbname,
        "user": os.environ.get("POSTGRES_USER", "assessment"),
    }
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    # Empty values are meaningful: the fallback uses a unix socket with no password.
    if host:
        params["host"] = host
    if port:
        params["port"] = port
    if password:
        params["password"] = password
    return params


@pytest.fixture(scope="session", autouse=True)
def ensure_task_database() -> None:
    """Django can only create test_task05 once the task05 database exists."""
    with (
        psycopg.connect(**_pg_params("postgres"), autocommit=True) as conn,
        contextlib.suppress(psycopg.errors.DuplicateDatabase),
    ):
        conn.execute(f'CREATE DATABASE "{DB_NAME}"')
