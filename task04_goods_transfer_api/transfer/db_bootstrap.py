"""Database bootstrap shared by pytest and the ``ensure_db`` management command."""

import os

import psycopg
from psycopg import sql

DATABASE_NAME = "task04"
MAINTENANCE_DB = "postgres"


def connect(**overrides) -> psycopg.Connection:
    """Connect to the maintenance database using the task environment contract."""
    params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "user": os.environ.get("POSTGRES_USER", "assessment"),
        "dbname": MAINTENANCE_DB,
    }
    port = os.environ.get("POSTGRES_PORT", "5432")
    if port:
        params["port"] = int(port)
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if password:
        params["password"] = password
    params.update(overrides)
    return psycopg.connect(**params)


def database_exists(name: str = DATABASE_NAME) -> bool:
    """Report whether the named database is present."""
    with connect(autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        return cursor.fetchone() is not None


def ensure_database(name: str = DATABASE_NAME) -> bool:
    """Create the task database if missing; return True only when it was created."""
    try:
        with connect(autocommit=True) as connection, connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    except psycopg.errors.DuplicateDatabase:
        return False
    return True
