"""Ensure the task database exists before pytest-django creates ``test_task03``."""

import os

import psycopg
import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """Create the base ``task03`` database; tolerate it already existing."""
    kwargs: dict[str, str] = {
        "dbname": "postgres",
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
    }
    port = os.environ.get("POSTGRES_PORT", "5432")
    if port:
        kwargs["port"] = port

    with psycopg.connect(**kwargs, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("task03",))
        if cur.fetchone() is None:
            cur.execute("CREATE DATABASE task03")
