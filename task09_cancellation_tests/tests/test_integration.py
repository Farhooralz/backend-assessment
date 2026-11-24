"""Integration tests: cancel against the database with an injected clock."""

from datetime import datetime, timedelta

import pytest

import cancelapp.errors as errors
from cancelapp.errors import ReservationNotCancellable
from cancelapp.models import RefundDocument, Reservation
from cancelapp.services import CancellationResult, cancel


class FakeTimezone:
    """Stand-in for the only clock the service is allowed to read."""

    def __init__(self, value: datetime) -> None:
        self.value = value
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self.value


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
def test_spec_cancelled_without_document_raises_inconsistent_state(
    reservation: Reservation,
) -> None:
    reservation.status = "cancelled"
    reservation.save(update_fields=["status"])
    with pytest.raises(errors.InconsistentStateError):
        cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert RefundDocument.objects.filter(reservation=reservation).count() == 0


@pytest.mark.django_db
def test_spec_default_clock_is_timezone_now(
    monkeypatch: pytest.MonkeyPatch, reservation: Reservation
) -> None:
    clock = FakeTimezone(reservation.start - timedelta(hours=3))
    monkeypatch.setattr("cancelapp.services.timezone", clock, raising=False)
    result = cancel(reservation, reservation.owner)
    assert clock.calls == 1
    assert result.refund_amount == 50


@pytest.mark.django_db
def test_spec_explicit_now_does_not_read_default_clock(
    monkeypatch: pytest.MonkeyPatch, reservation: Reservation
) -> None:
    class ExplodingClock:
        @staticmethod
        def now() -> datetime:
            raise AssertionError("the service must use the injected now, not the default clock")

    monkeypatch.setattr("cancelapp.services.timezone", ExplodingClock(), raising=False)
    result = cancel(reservation, reservation.owner, reservation.start - timedelta(hours=25))
    assert result.refund_amount == 101
