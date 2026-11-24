"""Reservation cancellation policy and its atomic persistence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from cancelapp.errors import (
    InconsistentStateError,
    PermissionDenied,
    ReservationNotCancellable,
)
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
    now: datetime | None = None,
    document_writer: DocumentWriter = write_refund_document,
) -> CancellationResult:
    """Cancel a confirmed reservation atomically; repeats replay the stored result."""
    if not _may_cancel(reservation, user):
        raise PermissionDenied("Only the owner or a same-branch manager may cancel.")

    moment = timezone.now() if now is None else now
    with transaction.atomic():
        # Lock first: a racing caller then sees the committed status and replays
        # the stored result instead of writing a second refund document.
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if locked.status == "cancelled":
            try:
                document = RefundDocument.objects.get(reservation=locked)
            except RefundDocument.DoesNotExist as exc:
                msg = "a cancelled reservation must have a refund document"
                raise InconsistentStateError(msg) from exc
            return CancellationResult(refund_amount=document.amount)
        if locked.status != "confirmed":
            raise ReservationNotCancellable("Only a confirmed reservation can be cancelled.")
        if moment >= locked.start:
            raise ReservationNotCancellable(
                "A reservation cannot be cancelled at or after its start."
            )

        amount = compute_refund(locked.payment_amount, locked.start - moment)
        document_writer(locked, amount)
        locked.status = "cancelled"
        locked.save(update_fields=["status"])

    return CancellationResult(refund_amount=amount)
