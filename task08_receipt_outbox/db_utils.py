"""Idempotent database creation shared by pytest and the ``ensure_db`` command."""

import os

import psycopg
from psycopg import sql

DEFAULT_DB_NAME = "task08"


def pg_params(dbname: str) -> dict[str, object]:
    """Build psycopg connection parameters from the shared environment contract."""
    port = os.environ.get("POSTGRES_PORT", "5432")
    return {
        "dbname": dbname,
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(port) if port else 5432,
    }


def ensure_database(dbname: str = DEFAULT_DB_NAME) -> None:
    """Create the target database if absent; safe to call repeatedly."""
    with psycopg.connect(**pg_params("postgres"), autocommit=True) as conn:
        found = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not found:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
