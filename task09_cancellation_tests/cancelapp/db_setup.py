"""Idempotent creation of this task's PostgreSQL database from the shared env."""

from __future__ import annotations

import os

import psycopg
from psycopg import sql

DB_NAME = "task09"


def _connection_parameters(database: str) -> dict[str, str | int]:
    """Map the env contract to psycopg, dropping empty socket-style values."""
    parameters: dict[str, str | int] = {
        "dbname": database,
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "user": os.environ.get("POSTGRES_USER", "assessment"),
    }
    port = os.environ.get("POSTGRES_PORT", "5432")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if port:
        parameters["port"] = int(port)
    if password:
        parameters["password"] = password
    return parameters


def ensure_database() -> None:
    """Create ``task09`` if absent so pytest-django can create ``test_task09``."""
    with (
        psycopg.connect(autocommit=True, **_connection_parameters("postgres")) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if cursor.fetchone() is None:
            statement = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME))
            cursor.execute(statement)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    ensure_database()
