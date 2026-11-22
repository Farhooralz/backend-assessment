"""Spec tests for the shared database bootstrap helper and management command."""

import os
from collections.abc import Iterator

import psycopg
import pytest
from django.core.management import call_command
from psycopg import sql

from reports.db_utils import connection_kwargs, ensure_database

SCRATCH_DB = "task03_ensure_db_idempotent_test"


def _admin_connection() -> psycopg.Connection:
    return psycopg.connect(**connection_kwargs("postgres"), autocommit=True)


def _drop(name: str) -> None:
    with _admin_connection() as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


@pytest.fixture
def scratch_db() -> Iterator[str]:
    _drop(SCRATCH_DB)
    yield SCRATCH_DB
    _drop(SCRATCH_DB)


def test_spec_ensure_database_is_idempotent(scratch_db: str) -> None:
    """Creating a missing database twice is safe and leaves it connectable."""
    ensure_database(scratch_db)
    ensure_database(scratch_db)

    with _admin_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_database WHERE datname = %s", (scratch_db,))
        assert cur.fetchone() == (1,)

    with psycopg.connect(**connection_kwargs(scratch_db)) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_spec_ensure_db_command_is_repeatable(scratch_db: str) -> None:
    """The management command used by the README Run steps is also idempotent."""
    call_command("ensure_db", "--name", scratch_db, verbosity=0)
    call_command("ensure_db", "--name", scratch_db, verbosity=0)

    with _admin_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_database WHERE datname = %s", (scratch_db,))
        assert cur.fetchone() == (1,)


def test_spec_connection_kwargs_reads_env_contract() -> None:
    """Settings come from the documented environment variables, never literals."""
    kwargs = connection_kwargs("task03")
    assert kwargs["dbname"] == "task03"
    assert kwargs["user"] == os.environ.get("POSTGRES_USER", "assessment")
    assert kwargs["host"] == os.environ.get("POSTGRES_HOST", "localhost")
    assert kwargs["password"] == os.environ.get("POSTGRES_PASSWORD", "")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if port:
        assert kwargs["port"] == port
    else:
        assert "port" not in kwargs
