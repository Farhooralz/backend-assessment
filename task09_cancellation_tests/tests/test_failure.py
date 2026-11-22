"""Failure tests: a refund-document error must roll back the cancellation."""

from datetime import timedelta

import pytest

from cancelapp.errors import RefundDocumentWriteError
from cancelapp.models import RefundDocument, Reservation
from cancelapp.services import cancel


def failing_writer(_reservation: Reservation, _amount: int) -> None:
    """Simulate a storage failure while writing the refund document."""
    raise RefundDocumentWriteError("document storage unavailable")


@pytest.mark.django_db
def test_spec_document_write_failure_rolls_back(reservation: Reservation) -> None:
    with pytest.raises(RefundDocumentWriteError, match="document storage unavailable"):
        cancel(
            reservation,
            reservation.owner,
            reservation.start - timedelta(hours=25),
            document_writer=failing_writer,
        )
    reservation.refresh_from_db()
    assert reservation.status == "confirmed"
    assert RefundDocument.objects.count() == 0


@pytest.mark.django_db
def test_spec_failed_write_leaves_no_repeat_result(reservation: Reservation) -> None:
    with pytest.raises(RefundDocumentWriteError):
        cancel(
            reservation,
            reservation.owner,
            reservation.start - timedelta(hours=25),
            document_writer=failing_writer,
        )
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert result.refund_amount == 101
    assert RefundDocument.objects.filter(reservation=reservation).count() == 1
