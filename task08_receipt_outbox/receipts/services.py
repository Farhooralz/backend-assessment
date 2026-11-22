"""Plain services for the transactional outbox and its recovery rules."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

import redis
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from kombu.exceptions import OperationalError

from receipts import fake_service
from receipts.models import OutboxAttempt, OutboxMessage, Payment, Receipt

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
# next_attempt_at doubles as a dispatch lease so beat will not re-claim a slow send.
LEASE_SECONDS = 30


def backoff_seconds(attempts: int) -> int:
    """Return increasing retry intervals: 1, 2, 4, 8 seconds."""
    return 2 ** (attempts - 1)


def enqueue_dispatch(message_id: int) -> None:
    """Publish one task; a broker failure leaves the committed row for the sweeper."""
    from receipts.tasks import dispatch_receipt

    try:
        dispatch_receipt.delay(message_id)
    except (OperationalError, redis.exceptions.ConnectionError) as exc:
        # The row is already committed; the sweeper will find it on the next tick.
        logger.warning(
            "broker enqueue failed for outbox %s; sweeper will recover: %s", message_id, exc
        )


def _to_rial(amount_rial: int | Decimal) -> int:
    """Reject floats and fractional Decimals instead of silently truncating money."""
    if isinstance(amount_rial, bool) or not isinstance(amount_rial, int | Decimal):
        raise ValueError(f"amount_rial must be int or Decimal, got {type(amount_rial).__name__}")
    rial = int(amount_rial)
    if rial != amount_rial:
        raise ValueError("amount_rial must be a whole number of rials")
    return rial


def record_payment(
    reference: str, amount_rial: int | Decimal, *, now: datetime | None = None
) -> Payment:
    """Store the payment and its receipt outbox row in one transaction."""
    moment = now or timezone.now()
    rial = _to_rial(amount_rial)
    with transaction.atomic():
        payment = Payment.objects.create(reference=reference, amount_rial=rial)
        outbox = OutboxMessage.objects.create(
            payment=payment,
            idempotency_key=f"receipt:{reference}",
            payload={"reference": reference, "amount_rial": rial},
            next_attempt_at=moment,
        )
        transaction.on_commit(lambda: enqueue_dispatch(outbox.pk))
    return payment


def claim_due_messages(*, now: datetime | None = None) -> list[int]:
    """Read due rows with skip_locked; the lock ends before the caller enqueues.

    Two sweepers can therefore return the same id. That is harmless: the task
    re-locks the row, checks the lease/backoff, and the external Fake keys on the
    idempotency key, so at most one send and one receipt are created.
    """
    moment = now or timezone.now()
    with transaction.atomic():
        return list(
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=(OutboxMessage.Status.PENDING, OutboxMessage.Status.IN_PROGRESS),
                next_attempt_at__lte=moment,
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )


def sweep_outbox(*, now: datetime | None = None) -> int:
    """Periodic recovery: enqueue every due row, including rows left by a crash."""
    ids = claim_due_messages(now=now)
    for message_id in ids:
        enqueue_dispatch(message_id)
    return len(ids)


def record_receipt(outbox: OutboxMessage, external_message_id: str) -> None:
    """Create at most one local receipt for an outbox row."""
    with transaction.atomic():
        Receipt.objects.get_or_create(
            outbox=outbox,
            defaults={
                "idempotency_key": outbox.idempotency_key,
                "external_message_id": external_message_id,
            },
        )


def _next_attempt_no(outbox: OutboxMessage, attempts: int) -> int:
    """Keep attempt numbers monotonic even when an operator resets the retry counter."""
    highest = (
        OutboxAttempt.objects.filter(message=outbox).aggregate(Max("attempt_no"))["attempt_no__max"]
        or 0
    )
    return max(highest, attempts - 1) + 1


def _relock_claim(message_id: int, attempts: int) -> tuple[OutboxMessage | None, str]:
    """Re-lock a row and check that this worker still owns the claim."""
    current = OutboxMessage.objects.select_for_update().get(pk=message_id)
    if current.status == OutboxMessage.Status.IN_PROGRESS and current.attempts == attempts:
        return current, current.status
    return None, current.status


def _finish_attempt(message_id: int, attempt_no: int, outcome: str, error: str = "") -> None:
    """Record the final outcome of one attempt inside the caller's transaction."""
    OutboxAttempt.objects.filter(message_id=message_id, attempt_no=attempt_no).update(
        outcome=outcome, error=error
    )


