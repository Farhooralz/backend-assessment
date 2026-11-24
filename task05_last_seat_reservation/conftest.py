"""Create the isolated task database before pytest-django connects to it."""

import pytest

from reservations.db import ensure_database


@pytest.fixture(scope="session", autouse=True)
def ensure_task_database() -> None:
    """Django can only create test_task05 once the task05 database exists."""
    ensure_database()
