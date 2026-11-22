"""Idempotent PostgreSQL bootstrap shared by pytest setup and ``manage.py ensure_db``."""

import contextlib
import os

import psycopg
from psycopg import errors as pg_errors
from psycopg import sql


def _maintenance_kwargs() -> dict:
    """Parameters for the maintenance database; empty port/password mean unix socket trust."""
    kwargs = {
        "dbname": "postgres",
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


def ensure_database(db_name: str) -> None:
    """Create ``db_name`` if absent; tolerates concurrent or repeated callers."""
    with (
        psycopg.connect(**_maintenance_kwargs(), autocommit=True) as conn,
        contextlib.suppress(pg_errors.DuplicateDatabase),
    ):
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
