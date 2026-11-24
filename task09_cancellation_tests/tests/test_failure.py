"""Failure tests: a refund-document error must roll back the cancellation."""

from datetime import timedelta

import psycopg
import pytest
from django.db import connection

from cancelapp import db_setup
from cancelapp.errors import RefundDocumentWriteError
from cancelapp.models import RefundDocument, Reservation
from cancelapp.services import DocumentWriter, cancel


def _creating_then_failing_writer(created_ids: list[int]) -> DocumentWriter:
    """Insert the document first, then fail: the failure follows a real write."""

    def writer(reservation: Reservation, amount: int) -> None:
        document = RefundDocument.objects.create(reservation=reservation, amount=amount)
        created_ids.append(document.pk)
        raise RefundDocumentWriteError("document storage unavailable")

    return writer


def _committed_state(reservation_id: int) -> tuple[str, int]:
    """Read the committed state through a connection independent of the service's."""
    parameters = db_setup._connection_parameters(connection.settings_dict["NAME"])
    with psycopg.connect(**parameters) as other, other.cursor() as cursor:
        cursor.execute("SELECT status FROM cancelapp_reservation WHERE id = %s", (reservation_id,))
        status: str = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM cancelapp_refunddocument WHERE reservation_id = %s",
            (reservation_id,),
        )
        documents: int = cursor.fetchone()[0]
    return status, documents


@pytest.mark.django_db(transaction=True)
def test_spec_document_write_failure_rolls_back(reservation: Reservation) -> None:
    created_ids: list[int] = []
    with pytest.raises(RefundDocumentWriteError, match="document storage unavailable"):
        cancel(
            reservation,
            reservation.owner,
            reservation.start - timedelta(hours=25),
            document_writer=_creating_then_failing_writer(created_ids),
        )
    assert len(created_ids) == 1, "the failure must be injected after the document INSERT"
    assert _committed_state(reservation.pk) == ("confirmed", 0)


@pytest.mark.django_db(transaction=True)
def test_spec_failed_write_leaves_no_repeat_result(reservation: Reservation) -> None:
    created_ids: list[int] = []
    with pytest.raises(RefundDocumentWriteError):
        cancel(
            reservation,
            reservation.owner,
            reservation.start - timedelta(hours=25),
            document_writer=_creating_then_failing_writer(created_ids),
        )
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert result.refund_amount == 101
    assert RefundDocument.objects.filter(reservation=reservation).count() == 1
