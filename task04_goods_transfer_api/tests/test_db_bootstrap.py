"""Tests for reproducible database bootstrap helpers."""

from unittest.mock import patch

from django.core.management import call_command

from transfer import db_bootstrap

PROBE_DB = "task04_ensure_db_probe"


def _drop_probe() -> None:
    """Remove the scratch database used by the idempotency test."""
    with db_bootstrap.connect(autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("DROP DATABASE IF EXISTS task04_ensure_db_probe")


def test_spec_ensure_database_is_idempotent():
    _drop_probe()
    try:
        assert db_bootstrap.ensure_database(PROBE_DB) is True
        assert db_bootstrap.database_exists(PROBE_DB) is True
        assert db_bootstrap.ensure_database(PROBE_DB) is False
        assert db_bootstrap.database_exists(PROBE_DB) is True
    finally:
        _drop_probe()


def test_spec_ensure_db_command_calls_ensure_database():
    with patch(
        "transfer.management.commands.ensure_db.ensure_database", return_value=False
    ) as ensure:
        call_command("ensure_db")
    ensure.assert_called_once_with()
