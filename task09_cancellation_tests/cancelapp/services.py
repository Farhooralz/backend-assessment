"""Reservation cancellation policy and its atomic persistence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction

from cancelapp.errors import PermissionDenied, ReservationNotCancellable
from cancelapp.models import RefundDocument, Reservation, User

FULL_REFUND_THRESHOLD = timedelta(hours=24)
HALF_REFUND_THRESHOLD = timedelta(hours=2)

DocumentWriter = Callable[[Reservation, int], None]


@dataclass(frozen=True)
class CancellationResult:
    """Refund decided by the policy for a single cancellation."""

    refund_amount: int


def write_refund_document(reservation: Reservation, amount: int) -> None:
    """Default writer: persist the refund document beside the reservation."""
    RefundDocument.objects.create(reservation=reservation, amount=amount)


def compute_refund(payment_amount: int, remaining: timedelta) -> int:
    """Return the refund in whole rials for the time left before start."""
    if remaining >= FULL_REFUND_THRESHOLD:
        return payment_amount
    if remaining >= HALF_REFUND_THRESHOLD:
        return payment_amount // 2
    return 0


def _may_cancel(reservation: Reservation, user: User) -> bool:
    """Only the owner or a manager of the reservation's branch may cancel."""
    if user.pk == reservation.owner_id:
        return True
    return user.is_manager and user.branch_id == reservation.branch_id


def cancel(
    reservation: Reservation,
    user: User,
    now: datetime,
    document_writer: DocumentWriter = write_refund_document,
) -> CancellationResult:
    """Cancel a confirmed reservation atomically; repeats replay the stored result."""
    if not _may_cancel(reservation, user):
        raise PermissionDenied("Only the owner or a same-branch manager may cancel.")

    if reservation.status == "cancelled":
        document = RefundDocument.objects.get(reservation=reservation)
        return CancellationResult(refund_amount=document.amount)

    if reservation.status != "confirmed":
        raise ReservationNotCancellable("Only a confirmed reservation can be cancelled.")
    if now >= reservation.start:
        raise ReservationNotCancellable("A reservation cannot be cancelled at or after its start.")

    amount = compute_refund(reservation.payment_amount, reservation.start - now)

    with transaction.atomic():
        document_writer(reservation, amount)
        reservation.status = "cancelled"
        reservation.save(update_fields=["status"])

    return CancellationResult(refund_amount=amount)
