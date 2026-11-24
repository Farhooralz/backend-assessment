"""Shared database fixtures; every test supplies its own clock explicitly."""

from datetime import UTC, datetime

import pytest

from cancelapp.db_setup import ensure_database
from cancelapp.models import Branch, Reservation, User

# Must run before pytest-django creates test_task09.
ensure_database()

START = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def branch(db) -> Branch:
    """A branch that both the owner and the test manager belong to."""
    return Branch.objects.create(name="North")


@pytest.fixture
def owner(branch: Branch) -> User:
    """A plain (non-manager) user who owns the reservation."""
    return User.objects.create(name="owner", branch=branch)


@pytest.fixture
def reservation(branch: Branch, owner: User) -> Reservation:
    """A confirmed 101-rial reservation starting at a fixed UTC instant."""
    return Reservation.objects.create(
        owner=owner,
        branch=branch,
        start=START,
        payment_amount=101,
        status="confirmed",
    )
