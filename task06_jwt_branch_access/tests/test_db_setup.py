"""Reproducible PostgreSQL bootstrap shared by pytest and the manage command."""

from django.core.management import call_command

from access.db_utils import ensure_database

TASK_DB = "task06"


def test_spec_ensure_database_is_idempotent() -> None:
    ensure_database(TASK_DB)
    ensure_database(TASK_DB)


def test_spec_ensure_db_management_command_is_idempotent() -> None:
    call_command("ensure_db")
    call_command("ensure_db")