def process_outbox_message(
    message_id: int,
    *,
    now: datetime | None = None,
    service: fake_service.FakeReceiptService | None = None,
) -> str:
    """Dispatch one due outbox row; never let a stale worker write state."""
    moment = now or timezone.now()
    gateway = service or fake_service.FakeReceiptService()
    with transaction.atomic():
        outbox = OutboxMessage.objects.select_for_update().get(pk=message_id)
        if outbox.status in (OutboxMessage.Status.SENT, OutboxMessage.Status.FAILED):
            return outbox.status
        if outbox.next_attempt_at > moment:
            # Future backoff for PENDING, live lease for IN_PROGRESS: no attempt consumed.
            return outbox.status
        attempts = outbox.attempts + 1
        attempt_no = _next_attempt_no(outbox, attempts)
        if attempts > MAX_ATTEMPTS:
            reason = "worker crashed repeatedly"
            outbox.status = OutboxMessage.Status.FAILED
            outbox.last_error = reason
            outbox.save(update_fields=["status", "last_error"])
            OutboxAttempt.objects.create(
                message=outbox,
                attempt_no=attempt_no,
                started_at=moment,
                outcome=OutboxAttempt.Outcome.FAILED,
                error=reason,
            )
            return OutboxMessage.Status.FAILED
        outbox.status = OutboxMessage.Status.IN_PROGRESS
        outbox.attempts = attempts
        outbox.next_attempt_at = moment + timedelta(seconds=LEASE_SECONDS)
        outbox.save(update_fields=["status", "attempts", "next_attempt_at"])
        OutboxAttempt.objects.create(message=outbox, attempt_no=attempt_no, started_at=moment)

    try:
        result = gateway.send(outbox.idempotency_key, outbox.payload)
    except fake_service.ReceiptTimeoutError:
        result = gateway.lookup(outbox.idempotency_key)
        if result is None:
            return _defer(message_id, attempts, attempt_no, moment, "temporary: response timed out")
    except fake_service.PermanentReceiptError as exc:
        return _fail(message_id, attempts, attempt_no, str(exc))
    except fake_service.TemporaryReceiptError as exc:
        return _defer(message_id, attempts, attempt_no, moment, f"temporary: {exc}")

    with transaction.atomic():
        current, status = _relock_claim(message_id, attempts)
        if current is None:
            return status
        record_receipt(current, result.external_message_id)
        current.status = OutboxMessage.Status.SENT
        current.last_error = ""
        current.save(update_fields=["status", "last_error"])
        _finish_attempt(message_id, attempt_no, OutboxAttempt.Outcome.SENT)
    return OutboxMessage.Status.SENT


def _defer(message_id: int, attempts: int, attempt_no: int, now: datetime, error: str) -> str:
    """Schedule another attempt, or stop after the fifth failure."""
    exhausted = attempts >= MAX_ATTEMPTS
    next_attempt = now if exhausted else now + timedelta(seconds=backoff_seconds(attempts))
    outcome = OutboxAttempt.Outcome.FAILED if exhausted else OutboxAttempt.Outcome.DEFERRED
    with transaction.atomic():
        current, status = _relock_claim(message_id, attempts)
        if current is None:
            return status
        current.status = OutboxMessage.Status.FAILED if exhausted else OutboxMessage.Status.PENDING
        current.next_attempt_at = next_attempt
        current.last_error = error
        current.save(update_fields=["status", "next_attempt_at", "last_error"])
        _finish_attempt(message_id, attempt_no, outcome, error)
    return current.status


def _fail(message_id: int, attempts: int, attempt_no: int, error: str) -> str:
    """Stop immediately for a permanent rejection."""
    message = f"permanent: {error}"
    with transaction.atomic():
        current, status = _relock_claim(message_id, attempts)
        if current is None:
            return status
        current.status = OutboxMessage.Status.FAILED
        current.last_error = message
        current.save(update_fields=["status", "last_error"])
        _finish_attempt(message_id, attempt_no, OutboxAttempt.Outcome.FAILED, message)
    return OutboxMessage.Status.FAILED
