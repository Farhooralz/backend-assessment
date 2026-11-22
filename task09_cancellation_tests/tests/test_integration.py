"""Integration tests: cancel against the database with an injected clock."""

from datetime import timedelta

import pytest

from cancelapp.errors import ReservationNotCancellable
from cancelapp.models import RefundDocument, Reservation
from cancelapp.services import CancellationResult, cancel


@pytest.mark.django_db
def test_spec_owner_can_cancel(reservation: Reservation) -> None:
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert result == CancellationResult(refund_amount=101)


@pytest.mark.django_db
def test_spec_cancel_records_cancellation_and_refund_document(reservation: Reservation) -> None:
    cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    reservation.refresh_from_db()
    assert reservation.status == "cancelled"
    document = RefundDocument.objects.get(reservation=reservation)
    assert document.amount == 101


@pytest.mark.django_db
def test_spec_exactly_24h_remaining_returns_101(reservation: Reservation) -> None:
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=24))
    assert result.refund_amount == 101


@pytest.mark.django_db
def test_spec_24h_plus_one_second_returns_50(reservation: Reservation) -> None:
    now = reservation.start - timedelta(hours=24) + timedelta(seconds=1)
    assert cancel(reservation, reservation.owner, now).refund_amount == 50


@pytest.mark.django_db
def test_spec_exactly_2h_remaining_returns_50(reservation: Reservation) -> None:
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=2))
    assert result.refund_amount == 50


@pytest.mark.django_db
def test_spec_2h_plus_one_second_returns_zero(reservation: Reservation) -> None:
    now = reservation.start - timedelta(hours=2) + timedelta(seconds=1)
    assert cancel(reservation, reservation.owner, now).refund_amount == 0


@pytest.mark.django_db
def test_spec_at_start_instant_rejected(reservation: Reservation) -> None:
    with pytest.raises(ReservationNotCancellable):
        cancel(reservation, reservation.owner, reservation.start)
    reservation.refresh_from_db()
    assert reservation.status == "confirmed"
    assert RefundDocument.objects.count() == 0


@pytest.mark.django_db
def test_spec_after_start_rejected(reservation: Reservation) -> None:
    with pytest.raises(ReservationNotCancellable):
        cancel(reservation, reservation.owner, reservation.start + timedelta(seconds=1))


@pytest.mark.django_db
def test_spec_non_confirmed_reservation_rejected(reservation: Reservation) -> None:
    reservation.status = "pending"
    reservation.save(update_fields=["status"])
    with pytest.raises(ReservationNotCancellable):
        cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))


@pytest.mark.django_db
def test_spec_repeat_returns_previous_result(reservation: Reservation) -> None:
    first = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert first.refund_amount == 101
    # A replay after the start must not recompute or create a second document.
    second = cancel(reservation, reservation.owner, reservation.start + timedelta(hours=1))
    assert second == first
    assert RefundDocument.objects.filter(reservation=reservation).count() == 1


@pytest.mark.django_db
def test_spec_clock_is_injected_not_read_from_wall(
    monkeypatch: pytest.MonkeyPatch, reservation: Reservation
) -> None:
    class ForbiddenWallClock:
        @staticmethod
        def now() -> None:
            raise AssertionError("the service must not read the wall clock")

    monkeypatch.setattr("cancelapp.services.datetime", ForbiddenWallClock, raising=False)
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert result.refund_amount == 101
