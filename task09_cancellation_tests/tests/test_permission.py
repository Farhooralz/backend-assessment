"""Permission tests: owner, same-branch manager, and outsiders."""

from datetime import timedelta

import pytest

from cancelapp.errors import PermissionDenied
from cancelapp.models import Branch, RefundDocument, Reservation, User
from cancelapp.services import cancel

CANCEL_TIME_BEFORE_START = timedelta(hours=25)


@pytest.mark.django_db
def test_spec_same_branch_manager_can_cancel(reservation: Reservation) -> None:
    manager = User.objects.create(name="manager", branch=reservation.branch, is_manager=True)
    result = cancel(reservation, manager, reservation.start - CANCEL_TIME_BEFORE_START)
    assert result.refund_amount == 101


@pytest.mark.django_db
def test_spec_other_branch_manager_cannot_cancel(reservation: Reservation) -> None:
    other_branch = Branch.objects.create(name="South")
    manager = User.objects.create(name="other-manager", branch=other_branch, is_manager=True)
    with pytest.raises(PermissionDenied):
        cancel(reservation, manager, reservation.start - CANCEL_TIME_BEFORE_START)
    reservation.refresh_from_db()
    assert reservation.status == "confirmed"
    assert RefundDocument.objects.count() == 0


@pytest.mark.django_db
def test_spec_unrelated_user_cannot_cancel(reservation: Reservation) -> None:
    stranger = User.objects.create(name="stranger", branch=reservation.branch)
    with pytest.raises(PermissionDenied):
        cancel(reservation, stranger, reservation.start - CANCEL_TIME_BEFORE_START)
    reservation.refresh_from_db()
    assert reservation.status == "confirmed"
    assert RefundDocument.objects.count() == 0
