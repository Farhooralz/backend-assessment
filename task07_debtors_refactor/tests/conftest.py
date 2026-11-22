"""Create the isolated task database before pytest-django builds test_task07."""

import contextlib
import os
from types import SimpleNamespace

import psycopg
import pytest

DB_NAME = "task07"


def _pg_kwargs() -> dict[str, str]:
    """Map the shared env contract to psycopg arguments (empty values are omitted)."""
    kwargs = {"user": os.environ.get("POSTGRES_USER", "assessment")}
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if host:
        kwargs["host"] = host
    if port:
        kwargs["port"] = port
    if password:
        kwargs["password"] = password
    return kwargs


def pytest_configure() -> None:
    """Create task07 once; pytest-django then creates test_task07 from its migrations."""
    with (
        psycopg.connect(dbname="postgres", autocommit=True, **_pg_kwargs()) as conn,
        contextlib.suppress(psycopg.errors.DuplicateDatabase),
    ):
        conn.execute(f"CREATE DATABASE {DB_NAME}")


@pytest.fixture
def user() -> SimpleNamespace:
    return SimpleNamespace(id=42)
