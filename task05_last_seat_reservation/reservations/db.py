"""Idempotent creation of the isolated task database from the shared env contract."""

import contextlib
import os

import psycopg

DB_NAME = "task05"


def pg_params(dbname: str) -> dict[str, str]:
    """Translate the shared env contract into psycopg connection parameters."""
    params: dict[str, str] = {
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


def ensure_database() -> None:
    """Create the task database if absent, so migrate works on a fresh setup."""
    with (
        psycopg.connect(**pg_params("postgres"), autocommit=True) as conn,
        contextlib.suppress(psycopg.errors.DuplicateDatabase),
    ):
        conn.execute(f'CREATE DATABASE "{DB_NAME}"')
