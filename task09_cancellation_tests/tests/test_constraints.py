"""Tests that pin the explicit constraints and deliverables of the spec."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection

from cancelapp.models import Reservation
from cancelapp.services import cancel
from mutation_check import DEFECTS, MUTATIONS


def test_spec_uses_pytest_django(django_db_setup: None) -> None:
    assert settings.configured
    assert "cancelapp" in settings.INSTALLED_APPS
    assert connection.vendor == "postgresql"


@pytest.mark.django_db
def test_spec_simulates_document_writing_failure(reservation: Reservation) -> None:
    def broken_writer(_reservation: Reservation, _amount: int) -> None:
        raise RuntimeError("simulated document failure")

    with pytest.raises(RuntimeError, match="simulated document failure"):
        cancel(
            reservation,
            reservation.owner,
            reservation.start - timedelta(hours=25),
            document_writer=broken_writer,
        )


def test_spec_three_deliberate_defects_are_defined() -> None:
    assert len(DEFECTS) == 3
    assert all(name in MUTATIONS for name in DEFECTS)
    assert all(MUTATIONS[name][2] for name in DEFECTS)
