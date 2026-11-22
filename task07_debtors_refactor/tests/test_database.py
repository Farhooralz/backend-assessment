"""Idempotency contract for the shared database bootstrap helper."""

import psycopg

from ledger.db_utils import DB_NAME, ensure_database, pg_kwargs


def test_spec_ensure_database_is_idempotent() -> None:
    """Repeated calls must not raise and must leave exactly one task database."""
    ensure_database()
    ensure_database()
    with psycopg.connect(dbname="postgres", autocommit=True, **pg_kwargs()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM pg_database WHERE datname = %s", (DB_NAME,)
        ).fetchone()[0]
    assert count == 1
