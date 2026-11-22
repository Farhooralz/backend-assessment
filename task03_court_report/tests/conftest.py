"""Ensure the task database exists before pytest-django creates ``test_task03``."""

import pytest

from reports.db_utils import ensure_database


def pytest_sessionstart(session: pytest.Session) -> None:
    """Create the base ``task03`` database; tolerate it already existing."""
    ensure_database()
