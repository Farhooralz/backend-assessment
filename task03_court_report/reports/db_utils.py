"""PostgreSQL bootstrap shared by pytest and the ``ensure_db`` command."""

import os

import psycopg
from psycopg import sql

DEFAULT_DB_NAME = "task03"


def connection_kwargs(dbname: str = "postgres") -> dict[str, str]:
    """Map the task's environment contract onto psycopg connection parameters."""
    kwargs: dict[str, str] = {
        "dbname": dbname,
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
    }
    port = os.environ.get("POSTGRES_PORT", "5432")
    if port:
        kwargs["port"] = port
    return kwargs


def ensure_database(db_name: str = DEFAULT_DB_NAME) -> None:
    """Create ``db_name`` if missing; a second call is a harmless no-op."""
    with (
        psycopg.connect(**connection_kwargs(), autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
