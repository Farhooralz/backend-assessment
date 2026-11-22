"""Bootstrap the isolated task database from the shared env contract."""

import contextlib
import os

import psycopg

DB_NAME = "task07"


def pg_kwargs() -> dict[str, str]:
    """Map the env contract to psycopg arguments (empty values are omitted)."""
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


def ensure_database(db_name: str = DB_NAME) -> None:
    """Create ``db_name`` if absent so fresh check/migrate/shell runs work.

    Connect to ``postgres`` in autocommit mode because CREATE DATABASE cannot
    run inside a transaction; an existing database is not an error.
    """
    statement = psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(db_name))
    with (
        psycopg.connect(dbname="postgres", autocommit=True, **pg_kwargs()) as conn,
        contextlib.suppress(psycopg.errors.DuplicateDatabase),
    ):
        conn.execute(statement)
