"""Create the isolated task database before pytest-django builds test_task07."""

from types import SimpleNamespace

import pytest

from ledger.db_utils import ensure_database


def pytest_configure() -> None:
    """Create task07 once; pytest-django then creates test_task07 from its migrations."""
    ensure_database()


@pytest.fixture
def user() -> SimpleNamespace:
    return SimpleNamespace(id=42)
