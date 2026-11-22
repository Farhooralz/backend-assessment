"""Tests for the env-driven, idempotent PostgreSQL bootstrap helper."""

from __future__ import annotations

import pytest

from cancelapp import db_setup


class FakeCursor:
    """Record statements so the create path can be observed without a server."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: object, _params: tuple[str] | None = None) -> None:
        self.statements.append(statement)

    def fetchone(self) -> tuple[int] | None:
        return None


class FakeConnection:
    """Minimal connection context manager around a FakeCursor."""

    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_spec_db_setup_reads_port_and_password_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "/var/run/postgresql")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_USER", "assessment")
    monkeypatch.setenv("POSTGRES_PASSWORD", "placeholder")
    assert db_setup._connection_parameters("postgres") == {
        "dbname": "postgres",
        "host": "/var/run/postgresql",
        "user": "assessment",
        "port": 5432,
        "password": "placeholder",
    }


def test_spec_db_setup_omits_empty_socket_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PORT", "")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    parameters = db_setup._connection_parameters("postgres")
    assert "port" not in parameters
    assert "password" not in parameters


def test_spec_db_setup_creates_missing_database_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(
        db_setup.psycopg,
        "connect",
        lambda **_kwargs: FakeConnection(cursor),
    )
    db_setup.ensure_database()
    assert len(cursor.statements) == 2
    assert "CREATE DATABASE" in str(cursor.statements[1])
